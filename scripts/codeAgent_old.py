from .constants import LLMAgentStatus, ModuleNamePrefix, Template
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_core.messages.base import BaseMessage
import re, os, subprocess
from langchain_core.messages import HumanMessage
from .lazy import modulePathToModuleWorkPath, getMainLLMFilenamePath, readFileContent
import os
from langchain.chat_models import init_chat_model
from langchain_ollama import OllamaEmbeddings
from langchain_milvus import Milvus
from langchain_core.tools import tool

class LLMCodeAgent:
    def __init__(self, modulePath: str, milvus_URI="http://localhost:19530"):
        self._modulePath = modulePath
        self._moduleWorkPath = modulePathToModuleWorkPath(self._modulePath)
        self._modulePathLint = os.path.join(self._moduleWorkPath, "lint")
        self._curLLMCode = ""
        self._workFolderName = Template.TEMPORARYLLMWORKFOLDERNAME.value
        self._chat_history = []

        # init history

        # description
        description = readFileContent(os.path.join(self._modulePath, Template.DESCRIPTIONFILENAME.value))
        
        # code
        code = readFileContent(getMainLLMFilenamePath(self._moduleWorkPath))

        self._chat_history.extend([HumanMessage(content=description), code])

        # 
        self._llm = init_chat_model("llama3-70b-8192", model_provider="groq")
        self._embeddings = OllamaEmbeddings(model="llama3", base_url="http://127.0.0.1:32320", )

        self._vector_store = Milvus(embedding_function=self._embeddings,connection_args={"uri": milvus_URI, "token": "root:Milvus", "db_name": "milvus_demo"},index_params={"index_type": "FLAT", "metric_type": "L2"},
            consistency_level="Strong",
            drop_old=False,  # set to True if seeking to drop the collection with that name if it exists
            )
        self_retriever = self._vector_store.as_retriever()
    
    @tool(response_format="content_and_artifact")
    def retrieve(self, query: str):
        """Retrieve information related to a query."""
        retrieved_docs = self._vector_store.similarity_search(query, k=2)
        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\n" f"Content: {doc.page_content}")
            for doc in retrieved_docs
        )
        return serialized, retrieved_docs
    
    def __iter__(self):
        self.a = 1
        self.status = "error"
        return self

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
        for i in range(len(founds)) if not firstOnly else [0]:
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

    def cur_res(self):
        # current llm code

        # cache current
        curLLMCodeFilePath = getMainLLMFilenamePath(self._moduleWorkPath)
        curLLMCodeFile = open(curLLMCodeFilePath, "r+")
        self._curLLMCode = curLLMCodeFile.read()
        curLLMCodeFile.close()

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

        if isinstance(firstWarning, dict):
            return {"status": LLMAgentStatus.ERROR.value, "content": firstWarning}
        # if type(firstWarning) == 'dict'

        return {"status": "success", "content": ""}

    @property
    def rag_chain(self):
        

    def invoke(self, user_input:str):
        ai_msg = rag_chain.invoke({"input": user_input, "chat_history": self._chat_history})
        self._chat_history.extend([HumanMessage(content=user_input), ai_msg["answer"]])
        print(ai_msg["answer"])
        return ''

    def __next__(self):
        confirm = input(f"Next? (y/n) ")
        if confirm == "n" or confirm == "N":
            print("End Agent")
            raise StopIteration

        # {status: 'error' | 'success', content: str}
        currentRes = self.cur_res()

        # prompt
        prompt = """The Verilator compiler raises a {exceptionType}, called {exceptionTitle}, for this module. The content of the {exceptionType} is \"{exceptionContent}\".
Here is the related in-line content with the {exceptionType}:

{logContent}
""".format(
            **currentRes["content"]
        )
        print(f"what and why? {prompt}")

        # query
        print(self.invoke(prompt))


        x = self.a
        self.a += 1
        return (x, self.status)

    def __call__(self):
        print("Start agent")
        myiter = iter(self)
        currentStatus = None
        for x in myiter:
            currentStatus = x
            print("iter status", currentStatus[1], ". iter times: ", currentStatus[0])

        print("last status", currentStatus[1], ". iter times: ", currentStatus[0])


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
                # moduleWorkListLinting,
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
