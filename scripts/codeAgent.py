import getpass
import os, subprocess, re, json, ast
from typing import Annotated

from typing_extensions import TypedDict, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver
from IPython.display import Image, display
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import interrupt
from .lazy import (
    readFileContent,
    getMainLLMFilenamePath,
    modulePathToModuleWorkPath,
    saveFileContent,
)
from .constants import Template
from langchain_core.prompts import ChatPromptTemplate

# from pydantic import BaseModel, Field


class CodeOutput(TypedDict):
    """Fixed Verilog Code and any description"""

    code: Annotated[str, ..., "The fixed Verilog code"]
    description: Annotated[
        str,
        ...,
        "Any description. Description for the fixed code, plan to fix the code, ...",
    ]


# `json` output contain
defaultCodeFixerTemplate = ChatPromptTemplate(
    [
        (
            "system",
            """Please act as a professional verilog code fixer.
You are provided a Verilog Code with exceptions, such as Error or Warning from  A Verilog Compiler, called Verilator.
You will fix Verilog code based on the excaption content.
Please provide `json` output containing the fixed Verilog code as a single module or module compositions that can be contruct in a Verilog file.
""",
        ),
        # Means the template will receive an optional list of messages under
        # the "conversation" key
        ("placeholder", "{conversation}"),
        # Equivalently:
        # MessagesPlaceholder(variable_name="conversation", optional=True)
        ("user", "{user_input}"),
    ]
)


class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    conversation: Annotated[list, add_messages]
    user_input: str
    exception: Optional[dict]


