import os, subprocess, re, json, ast, glob
from typing import Annotated

from typing_extensions import TypedDict, Optional, Literal

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
from .xmlDescription import Module, Modules
from tqdm import tqdm


class CodeOutput(TypedDict):
    """Fixed/Generated Verilog Code and any description"""

    code: Annotated[str, ..., "The fixed/generated Verilog code"]
    description: Annotated[
        str,
        ...,
        "Any description. Description for the fixed/generate code, plan to fix/generate the code, ...",
    ]


# `json` output contain
defaultCodeFixerTemplate = ChatPromptTemplate(
    [
        (
            "system",
            """Please act as a professional verilog code fixer.
You are provided a Verilog Code with exceptions, such as Error or Warning from  A Verilog Compiler, called Verilator.
You will fix Verilog code based on the exception content.
But make sure that your fixing method must not violate any description in the <module /> tag content.
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

#
# reducer
def limitTrialsReducer(left: dict, right: list[str]):

    for r in right:
        if r in left:
            left[r] += 1
        else:
            left[r] = 1

    return left

#
class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    conversation: Annotated[list, add_messages]
    exceptionTitleAdditionContent: Annotated[list[str], add]
    user_input: str
    exception: Optional[dict]
    tb_failed: Optional[dict]
    generated_code: dict
    lastAllSyntaxCompileStatus: list[dict]
    lastTBSimulationSuccessStatus: Annotated[list[dict], add]
    lastSyntaxSimilationSuccessStatus: Annotated[list[dict], add]
    compileStatusSuccess: Optional[bool]
    tbStatusSuccess: Optional[bool]
    tbLimitTrials: Annotated[dict, limitTrialsReducer]
    tbLimitReach: dict
    syntaxLimitTrials: Annotated[dict, limitTrialsReducer]
    syntaxLimitReach: dict
    errorOnlyCompilation: bool


class LLMCodeAgent:
    def __init__(
        self,
        modulePath: str,
        llm_model: str = "qwen-2.5-coder-32b",
        workFolderName: str = Template.TEMPORARYLLMWORKFOLDERNAME.value,
        model_provider: Literal['gpt-4o-mini-2024-07-18', "groq"] = "groq",
        descriptionType: Literal['txt', 'xml'] = 'txt',
        customInputDirective: dict = {
        },
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
        graph_builder.add_node("syntax_compile", self.syntax_compile)
        graph_builder.add_node("tb_simulation", self.tb_simulation)

        graph_builder.add_edge(START, "code_generator")
        graph_builder.add_edge("code_generator", "syntax_compile")
        graph_builder.add_edge("code_fixer", "syntax_compile")
        graph_builder.add_conditional_edges("syntax_compile", self.syntax_compile_route)
        graph_builder.add_conditional_edges("tb_simulation", self.tb_simulation_route)

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

        #
        #
        self._descriptionType = descriptionType

        #
        self._customInputDirective = customInputDirective

    @property
    def config(self):
        myconfig: RunnableConfig = {
            "configurable": {"thread_id": str(self._iteration_time), },
            "recursion_limit": 200
        }
        return myconfig

    @property
    def is_verified_flow(self):
        if self._workFolderName == Template.TEMPORARYWORKFOLDERNAME.value:
            return True
        return False
    
    def compilation_status(self, log:str, errorOnly=True):
        
        warnRegex = "Warning" if not errorOnly else ""
        WarningRegex = re.compile(
            rf"%(?P<exceptionType>{warnRegex}|Error)(?P<lineException>(-(?P<exceptionTitle>[A-Z0-9_]*))?:\s(?P<fileName>\w*\.v):(?P<lineNumber>[0-9]*):(?P<posNumber>[0-9]*))?:\s(?P<exceptionContent>.*)",
            re.MULTILINE,
        )

        founds = [
            found.groupdict() | {"span": found.span()}
            for found in WarningRegex.finditer(log)
        ]

        lineWarningContentRegex = re.compile(
            r"(?P<lineNumber>\d+)\s\|\s(?P<logContent>.+)", re.MULTILINE
        )

        for i in range(len(founds)):
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
        #
        firstException = founds[0] if len(founds) else None
        
        #
        # delete "%Error: Exiting due to 1 error(s)"
        lastExceptionContent:str = founds[-1]["exceptionContent"] if len(founds) else ""
        if "Exiting due to" in lastExceptionContent:
            del founds[-1]

        return (firstException, founds)

    def syntax_compile(self, state: State):
        retState: State = {
            "exception": None
        }

        #
        curCodeFilePath = getTemplateFilenamePath(self._moduleWorkPath)
        codeOutputDict = state["generated_code"]
        saveFileContent(curCodeFilePath, codeOutputDict["code"])

        compilationCpltProcess = subprocess.run(
            [
                "make",
                self._modulePathLint,
                f"WORKDIR={self._workFolderName}",
            ],
            stdout=subprocess.PIPE,
        )

        resultSTDOUTUTF8 = compilationCpltProcess.stdout.decode("utf8")

        #
        # compilation status (firstException, success, all)
        firstException, compileResultAll = self.compilation_status(resultSTDOUTUTF8, state['errorOnlyCompilation'])
        compileStatusSuccess = compilationCpltProcess.returncode == 0

        additionRetState : State = {
            'conversation': [],
            'exceptionTitleAdditionContent': [],
            'compileStatusSuccess': compileStatusSuccess,
            'syntaxLimitTrials': [],
            'lastAllSyntaxCompileStatus': compileResultAll
        }
        
        #
        # check syntax limit
        syntaxLimitKey = f"{firstException["exceptionType"]}-{firstException["exceptionTitle"]}-{firstException["exceptionContent"]}" if firstException != None else None
        if syntaxLimitKey != None:
            additionRetState['syntaxLimitTrials'] += [syntaxLimitKey]
        
        syntaxLimitTrials = state['syntaxLimitTrials'][syntaxLimitKey] if ((syntaxLimitKey != None) and (syntaxLimitKey in state['syntaxLimitTrials'])) else 0
        if syntaxLimitTrials >= 5:
            return {'syntaxLimitReach': firstException}

        totalSyntaxLimitTrials = sum(state['syntaxLimitTrials'].values())
        if totalSyntaxLimitTrials >= 100:
            return {'syntaxLimitReach': {'totalSyntaxLimitTrials': totalSyntaxLimitTrials}}

        if firstException != None:
            if self.is_verified_flow:
                print("Verified Code Warnings: ", resultSTDOUTUTF8)
                retState = retState | ({
                    "exception": firstException,
                } | additionRetState)
            else:
                #
                
                if (firstException["exceptionTitle"] not in self._verilator_warns) and (
                 firstException["exceptionTitle"] != None):
                    with open('reports/log/log.txt', 'a') as file:
                        print(f'Module: {self._moduleName} - New addition content for Verilator warning "{firstException['exceptionTitle']}"', firstException, sep='\n', file=file)
                    print("firstException", firstException)
                    if (
                        self.customInput(f'New addition content for Verilator warning "{firstException['exceptionTitle']}"?', 'syntax_compile')
                        == "y"
                    ):
                        self._verilator_warns = readFileContent("rag/verilator_warns.json")
                        self._verilator_warns: dict = ast.literal_eval(
                            self._verilator_warns
                        )
                    
                if (firstException["exceptionTitle"] in self._verilator_warns) and (
                    firstException["exceptionTitle"]
                    not in state["exceptionTitleAdditionContent"]
                ):
                    additionRetState[
                        "conversation"
                    ] += [HumanMessage(content=f"""Here is description of the "{firstException['exceptionTitle']}":
{self._verilator_warns[firstException['exceptionTitle']]}""")]
                    additionRetState["exceptionTitleAdditionContent"] += [
                    firstException["exceptionTitle"]
                    ]
                prompt = ""
                if firstException["exceptionType"] == "Warning":
                    prompt = """The Verilator compiler raises a {exceptionType}, called {exceptionTitle}, for the below module. The content of the {exceptionType} is \"{exceptionContent}\".
Here is the related in-line content with the {exceptionType}:
{logContent}""".format(
                    **(firstException)
                )
                elif firstException["lineException"] != None:  # error with line number
                    prompt = """The Verilator compiler raises a {exceptionType} for the below module. The content of the {exceptionType} is \"{exceptionContent}\".
Here is the related in-line content with the {exceptionType}:
{logContent}
""".format(
                        **(firstException)
                    )
                elif firstException["lineException"] == None:
                    prompt = """The Verilator compiler raises a {exceptionType} for the below module. The content of the {exceptionType} is \"{exceptionContent}\".
""".format(
                        **(firstException)
                    )
                else:
                    prompt = """The Verilator compiler raises a {exceptionType} for the below module. The content of the {exceptionType} is \"{exceptionContent}\".
Here is the related in-line content with the {exceptionType}:
{logContent}""".format(
                    **(firstException)
                )

                print("compile", firstException)
                retState |= {
                    "exception": firstException,
                    "user_input": prompt,
                }
        
        #
        # No warning, testbench simulation available
        if compileStatusSuccess:
            if len(state['lastTBSimulationSuccessStatus']) == 0:
                firstException, compileResultAll = self.compilation_status(resultSTDOUTUTF8, False)
                additionRetState['lastSyntaxSimilationSuccessStatus'] = [{
                    'exception': firstException,
                    'generated_code': state['generated_code'],
                    'lastAllSyntaxCompileStatus': compileResultAll,
                    'user_input': state['user_input'],
                }]
            print("Compile Status Success: ", resultSTDOUTUTF8)
            
        return retState | additionRetState

    def syntax_compile_route(self, state: State):
        print("syntax_compile_route state: ", "exception:", state["exception"])
        
        syntaxLimitReach = state['syntaxLimitReach'] if 'syntaxLimitReach' in state else None
        tbLimitReach = state['tbLimitReach'] if 'tbLimitReach' in state else None
        
        if syntaxLimitReach == None and tbLimitReach == None:
            syntax_route_compile_yn = (
                "n" if self.is_verified_flow else self.customInput("Syntax Route compile", 'syntax_compile_route')
            )

            if (state['compileStatusSuccess']) and syntax_route_compile_yn == "y":
                return "tb_simulation"
            elif (not state['compileStatusSuccess']) and syntax_route_compile_yn == "y":
                return 'code_fixer'
        return END

    def tb_simulation(self, state: State):
        print("Compile Status Success, check testbench")

        retState: State = {

        }

        additionRetState : State = {
            "tb_failed": {} if "tb_failed" not in state else state["tb_failed"],
            'conversation': [],
            'exceptionTitleAdditionContent': [],
            'tbStatusSuccess': False,
            'tbLimitTrials': [],
        }

        #
        # tb check
        if not self.tb_syntax_is_correct:
            interrupt("TB Syntax is incorrect!")

        # testbench
        tbCpltProcess = subprocess.run(
            [
                "make",
                self._modulePathDockerRun,
                f"WORKDIR={self._workFolderName}",
            ],
            stdout=subprocess.PIPE,
        )

        resultSTDOUTUTF8 = tbCpltProcess.stdout.decode("utf8")
        tbStatusSuccess = tbCpltProcess.returncode == 0
        additionRetState['tbStatusSuccess'] = tbStatusSuccess

        #
        # core.number file
        if not tbStatusSuccess:
            core_number_files = glob.glob('core.[0-9]*')
            # Remove all files one by one
            for file in core_number_files:
                try:
                    os.remove(file)
                except OSError:
                    print("Error while deleting file")

        tb_failed = self.testbench_failed(resultSTDOUTUTF8)

        #
        # check tb limit
        tbLimitKey = f"{tb_failed["todoNum"]}-{tb_failed["failureContent"]}" if (("todoNum" in tb_failed) and ("failureContent" in tb_failed)) else None
        if tbLimitKey != None:
            additionRetState['tbLimitTrials'] += [tbLimitKey]
        
        tbLimitTrials = state['tbLimitTrials'][tbLimitKey] if ((tbLimitKey != None) and (tbLimitKey in state['tbLimitTrials'])) else 0
        if tbLimitTrials >= 5:
            return {'tbLimitReach': tb_failed}

        additionRetState |= {
                "tb_failed": tb_failed,
        }
        print("tb_failed", tb_failed)

        if "todoNum" in tb_failed:
            prompt = """The funtion of the generated module is incorrect due to the testbench check.
The incorrect failure is raised between /* TODO BEGIN {todoNum} */ and /* TODO END {todoNum} */ of the testbench code. This failure is because \"{failureContent}\".

The trace values of the inputs are: {inputTrace}
The trace values of the outputs are: {outputTrace}
The trace values of the expected outputs must be: {refOutputTrace}

Find out related signals mismatchs with the expected outputs. If mismatched and related signals is described in the description <module refid=\"{moduleName}\"/>, fix the mismatchs based on the description <module refid=\"{moduleName}\"/>.
""".format(
            **(tb_failed | {"moduleName": self._moduleName})
        )
            if "tb_failed" not in state['exceptionTitleAdditionContent']:
                tb_codeFilePath = getTemplateFilenamePath(
                    self._moduleWorkPath, "cpp", "tb"
                )
                tb_code = readFileContent(tb_codeFilePath)
                additionRetState[
                    "conversation"
                ] += [HumanMessage(content="""
Here are the content of the testbench code of the Verilog module:
{tb_code}""".format(
                        tb_code=tb_code
                    )
                )]
                additionRetState["exceptionTitleAdditionContent"] += [
                    "tb_failed"
                ]

            additionRetState |= {
                "user_input": prompt,
            }
        elif tbStatusSuccess:
            print("compile: NO EXCEPTION AND TESTBENCH NOW!", resultSTDOUTUTF8)
            additionRetState |= {
                # TODO
                'tb_failed': None,
                'lastTBSimulationSuccessStatus': [{
                    'exception': state['exception'],
                    'generated_code': state['generated_code'],
                    'lastAllSyntaxCompileStatus': state['lastAllSyntaxCompileStatus'],
                    'user_input': state['user_input'],
                }]
            }
            if state['errorOnlyCompilation']:
                errorOnlyCompilationDisable = {
                    'errorOnlyCompilation' : False
                }
                additionRetState |= errorOnlyCompilationDisable
                new_syntax_compile_status : State = self.syntax_compile(state=(state | errorOnlyCompilationDisable))
                additionRetState |= new_syntax_compile_status
                additionRetState |= {
                # TODO
                'tb_failed': None,
                'lastTBSimulationSuccessStatus': [{
                    'exception': new_syntax_compile_status['exception'],
                    'generated_code': state['generated_code'],
                    'lastAllSyntaxCompileStatus': new_syntax_compile_status['lastAllSyntaxCompileStatus'],
                    'user_input': state['user_input'],
                }]
            }
        elif tbStatusSuccess == False and state['errorOnlyCompilation'] == False:
            additionRetState |= state['lastTBSimulationSuccessStatus'][-1]
        else:
            print("TB Simulation raised unknown error!")
            interrupt("TB Simulation raised unknown error!")

        return retState | additionRetState

    def tb_simulation_route(self, state: State):
        print("tb_simulation_route state: tb_failed: ", state['tb_failed'])

        tbLimitReach = state['tbLimitReach'] if 'tbLimitReach' in state else None
        syntaxLimitReach = state['syntaxLimitReach'] if 'syntaxLimitReach' in state else None
        
        if tbLimitReach == None and syntaxLimitReach == None:
            tb_route_compile_yn = (
                "n" if self.is_verified_flow else self.customInput("TB Route compile", 'tb_simulation_route')
            )

            if ((not state['tbStatusSuccess']) or (state['exception'] != None)) and tb_route_compile_yn == "y":
                #
                # TODO: enhancement fallback decision.
                return "code_fixer"
        return END

    def testbench_failed(self, log: str):

        FailedDetectRegex = re.compile(
            r"#\sTODO\s(?P<todoNum>[0-9]*)\sFailed\sat\ssimtime\s(?P<simtime>[0-9]*)"
        )
        failedDetectMatch = FailedDetectRegex.search(log)

        if failedDetectMatch != None:
            failedDetectMatchDict = failedDetectMatch.groupdict()
            todoNum = failedDetectMatchDict["todoNum"]

            ioTraceRegex = re.compile(
                r"#\sTODO\s[0-9]*\s(REFERENCE\s)?(INPUT|OUTPUT)\sTRACE:\s(?P<traceContent>.*)"
            )
            ioTraceMatches = [
                ioTraceMatch.groupdict() for ioTraceMatch in ioTraceRegex.finditer(log)
            ]
            inputTraceContent = ioTraceMatches[0]["traceContent"] if len(ioTraceMatches) > 0 else None
            outputTraceContent = ioTraceMatches[1]["traceContent"] if len(ioTraceMatches) > 1 else None
            refOutputTraceContent = ioTraceMatches[2]["traceContent"] if len(ioTraceMatches) > 2 else None
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
                "refOutputTrace": refOutputTraceContent
            }
        return {}

    def no_exception_tb_failed(self, state: State):

        return state['compileStatusSuccess'] and state['tbStatusSuccess'] and (state['exception'] == None)

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
        generatedModuleMess = [HumanMessage(content=f"""Here is the provided module code:
{state['generated_code']}
""")]
        for i in range(5):
            try:
                invokeResult = chain.invoke(
                    {
                        "user_input": state["user_input"],
                        "conversation": state["conversation"] + generatedModuleMess,
                    }
                )
                break
            except Exception as e:
                print("Chat bot trial:", i, e)

        # EOFNEWLINE: Missing newline at end of file (POSIX 3.206).
        if invokeResult["code"][-1] != "\n":
            invokeResult["code"] += "\n"

        conver_human_mess = HumanMessage(content=state["user_input"])
        # conver_ai_mess = AIMessage(content=json.dumps(invokeResult))
        conver_human_mess.pretty_print()
        # conver_ai_mess.pretty_print()
        AIMessage(content=invokeResult['code']).pretty_print()
        return {
            # "conversation": [
            #     conver_human_mess,
            #     conver_ai_mess
            # ]
            "generated_code": invokeResult
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
            "n" if self.is_verified_flow else self.customInput("Generate new code?", "chatbot_code_generator")
        )
        if generate_new_code == "n":
            curCodeFilePath = getTemplateFilenamePath(self._moduleWorkPath)
            code = readFileContent(curCodeFilePath)
            content = {"code": code}
            conver_human_mess = HumanMessage(content=state["user_input"])
            conver_ai_mess = AIMessage(content=json.dumps(content))
            
            conver_human_mess.pretty_print()
            # conver_ai_mess.pretty_print()
            AIMessage(content=content['code']).pretty_print()
            return {
                "conversation": [
                    conver_human_mess,
                    conver_ai_mess,
                ],
                "generated_code": content,
                # 'queriedCode': content
            }

        for i in range(5):
            try:
                invokeResult = self.code_generator_chain.invoke(
                    {
                        "user_input": state["user_input"],
                    }
                )
                break
            except:
                print("Chat bot trial:", i)

        # EOFNEWLINE: Missing newline at end of file (POSIX 3.206).
        if invokeResult["code"][-1] != "\n":
            invokeResult["code"] += "\n"

        conver_human_mess = HumanMessage(content=state["user_input"])
        conver_ai_mess = AIMessage(content=json.dumps(invokeResult))

        conver_human_mess.pretty_print()
        # conver_ai_mess.pretty_print()
        AIMessage(content=invokeResult['code']).pretty_print()
        return {
            "conversation": [
                conver_human_mess,
                conver_ai_mess
            ],
            "generated_code": invokeResult,
        }
    def checkXMLDescription(self, description:str):

        #
        # Module try
        try:
            self._xmlmodule = Module.from_xml(description)
            valid = True
            formattedXMLDoc:str = self._xmlmodule.to_xml(pretty_print=True).decode('utf-8')
        except:
            valid = False
            formattedXMLDoc = None

        #
        # Modules try
        if valid == False and formattedXMLDoc == None:
            try:
                self._xmlmodule = Modules.from_xml(description)
                valid = True
                formattedXMLDoc:str = self._xmlmodule.to_xml(pretty_print=True).decode('utf-8')
            except:
                valid = False
                formattedXMLDoc = None

        return (valid, formattedXMLDoc)
    def stream_graph_updates(self, user_input: State):
        return self._graph.invoke(user_input,
            self.config,
        )
    def customInput(self, s_in, key):
        #
        # initial
        if key not in self._customInputDirective:
            self._customInputDirective[key] = {
                'yall': False,
                'nall': False
            }

        #
        # yes all
        if self._customInputDirective[key]['yall']:
            return 'y'
        elif self._customInputDirective[key]['nall']:
            return 'n'
        
        while True:
            userInput = input(s_in + " (y/n/ya/na): ")
            if userInput == 'y' or userInput == 'Y' or \
                userInput == 'n' or userInput == 'n' or \
                userInput == 'ya' or userInput == 'YA' or \
                userInput == 'na' or userInput == 'NA':
                if  userInput == 'ya' or userInput == 'YA':
                    self._customInputDirective[key]['yall'] = True
                elif userInput == 'na' or userInput == 'NA':
                    self._customInputDirective[key]['nall'] = True
                break
            print("Wrong choice!", end=" ") 

        return userInput[0]
    def __next__(self):
        confirm = self.customInput("##### Trial: " + str(self._iteration_time) + ". Next?", "__next__")
        if (confirm == "n" or confirm == "N") or (
            self._iteration_time > self._iteration_time_limit
        ):
            print("End Agent with Iteration trial: ", self._iteration_time)
            raise StopIteration

        # description
        description = readFileContent(
            os.path.join(self._modulePath, Template.DESCRIPTIONFILENAME.value if self._descriptionType == 'txt' else Template.DESCRIPTIONXMLFILENAME.value)
        )

        if self._descriptionType == 'xml':
            xmlDescriptionIsValid, formattedXMLDescription = self.checkXMLDescription(description)
            if xmlDescriptionIsValid:
                description = formattedXMLDescription
            else:
                print("End Agent with Iteration trial: ", self._iteration_time, " . Because XML check failed!")
                raise StopIteration
        
        cur_graph_state: State = self.stream_graph_updates({"user_input": description, 'errorOnlyCompilation': True})

        # cur_graph_state: State = self._graph.get_state(self.config).values

        # exception = (
        #     cur_graph_state["exception"] if "exception" in cur_graph_state else None
        # )
        # tb_failed = (
        #     cur_graph_state["tb_failed"] if "tb_failed" in cur_graph_state else None
        # )
        exception = False
        tb_failed = False

        if len(cur_graph_state['lastTBSimulationSuccessStatus']):
            exception = tb_failed = True
        elif len(cur_graph_state['lastSyntaxSimilationSuccessStatus']):
            exception = True

        print("### Trial ", self._iteration_time, " results:")
        print(
            "\t\t- Trial ", self._iteration_time, " exception pass: ", exception
        )
        print("\t\t- Trial ", self._iteration_time, " tb pass: ", tb_failed)

        self._iteration_time += 1

        cur_graph_state = cur_graph_state.copy()
        del cur_graph_state['conversation']
        return cur_graph_state, exception, tb_failed

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
        self._tqdm = {
            "__call__": tqdm(total=(self._iteration_time_limit + 1), desc='Trial')
        }
        return self

    def __call__(self):
        print("Start agent")
        myiter = iter(self)

        # generate first shoot
        json_dumps_report = {
            "llm_model": self._llm_model,
            "exception_trial": [],
            "tb_failed_trial": [],
            "state_trial": [],
        }

        for iter_report, exception, tb_failed in myiter:
            self._tqdm['__call__'].update(1)
            json_dumps_report["exception_trial"].append(exception)
            json_dumps_report["tb_failed_trial"].append(tb_failed)
            json_dumps_report["state_trial"].append(iter_report)

        if not self.is_verified_flow:
            #
            cur_report_path = os.path.join(self._modulePath, "reports")
            if not os.path.isdir(cur_report_path):
                os.mkdir(cur_report_path)
            # save report.json
            with open(
                os.path.join(cur_report_path, f"report_{self._llm_model}.json"), "w"
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
                1 if excep_pass == True else 0
                for excep_pass in json_dumps_report["exception_trial"]
            ]
        )
        count_tb_pass = sum(
            [
                1 if tb_pass == True else 0
                for tb_pass in json_dumps_report["tb_failed_trial"]
            ]
        )

        
        # debug
        print("### exception and tb trials:", json_dumps_report["exception_trial"], json_dumps_report["tb_failed_trial"])

        print("### Result iter times: ", self._iteration_time)
        print("\t", f"{count_excep_pass}/5 Exception pass")
        print("\t", f"{count_tb_pass}/5 TB pass")
