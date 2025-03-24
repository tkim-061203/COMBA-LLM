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
    getTemplateFilenamePath,
    modulePathToModuleWorkPath,
    saveFileContent,
)
from .constants import Template
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.config import RunnableConfig
import datetime
from operator import add
from dotenv import load_dotenv

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
You will fix Verilog code based on the exception content.
Please provide `json` output containing the fixed Verilog code as a single module or module compositions that can be contruct in a Verilog file.

For example:
{{\"code\": \"module abc();
endmodule
\",
\"description\": \"Any description ...\"}}

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

For example:
{{\"code\": \"module abc();
endmodule
\",
\"description\": \"Any description ...\"}}

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
    exceptionTitleAdditionContent: Annotated[list[str], add]
    user_input: str
    exception: Optional[dict]
    tb_failed: Optional[dict]
    latest_code: Optional[str]


class LLMCodeAgent:
    def __init__(
        self,
        modulePath: str,
        llm_model: str = "qwen-2.5-coder-32b",
        workFolderName: str = Template.TEMPORARYLLMWORKFOLDERNAME.value,
        model_provider: str = "groq",
        **kwargs,
    ):

        load_dotenv()
        # if not os.environ.get("GROQ_API_KEY"):
        #     os.environ["GROQ_API_KEY"] = getpass.getpass("Enter API key for Groq: ")

        #
        self._llm_model = llm_model
        self._model_provider = model_provider
        # Base llm
        self._llm = init_chat_model(
            llm_model, model_provider=self._model_provider, **kwargs
        )

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
        self._modulePath = modulePath
        self._workFolderName = workFolderName
        self._moduleWorkPath = modulePathToModuleWorkPath(
            self._modulePath, self._workFolderName
        )
        self._modulePathLint = os.path.join(self._moduleWorkPath, "lint")
        self._modulePathDockerRun = os.path.join(self._moduleWorkPath, "docker_run")

        self._moduleName = os.path.basename(self._modulePath)
        self._modulePathBinMake = os.path.join(
            self._moduleWorkPath, f"obj_dir/V{self._moduleName}"
        )

        self._last_print_type = None

        #
        # check Verilator Additional
        self._verilator_warns = readFileContent("rag/verilator_warns.json")
        self._verilator_warns: dict = ast.literal_eval(self._verilator_warns)

    @property
    def config(self):
        myconfig: RunnableConfig = {
            "configurable": {"thread_id": str(self._iteration_time)}
        }
        return myconfig

    @property
    def is_verified_flow(self):
        if self._workFolderName == Template.TEMPORARYWORKFOLDERNAME.value:
            return True
        return False

    def route_compile(
        self,
        state: State,
    ):

        route_compile_yn = (
            "n" if self.is_verified_flow else input("Route compile (y/n): ")
        )

        if (not self.no_exception_tb_failed(state=state)) and route_compile_yn == "y":
            return "code_fixer"
        return END

    def warning_list(self, log: str, firstOnly=True):
        WarningRegex = re.compile(
            r"%(?P<exceptionType>Warning|Error)(?P<lineException>(-(?P<exceptionTitle>[A-Z0-9_]*))?:\s(?P<fileName>\w*\.v):(?P<lineNumber>[0-9]*):(?P<posNumber>[0-9]*))?:\s(?P<exceptionContent>.*)",
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
        curCodeFilePath = getTemplateFilenamePath(self._moduleWorkPath)

        # cache current
        if "conversation" in state and (not self.is_verified_flow):
            if isinstance(state["conversation"][-1], AIMessage):
                # if input("Save new code to file? (y/n): ") == 'y':
                codeOutputDict = ast.literal_eval(state["conversation"][-1].content)
                saveFileContent(curCodeFilePath, codeOutputDict["code"])

        # current code save
        self._curLLMCode = readFileContent(curCodeFilePath)

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

        additionRetState = {
            "tb_failed": {} if "tb_failed" not in state else state["tb_failed"]
        }

        if self.is_verified_flow and len(firstWarning.keys()):
            print("Verified Code Warnings: ", resultSTDOUTUTF8)
            return {
                "exception": firstWarning,
                "latest_code": self._curLLMCode,
            } | additionRetState
        elif len(firstWarning.keys()):
            #
            additionContent = {"exceptionTitleAdditionContent": ""}
            # ask for addition of the warning and update warning description
            if firstWarning["exceptionTitle"] not in self._verilator_warns:
                print("firstWarning", firstWarning)
                if (
                    input(
                        f'New addition content for Verilator warning "{firstWarning['exceptionTitle']}"? (y/n): '
                    )
                    == "y"
                ):
                    self._verilator_warns = readFileContent("rag/verilator_warns.json")
                    self._verilator_warns: dict = ast.literal_eval(
                        self._verilator_warns
                    )

            if (firstWarning["exceptionTitle"] in self._verilator_warns) and (
                firstWarning["exceptionTitle"]
                not in state["exceptionTitleAdditionContent"]
            ):
                additionContent[
                    "exceptionTitleAdditionContent"
                ] = f"""Here is description of the "{firstWarning['exceptionTitle']}":
{self._verilator_warns[firstWarning['exceptionTitle']]}"""
                additionRetState["exceptionTitleAdditionContent"] = [
                    firstWarning["exceptionTitle"]
                ]

            prompt = ""
            if firstWarning["exceptionType"] == "Warning":
                prompt = """The Verilator compiler raises a {exceptionType}, called {exceptionTitle}, for the below module. The content of the {exceptionType} is \"{exceptionContent}\".
Here is the related in-line content with the {exceptionType}:

{logContent}

{exceptionTitleAdditionContent}
    """.format(
                    **(firstWarning | additionContent)
                )
            elif firstWarning["lineException"] != None:  # error with line number
                prompt = """The Verilator compiler raises a {exceptionType} for the below module. The content of the {exceptionType} is \"{exceptionContent}\".
Here is the related in-line content with the {exceptionType}:

{logContent}

{exceptionTitleAdditionContent}
    """.format(
                    **(firstWarning | additionContent)
                )
            elif firstWarning["lineException"] == None:
                prompt = """The Verilator compiler raises a {exceptionType} for the below module. The content of the {exceptionType} is \"{exceptionContent}\".
""".format(
                    **(firstWarning)
                )
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
                "latest_code": self._curLLMCode,
            } | additionRetState
        print("compile: NO EXCEPTION NOW!", resultSTDOUTUTF8)

        #
        # tb check
        if not self.tb_syntax_is_correct:
            interrupt("TB Syntax is incorrect!")

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
        print("tb_failed", tb_failed)
        if "todoNum" in tb_failed:
            prompt = """The funtion of the generated module is incorrect due to the testbench check.
The incorrect failure is raised between /* TODO BEGIN {todoNum} */ and /* TODO END {todoNum} */ of the testbench code. This failure is because "{failureContent}"

The trace values of the inputs are: {inputTrace}
The trace values of the outputs are: {outputTrace}
""".format(
                **tb_failed
            )

            tb_failed_len = (
                len(state["tb_failed"].keys()) if "tb_failed" in state else 0
            )
            # memory for the tb code
            if ("tb_failed" not in state) or (tb_failed_len == 0):
                tb_codeFilePath = getTemplateFilenamePath(
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

            return {
                "exception": None,
                "tb_failed": tb_failed,
                "user_input": prompt,
                "latest_code": self._curLLMCode,
            }

        print("compile: NO EXCEPTION AND TESTBENCH NOW!", resultSTDOUTUTF8)
        return {"exception": None, "tb_failed": None, "latest_code": self._curLLMCode}

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

            failureContentRegex = re.compile(
                r"Assertion\s`.*\"TODO\s[0-9]*\sFailed:\s(?P<failureContent>.*)"
            )
            # failureContent = failureContentRegex.search(log).groupdict()[
            #     "failureContent"
            # ]
            failureContent = failureContentRegex.search(log).groupdict()[
                "failureContent"
            ]

            return {
                "todoNum": todoNum,
                "inputTrace": inputTraceContent,
                "outputTrace": outputTraceContent,
                "failureContent": failureContent,
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
            except Exception as e:
                print("Chat bot trial:", i, e)

        # EOFNEWLINE: Missing newline at end of file (POSIX 3.206).
        if invokeResult["code"][-1] != "\n":
            invokeResult["code"] += "\n"

        return {
            "conversation": [
                HumanMessage(content=state["user_input"]),
                AIMessage(content=json.dumps(invokeResult)),
            ]
        }

    @property
    def tb_syntax_is_correct(self):
        # prepare for docker testbench
        result = subprocess.run(
            [
                "make",
                self._modulePathBinMake,
                f"WORKDIR={self._workFolderName}",
            ],
            stdout=subprocess.PIPE,
        )
        resultSTDOUTUTF8 = result.stdout.decode("utf8")

        tb_failed_regex = re.compile(
            r"^make:\s*\*\*\*\s\[.*\]\sError\s[0-9]*", re.MULTILINE
        )
        tb_failed = True if tb_failed_regex.search(resultSTDOUTUTF8) != None else False

        if tb_failed:
            print("pre tb_failed", resultSTDOUTUTF8)
            return False
        return True

    def chatbot_code_generator(self, state: State):

        generate_new_code = (
            "n" if self.is_verified_flow else input("Generate new code? (y/n): ")
        )
        if generate_new_code == "n":
            curCodeFilePath = getTemplateFilenamePath(self._moduleWorkPath)
            code = readFileContent(curCodeFilePath)
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
            self.config,
            stream_mode="values",
        )
        try:
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
        except:
            pass

    def __next__(self):
        confirm = input("##### Trial: " + str(self._iteration_time) + ". Next? (y/n) ")
        if (confirm == "n" or confirm == "N") or (
            self._iteration_time > self._iteration_time_limit
        ):
            print("End Agent with Iteration trial: ", self._iteration_time)
            raise StopIteration

        # description
        description = readFileContent(
            os.path.join(self._modulePath, Template.DESCRIPTIONFILENAME.value)
        )

        self.stream_graph_updates({"user_input": description})

        cur_graph_state: State = self._graph.get_state(self.config).values

        exception = (
            cur_graph_state["exception"] if "exception" in cur_graph_state else None
        )
        tb_failed = (
            cur_graph_state["tb_failed"] if "tb_failed" in cur_graph_state else None
        )
        print("### Trial ", self._iteration_time, " results:")
        print(
            "\t\t- Trial ", self._iteration_time, " exception pass: ", exception == None
        )
        print("\t\t- Trial ", self._iteration_time, " tb pass: ", tb_failed == None)

        self._iteration_time += 1
        return cur_graph_state

    def pnggraph(self):
        try:
            display(Image(self._graph.get_graph().draw_mermaid_png()))
        except Exception:
            # This requires some extra dependencies and is optional
            pass

    def __iter__(self):
        #
        # self._graph.update_state(self._config, {"exception": {"test": "ok"}})

        self._iteration_time = 0
        self._iteration_time_limit = 4 if not self.is_verified_flow else 1

        self.status = "error"
        return self

    def __call__(self):
        print("Start agent")
        myiter = iter(self)

        # generate first shoot
        json_dumps_report = {
            "llm_model": self._llm_model,
            "history_trial": [],
            "exception_trial": [],
            "tb_failed_trial": [],
            "code_trial": [],
        }

        for iter_report in myiter:
            exception = iter_report["exception"] if "exception" in iter_report else None
            tb_failed = iter_report["tb_failed"] if "tb_failed" in iter_report else None
            latest_code = (
                iter_report["latest_code"] if "latest_code" in iter_report else None
            )
            json_dumps_report["history_trial"].append(
                [
                    {"role": message.type, "content": message.content}
                    for message in iter_report["conversation"]
                ]
            )
            json_dumps_report["exception_trial"].append(exception)
            json_dumps_report["tb_failed_trial"].append(tb_failed)
            json_dumps_report["code_trial"].append(latest_code)

        if not self.is_verified_flow:
            #
            cur_report_path = os.path.join(self._modulePath, "reports")
            if not os.path.isdir(cur_report_path):
                os.mkdir(cur_report_path)
            # save report.json
            with open(
                os.path.join(cur_report_path, f"report_{self._llm_model}.json"), "w+"
            ) as outfile:
                json.dump(json_dumps_report, outfile)

            # save report history
            history_tag = datetime.datetime.now().isoformat()
            # history path
            cur_history_path = os.path.join(self._modulePath, ".history")
            if not os.path.isdir(cur_history_path):
                os.mkdir(cur_history_path)
            with open(
                os.path.join(
                    cur_history_path, f"report_{self._llm_model}_{history_tag}.json"
                ),
                "w+",
            ) as outfile:
                json.dump(json_dumps_report, outfile)

        # count passes
        count_excep_pass = sum(
            [
                1 if excep_pass == None else 0
                for excep_pass in json_dumps_report["exception_trial"]
            ]
        )
        count_tb_pass = sum(
            [
                1 if tb_pass == None else 0
                for tb_pass in json_dumps_report["tb_failed_trial"]
            ]
        )

        print("### Result iter times: ", self._iteration_time)
        print("\t", f"{count_excep_pass}/5 Exception pass")
        print("\t", f"{count_tb_pass}/5 TB pass")
