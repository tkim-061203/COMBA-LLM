from .constants import Template
import os, re


def modulePathToModuleWorkPath(path: str):

    return re.sub(
        rf"^{Template.MODULEFOLDER.value}",
        Template.TEMPORARYLLMWORKFOLDERNAME.value,
        path,
    )


def getMainLLMFilenamePath(path: str, extension="v"):
    filename = os.path.basename(path)

    return os.path.join(path, f"{filename}.{extension}")


def readFileContent(filePath: str, mode="r+"):
    file = open(filePath, mode)
    fileContent: str = file.read()
    file.close()
    return fileContent


def saveFileContent(filePath: str, content: str, mode="w+"):
    file = open(filePath, mode)
    file.write(content)
    file.close()
