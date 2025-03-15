from .constants import LLMAgentStatus, ModuleNamePrefix, Template
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_core.messages.base import BaseMessage
import re, os, subprocess
from langchain_core.messages import HumanMessage


class CodeAgent:
    def __init__(
        self,
        inputModulePath: str,
        model="llama3-70b-8192",
        humanRole="user",
        assistantRole="assistant",
    ):
        self._llm = ChatGroq(
            model=model,
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            # other params...
        )
        self._inputModulePath = inputModulePath
        self._attempt = 5

        self._history = []
        initPrompts = CodeAgent.initPromptFromFile(inputModulePath)
        self._history.extend(initPrompts)

    @property
    def prompt_template(self):
        return ChatPromptTemplate(
            [
                ("system", self.system_prompt),
                # Means the template will receive an optional list of messages under
                # the "conversation" key
                ("placeholder", "{conversation}"),
                # Equivalently:
                # MessagesPlaceholder(variable_name="conversation", optional=True)
                ("user", "{user_input}"),
            ]
        )

    def checker(self, code: str):
        workFolderName = Template.TEMPORARYLLMWORKFOLDERNAME.value

        result = subprocess.run(
            [
                "make",
                moduleWorkListLinting,
                f"WORKDIR={workFolderName}",
            ],
            stdout=subprocess.PIPE,
        )
        print(
            "Return code:", result.returncode, "\nmess:", result.stdout.decode("utf-8")
        )
        log = result.stdout.decode("utf-8")
        return (LLMAgentStatus.SUCCESS.value, code)

    @property
    def status(self):
        latestCode = self.latestCode
        if len(latestCode):
            return self.checker(latestCode)
        return (LLMAgentStatus.INIT.value, "")

    @property
    def system_prompt(self):
        return """Please act as a professional verilog designer.
You will provide Verilog Code to A Verilog Compiler, called Verilator.
Please provide single module or module compositions that can be contructed in a Verilog file."""

    @property
    def chain(self):
        return self.prompt_template | self._llm

    @property
    def latestCode(self):
        return self._history[-1] if isinstance(self._history[-1], str) else ""

    def __call__(self):
        # latestCode:str =
        pass

    @staticmethod
    def defaultChain():
        model = ChatGroq(
            model="llama3-70b-8192",
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            # other params...
        )

        defaultTemplate = ChatPromptTemplate(
            [
                (
                    "system",
                    """Please act as a professional verilog designer.
Please provide single module or module compositions that can be contruct in a Verilog file.""",
                ),
                # Means the template will receive an optional list of messages under
                # the "conversation" key
                ("placeholder", "{conversation}"),
                # Equivalently:
                # MessagesPlaceholder(variable_name="conversation", optional=True)
                ("user", "{user_input}"),
            ]
        )

        prompt = defaultTemplate

        chain = prompt | model
        return chain

    @staticmethod
    def generate(
        input: dict,
        chain: RunnableSerializable[dict, BaseMessage] = None,
        codeOnly=False,
    ):
        if chain == None:
            chain = CodeAgent.defaultChain()

        baseMessage = chain.invoke(input)

        if codeOnly:
            return CodeAgent.md_code_extract(baseMessage.content)

        return baseMessage

    @staticmethod
    def initPromptFromFile(modulePath: str):
        moduleName = os.path.basename(modulePath)
        fileCodeWrapper = open(
            os.path.join(modulePath, f"{ModuleNamePrefix.LLM.value}{moduleName}.v"), "r"
        )
        fileCode = fileCodeWrapper.read()
        fileCodeWrapper.close()

        designDescriptionWrapper = open(
            os.path.join(modulePath, Template.DESCRIPTIONFILENAME.value), "r"
        )
        designDescriptionContent = designDescriptionWrapper.read()
        designDescriptionWrapper.close()

        return [HumanMessage(content=designDescriptionContent), fileCode]

    @staticmethod
    def md_code_extract(text: str) -> str:
        found = re.search(r"^```(\w*)\n(?P<code>(.|\n)*)```", text, re.MULTILINE)
        return (
            found.groupdict()["code"]
            if isinstance(found.groupdict()["code"], str)
            else ""
        )
