from enum import Enum
from typing_extensions import TypedDict


class Template(Enum):
    MODULEFOLDER = "modules"
    TEMPLATEFOLDER = "template"
    DESCRIPTIONFILENAME = "design_description.txt"
    DESCRIPTIONXMLFILENAME = "design_description.xml"
    TBFILENAME = "tb.txt"
    MODULEFILENAME = "module.txt"
    TEMPORARYWORKFOLDERNAME = ".work"
    CATEGORYFILENAME = "category"
    TEMPORARYLLMWORKFOLDERNAME = ".llmwork"
    LLMCACHEFOLDER = ".llmcache"

    #
    # MEIC
    MEIC_TEMPORARYLLMWORKFOLDERNAME = ".meicllmwork"
    MEIC_TEMPORARYWORKFOLDERNAME = ".meicwork"
    MEIC_MODULEFOLDER = "MEIC/ErrorSet"

class Commands(Enum):
    RUNVERIFIED = "runverified"
    CREATEMODULE = "createmodule"
    MAKEVERIFIED = "makeverified"
    GENERATE = "generate"
    RUNWORK = "run"
    RUNMEIC = "runmeic"
    MAKEWORK = "makework"
    RAG = "rag"


class ModuleNamePrefix(Enum):
    LLM = "llm_"
    VERIFIED = "verified_"


class WarningExtraction(TypedDict):
    warningTitle: str
    fileName: str
    lineNumber: str
    posNumber: str
    warningContent: str


class LLMAgentStatus(Enum):
    INIT = 0
    SUCCESS = 1
    ERROR = 2
