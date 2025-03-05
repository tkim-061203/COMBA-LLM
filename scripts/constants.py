from enum import Enum

class Template(Enum):
    MODULEFOLDER="modules"
    TEMPLATEFOLDER="template"
    DESCRIPTIONFILENAME="design_description.txt"
    TBFILENAME="tb.txt"
    MODULEFILENAME="module.txt"
    TEMPORARYWORKFOLDERNAME=".work"
    CATEGORYFILENAME = "category"
    TEMPORARYLLMWORKFOLDERNAME=".llmwork"
    LLMCACHEFOLDER='.llmcache'

class Commands(Enum):
    RUNVERIFIED = 'runverified'
    CREATEMODULE = 'createmodule'
    MAKEVERIFIED = 'makeverified'
    GENERATE = 'generate'
    RUNWORK = 'run'
    MAKEWORK = 'makework'

class ModuleNamePrefix(Enum):
    LLM = 'llm_'
    VERIFIED = 'verified_'