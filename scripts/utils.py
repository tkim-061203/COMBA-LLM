import re
from .constants import Template, ModuleNamePrefix


def md_code_extract(text: str):
    found = re.search(r"^```(\w*)\n(?P<code>(.|\n)*)```", text, re.MULTILINE)
    return found.groupdict()["code"]


def generateWorkFolderArgument(llm=False):
    if llm:
        return (Template.TEMPORARYLLMWORKFOLDERNAME.value, ModuleNamePrefix.LLM.value)
    return (Template.TEMPORARYWORKFOLDERNAME.value, ModuleNamePrefix.VERIFIED.value)

def generateMEICWorkFolderArgument(llm=False):
    if llm:
        return (Template.MEIC_TEMPORARYLLMWORKFOLDERNAME.value, )
    return (Template.MEIC_TEMPORARYWORKFOLDERNAME.value, )