class LLMCodeAgent:
    def __init__(self, modulePath: str):
        if not os.environ.get("GROQ_API_KEY"):
            os.environ["GROQ_API_KEY"] = getpass.getpass("Enter API key for Groq: ")

        #
        # LLM Code Fixer

        self._llm_code_fixer = init_chat_model("llama3-8b-8192", model_provider="groq")
        self._llm_code_fixer = self._llm_code_fixer.with_structured_output(
            CodeOutput, method="json_mode"
        )
        self.code_fixer_chain = defaultCodeFixerTemplate | self._llm_code_fixer

        graph_builder = StateGraph(State)

        graph_builder.add_node("code_fixer", self.chatbot_code_fixer)
        graph_builder.add_node("compile", self.compile)

        graph_builder.add_edge(START, "code_fixer")
        graph_builder.add_edge("code_fixer", "compile")
        graph_builder.add_edge("compile", END)

        #
        # memory
        memory = MemorySaver()

        self._graph = graph_builder.compile(checkpointer=memory)

        #
        # config
        self._config = {"configurable": {"thread_id": "1"}}

        #
        self._modulePath = modulePath
        self._moduleWorkPath = modulePathToModuleWorkPath(self._modulePath)
        self._modulePathLint = os.path.join(self._moduleWorkPath, "lint")
        self._workFolderName = Template.TEMPORARYLLMWORKFOLDERNAME.value

        # description
        description = readFileContent(
            os.path.join(self._modulePath, Template.DESCRIPTIONFILENAME.value)
        )

        # code
        code = readFileContent(getMainLLMFilenamePath(self._moduleWorkPath))
        self._code = code
        self._graph.update_state(
            self._config,
            {
                "conversation": [
                    HumanMessage(content=description),
                    AIMessage(content=f'{{"code": "{code}"}}, "description": ""}}'),
                    # CodeOuput(code=code, description=""),
                ]
            },
        )

    def warning_list(self, log: str, firstOnly=True):
        WarningRegex = re.compile(
            r"%(?P<exceptionType>Warning)-(?P<exceptionTitle>[A-Z]*):\s(?P<fileName>\w*\.v):(?P<lineNumber>[0-9]*):(?P<posNumber>[0-9]*):\s(?P<exceptionContent>.*)",
            re.MULTILINE,
        )

        founds = [
            found.groupdict() | {"span": found.span()}
            for found in WarningRegex.finditer(log)
        ]

        lineWarningContentRegex = re.compile(
            r"(?P<lineNumber>\d+)\s\|\s(?P<logContent>.+)", re.MULTILINE
        )
        print("founds", founds, len(founds), range(len(founds)), not firstOnly)
        for i in range(len(founds)) if not firstOnly else [0]:

            if len(founds) == 0:
                founds = [{}]
                break

            curSpan = founds[i]["span"][1] + 1
            nextSpan = founds[i + 1]["span"][0] - 1 if i != len(founds) - 1 else -1

            extractSpan = (curSpan, nextSpan)

            logContent = (
                log[extractSpan[0] : extractSpan[1]]
                if nextSpan != -1
                else log[extractSpan[0] :]
            )
            # error
            founds[i]["exceptionContent"] = founds[i]["exceptionContent"].replace(
                "\r", ""
            )
            founds[i]["logContent"] = "\n".join(
                [
                    f"Line {line.group('lineNumber')}: {line.group('logContent')}"
                    # line
                    for line in lineWarningContentRegex.finditer(logContent)
                ]
            )

        return founds

    def compile(self, state: State):
        curLLMCodeFilePath = getMainLLMFilenamePath(self._moduleWorkPath)

        # cache current
        if "conversation" in state:
            if isinstance(state["conversation"][-1], AIMessage):
                codeOutputDict = ast.literal_eval(state["conversation"][-1].content)
                saveFileContent(curLLMCodeFilePath, codeOutputDict["code"])

        # current code save
        self._curLLMCode = readFileContent(curLLMCodeFilePath)

        # currentLLMFile = open(self._moduleWorkPath,'r+')

        result = subprocess.run(
            [
                "make",
                self._modulePathLint,
                f"WORKDIR={self._workFolderName}",
            ],
            stdout=subprocess.PIPE,
        )

        resultSTDOUTUTF8 = result.stdout.decode("utf8")

        #
        # warning list
        firstWarning, *_ = self.warning_list(resultSTDOUTUTF8)

        if len(firstWarning.keys()):
            prompt = """The Verilator compiler raises a {exceptionType}, called {exceptionTitle}, for the below module. The content of the {exceptionType} is \"{exceptionContent}\".
Here is the related in-line content with the {exceptionType}:

{logContent}
""".format(
                **(firstWarning)
            )

            print("compile", firstWarning)
            return {
                "exception": firstWarning,
                "user_input": prompt,
            }
        print("compile: NO EXCEPTION NOW!", resultSTDOUTUTF8)
        return {"exception": None}

    def chatbot_code_fixer(self, state: State):
        if "exception" in state:
            if state["exception"] == None:
                print("No more exception to process!")
                interrupt("No more exception to process!")
                return {}

        # print("chatbot", state)
        for i in range(5):
            try:
                invokeResult = self.code_fixer_chain.invoke(
                    {
                        "user_input": state["user_input"],
                        "conversation": state["conversation"],
                    }
                )
                break
            except:
                print("Chat bot trial:", i)

        # EOFNEWLINE: Missing newline at end of file (POSIX 3.206).
        if invokeResult["code"][-1] == "\n":
            invokeResult["code"] += "\n"

        return {
            "conversation": [
                HumanMessage(content=state["user_input"]),
                AIMessage(content=json.dumps(invokeResult)),
            ]
        }

    def stream_graph_updates(self, user_input: State):

        events = self._graph.stream(
            user_input,
            self._config,
            stream_mode="values",
        )
        for event in events:
            # print(event)
            event["conversation"][-1].pretty_print()

    def __next__(self):
        confirm = input(f"Next? (y/n) ")
        if confirm == "n" or confirm == "N":
            print("End Agent")
            raise StopIteration

        self.stream_graph_updates(self.compile({}))
        # try:
        # except:
        #     raise StopIteration

        x = self.a
        self.a += 1
        return (x, "Nope")

    def pnggraph(self):
        try:
            display(Image(self._graph.get_graph().draw_mermaid_png()))
        except Exception:
            # This requires some extra dependencies and is optional
            pass

    def __iter__(self):
        #
        # self._graph.update_state(self._config, {"exception": {"test": "ok"}})

        self.a = 1
        self.status = "error"
        return self

    def __call__(self):
        print("Start agent")
        myiter = iter(self)
        currentStatus = None
        for x in myiter:
            currentStatus = x
            print("iter status", currentStatus[1], ". iter times: ", currentStatus[0])

        print("last status", currentStatus[1], ". iter times: ", currentStatus[0])
