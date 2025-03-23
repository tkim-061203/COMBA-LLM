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

defaultCodeCorrecterTemplate = ChatPromptTemplate(
    [
        (
            "system",
            """Please act as a professional Verilog code fixer.
You are provided a Verilog Code with no syntax error, but the Verilog code has functional failure due to testbench check.
You will fix Verilog code based on the input/output traces of a formatted comment pair of the testbench code.
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

defaultCodeGeneratorTemplate = ChatPromptTemplate(
    [
        (
            "system",
            """Please act as a professional verilog code generator.
Based on user requirement, you provide a Verilog Code for A Verilog Compiler, called Verilator.
Please provide `json` output containing the generated Verilog code as a single module or module compositions that can be contruct in a Verilog file.

For example:
{{\"code\": \"module abc();
endmodule
\",
\"description\": \"Any description ...\"}}
""",
        ),
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
    tb_failed: Optional[dict]


class LLMCodeAgent:
    def __init__(self, modulePath: str):
        if not os.environ.get("GROQ_API_KEY"):
            os.environ["GROQ_API_KEY"] = getpass.getpass("Enter API key for Groq: ")

        #

        # Base llm
        self._llm = init_chat_model("llama3-8b-8192", model_provider="groq")

        # LLM Code Fixer
        self._llm_code_fixer = self._llm.with_structured_output(
            CodeOutput, method="json_mode"
        )
        self.code_fixer_chain = defaultCodeFixerTemplate | self._llm_code_fixer

        # LLM Code TB Correcter
        self._llm_code_correcter = self._llm.with_structured_output(
            CodeOutput, method="json_mode"
        )
        self.code_correcter_chain = (
            defaultCodeCorrecterTemplate | self._llm_code_correcter
        )

        self._llm_code_generator = self._llm.with_structured_output(
            CodeOutput, method="json_mode"
        )

        self.code_generator_chain = (
            defaultCodeGeneratorTemplate | self._llm_code_generator
        )

        graph_builder = StateGraph(State)

        graph_builder.add_node("code_generator", self.chatbot_code_generator)
        graph_builder.add_node("code_fixer", self.chatbot_code_fixer)
        graph_builder.add_node("compile", self.compile)

        graph_builder.add_edge(START, "code_generator")
        graph_builder.add_edge("code_generator", "compile")
        # graph_builder.add_edge("compile", "code_fixer")
        graph_builder.add_edge("code_fixer", "compile")
        graph_builder.add_conditional_edges("compile", self.route_compile)
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
        self._modulePathDockerRun = os.path.join(self._moduleWorkPath, "docker_run")
        self._workFolderName = Template.TEMPORARYLLMWORKFOLDERNAME.value

        self._last_print_type = None

    def route_compile(
        self,
        state: State,
    ):
        # """
        # Use in the conditional_edge to route to the ToolNode if the last message
        # has tool calls. Otherwise, route to the end.
        # """
        # if isinstance(state, list):
        #     ai_message = state[-1]
        # elif messages := state.get("messages", []):
        #     ai_message = messages[-1]
        # else:
        #     raise ValueError(f"No messages found in input state to tool_edge: {state}")
        # if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
        #     return "tools"
        # return END
        route_compile_yn = input("Route compile (y/n): ")
        # exception = state["exception"] if "exception" in state else None
        # tb_failed = state["tb_failed"] if "tb_failed" in state else None

        # if exception != None and tb_failed != None and route_compile_yn == "y":
        if self.no_exception_tb_failed(state=state) and route_compile_yn == "y":
            return "code_fixer"
        return END

    def warning_list(self, log: str, firstOnly=True):
        WarningRegex = re.compile(
            r"%(?P<exceptionType>Warning|Error)(?P<lineException>(-(?P<exceptionTitle>[A-Z]*))?:\s(?P<fileName>\w*\.v):(?P<lineNumber>[0-9]*):(?P<posNumber>[0-9]*))?:\s(?P<exceptionContent>.*)",
            re.MULTILINE,
        )

        founds = [
            found.groupdict() | {"span": found.span()}
            for found in WarningRegex.finditer(log)
        ]

        lineWarningContentRegex = re.compile(
            r"(?P<lineNumber>\d+)\s\|\s(?P<logContent>.+)", re.MULTILINE
        )
        # print("founds", founds, len(founds), range(len(founds)), not firstOnly)
        for i in range(len(founds)) if not firstOnly else [0]:

            if len(founds) == 0:
                founds = [{}]
                break

            print("founds[i]", founds[i])

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
        # print("compile", state)
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
            prompt = ""
            if firstWarning["exceptionType"] == "Warning":
                prompt = """The Verilator compiler raises a {exceptionType}, called {exceptionTitle}, for the below module. The content of the {exceptionType} is \"{exceptionContent}\".
    Here is the related in-line content with the {exceptionType}:

    {logContent}
    """.format(
                    **(firstWarning)
                )
            elif firstWarning["lineException"] == None:
                prompt = """The Verilator compiler raises a {exceptionType} for the below module. The content of the {exceptionType} is \"{exceptionContent}\".
""".format(
                    **(firstWarning)
                )
                # if firstWarning["exceptionType"] == "Warning"
                # elif firstWarning['lineException'] == None ""
            else:
                prompt = """The Verilator compiler raises a {exceptionType} for the below module. The content of the {exceptionType} is \"{exceptionContent}\".
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

        #
        # testbench
        result = subprocess.run(
            [
                "make",
                self._modulePathDockerRun,
                f"WORKDIR={self._workFolderName}",
            ],
            stdout=subprocess.PIPE,
        )

        resultSTDOUTUTF8 = result.stdout.decode("utf8")
        tb_failed = self.testbench_failed(resultSTDOUTUTF8)
        if "todoNum" in tb_failed:
            prompt = """The funtion of the generated module is incorrect due to the testbench check.
The incorrect failure is raised between /* TODO BEGIN {todoNum} */ and /* TODO END {todoNum} */ of the testbench code.

The trace values of the inputs are: {inputTrace}
The trace values of the outputs are: {outputTrace}
""".format(
                **tb_failed
            )

            # memory for the tb code
            if "tb_failed" not in state:
                tb_codeFilePath = getMainLLMFilenamePath(
                    self._moduleWorkPath, "cpp", "tb"
                )
                tb_code = readFileContent(tb_codeFilePath)
                prompt = (
                    prompt
                    + """
Here are the content of the testbench code:
{tb_code}
""".format(
                        tb_code=tb_code
                    )
                )
            print(prompt)
            return {
                "exception": None,
                "tb_failed": tb_failed,
                "user_input": prompt,
            }
        return {"exception": None, "tb_failed": None}

    def testbench_failed(self, log: str):

        FailedDetectRegex = re.compile(
            r"#\sTODO\s(?P<todoNum>[0-9]*)\sFailed\sat\ssimtime\s(?P<simtime>[0-9]*)"
        )
        failedDetectMatch = FailedDetectRegex.search(log)

        if failedDetectMatch != None:
            failedDetectMatchDict = failedDetectMatch.groupdict()
            todoNum = failedDetectMatchDict["todoNum"]

            ioTraceRegex = re.compile(
                r"#\sTODO\s[0-9]*\s(INPUT|OUTPUT)\sTRACE:\s(?P<traceContent>.*)"
            )
            ioTraceMatches = [
                ioTraceMatch.groupdict() for ioTraceMatch in ioTraceRegex.finditer(log)
            ]
            inputTraceContent = ioTraceMatches[0]["traceContent"]
            outputTraceContent = ioTraceMatches[1]["traceContent"]
            return {
                "todoNum": todoNum,
                "inputTrace": inputTraceContent,
                "outputTrace": outputTraceContent,
            }
        return {}

    def no_exception_tb_failed(self, state: State):

        exception = state["exception"] if "exception" in state else None
        tb_failed = state["tb_failed"] if "tb_failed" in state else None

        if exception != None or tb_failed != None:
            return False

        return True

    def chatbot_code_fixer(self, state: State):

        # check none exception or none tb failure
        if self.no_exception_tb_failed(state):
            print("No more exception or tb failure to process!")
            interrupt("No more exception to process!")

        chain = (
            self.code_fixer_chain
            if state["exception"] != None
            else self.code_correcter_chain
        )
        # print("chatbot", state)
        for i in range(5):
            try:
                invokeResult = chain.invoke(
                    {
                        "user_input": state["user_input"],
                        "conversation": state["conversation"],
                    }
                )
                break
            except:
                print("Chat bot trial:", i)

        # EOFNEWLINE: Missing newline at end of file (POSIX 3.206).
        if invokeResult["code"][-1] != "\n":
            invokeResult["code"] += "\n"

        return {
            "conversation": [
                HumanMessage(content=state["user_input"]),
                AIMessage(content=json.dumps(invokeResult)),
            ]
        }

    def chatbot_code_generator(self, state: State):

        if input("Generate new code? (y/n): ") == "n":
            curLLMCodeFilePath = getMainLLMFilenamePath(self._moduleWorkPath)
            code = readFileContent(curLLMCodeFilePath)
            content = {"code": code}
            return {
                "conversation": [
                    HumanMessage(content=state["user_input"]),
                    AIMessage(content=json.dumps(content)),
                ]
            }

        # print("chatbot", state)
        for i in range(5):
            try:
                invokeResult = self.code_generator_chain.invoke(
                    {
                        "user_input": state["user_input"],
                        # "conversation": state["conversation"],
                    }
                )
                break
            except:
                print("Chat bot trial:", i)

        # EOFNEWLINE: Missing newline at end of file (POSIX 3.206).
        if invokeResult["code"][-1] != "\n":
            invokeResult["code"] += "\n"

        # print("chatbot_code_generator", invokeResult)

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
            if (
                "conversation" in event
                and len(event["conversation"])
                and self._last_print_type == type(HumanMessage)
            ):
                messagetype = type(event["conversation"][-1])
                contentDict = ast.literal_eval(event["conversation"][-1].content)
                code = contentDict["code"]
                newMessage = messagetype(content=code)
                newMessage.pretty_print()
                self._last_print_type = messagetype
            else:
                HumanMessage(content=event["user_input"]).pretty_print()
                self._last_print_type = type(HumanMessage)

    def __next__(self):
        confirm = input(f"Next? (y/n) ")
        if confirm == "n" or confirm == "N":
            print("End Agent")
            raise StopIteration

        # first generator
        # generate first code

        # description
        description = readFileContent(
            os.path.join(self._modulePath, Template.DESCRIPTIONFILENAME.value)
        )

        # self.stream_graph_updates(self.compile({}))
        self.stream_graph_updates({"user_input": description})
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

        # code
        # code = readFileContent(getMainLLMFilenamePath(self._moduleWorkPath))
        # self._code = code

        # self._graph.update_state(
        #     self._config,
        #     {
        #         "conversation": [
        #             HumanMessage(content=description),
        #             AIMessage(content=f'{{"code": "{code}"}}, "description": ""}}'),
        #             # CodeOuput(code=code, description=""),
        #         ]
        #     },
        # )

        # generate first shoot

        for x in myiter:
            currentStatus = x
            print("iter status", currentStatus[1], ". iter times: ", currentStatus[0])

        print("last status", currentStatus[1], ". iter times: ", currentStatus[0])
