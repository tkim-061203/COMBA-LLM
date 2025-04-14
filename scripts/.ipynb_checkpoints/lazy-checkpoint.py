from constants import Template
import os, re


def modulePathToModuleWorkPath(
    path: str, workFolderName=Template.TEMPORARYLLMWORKFOLDERNAME.value
):

    return re.sub(
        rf"^{Template.MODULEFOLDER.value}",
        workFolderName,
        path,
    )


def getTemplateFilenamePath(path: str, extension="v", fname: str = None):
    filename = os.path.basename(path) if fname == None else fname

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
