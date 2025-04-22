from dotenv import load_dotenv
load_dotenv()

import argparse, os, shutil, typing, glob
import datetime
from scripts.langchain_groq_util import generate as llmGenerate
from scripts.utils import md_code_extract, generateWorkFolderArgument, generateMEICWorkFolderArgument
from scripts.constants import Commands, ModuleNamePrefix, Template
from scripts.rag import ragCreate
from scripts.codeAgent import LLMCodeAgent
from scripts.MEICCodeAgent import MEICLLMCodeAgent

from tqdm import tqdm

parser = argparse.ArgumentParser(
    prog="LLM Prompt Template",
    description="What the program does",
    epilog="Text at the bottom of help",
)

subparsers = parser.add_subparsers(dest="command")
parser_createmodule = subparsers.add_parser(
    Commands.CREATEMODULE.value, help="Create new module project"
)

#
parser_runWork = subparsers.add_parser(
    Commands.RUNWORK.value, help="Run projects with verilog module"
)
parser_runWork.add_argument("modules", nargs="*")
parser_runWork.add_argument(
    "--llm", action="store_true", help="Run LLM Working Directory"
)
parser_runWork.add_argument(
    "--descriptiontype", default='xml', help="Description type", nargs='?', type=str
)
parser_runWork.add_argument(
    "--nodebug", action="store_true", help="No Debug with yes/no input"
)

#
parser_runMEICWork = subparsers.add_parser(
    Commands.RUNMEIC.value, help="Run projects with verilog module of MEIC"
)
parser_runMEICWork.add_argument("modules", nargs="*")
parser_runMEICWork.add_argument(
    "--llm", action="store_true", help="Run LLM Working Directory"
)
parser_runMEICWork.add_argument(
    "--descriptiontype", default='xml', help="Description type", nargs='?', type=str
)
parser_runMEICWork.add_argument(
    "--nodebug", action="store_true", help="No Debug with yes/no input"
)

#
parser_makeWork = subparsers.add_parser(
    Commands.MAKEWORK.value, help="Make projects with verilog module"
)
parser_makeWork.add_argument("modules", nargs="*")
parser_makeWork.add_argument(
    "--llm", action="store_true", help="Make LLM Working Directory"
)

parser_generate = subparsers.add_parser(
    Commands.GENERATE.value, help="Generate Verilog module"
)
parser_generate.add_argument("modules", nargs="*")

parser_rag = subparsers.add_parser(Commands.RAG.value, help="RAG Interface")
parser_rag.add_argument("ragfile")

def createmodule():
    modulename = input("Module name: ")
    newModulePath = os.path.join(Template.MODULEFOLDER.value, modulename)

    if not os.path.isdir(newModulePath):
        os.mkdir(newModulePath)

    #
    descriptionTemplateFIle = open(
        f"{Template.TEMPLATEFOLDER.value}/{Template.DESCRIPTIONFILENAME.value}", "r"
    )
    formattedDescriptionContent = descriptionTemplateFIle.read()
    descriptionTemplateFIle.close()

    #
    newDescriptonPath = os.path.normpath(
        os.path.join(newModulePath, Template.DESCRIPTIONFILENAME.value)
    )
    if not os.path.isfile(newDescriptonPath):
        newDescriptionFile = open(newDescriptonPath, "w")
        newDescriptionFile.write(formattedDescriptionContent)
        newDescriptionFile.close()
    else:
        print("\t- No override exist Description!")

    #
    newDescriptonXMLPath = os.path.normpath(
        os.path.join(newModulePath, Template.DESCRIPTIONXMLFILENAME.value)
    )
    if not os.path.isfile(newDescriptonXMLPath):
        with open(
        f"{Template.TEMPLATEFOLDER.value}/{Template.DESCRIPTIONXMLFILENAME.value}", "r"
        ) as descriptionXMLTemplateFIle:
            formattedDescriptionXMLContent = descriptionXMLTemplateFIle.read()

        with open(newDescriptonXMLPath, "w") as newDescriptionXMLFile:
            newDescriptionXMLFile.write(formattedDescriptionXMLContent)
    else:
        print("\t- No override exist XML Description!")

    #
    tbTemplateFIle = open(
        f"{Template.TEMPLATEFOLDER.value}/{Template.TBFILENAME.value}", "r"
    )
    formattedTBContent = tbTemplateFIle.read()
    tbTemplateFIle.close()

    #
    newTBPath = os.path.join(
        newModulePath, Template.TBFILENAME.value.replace(".txt", ".cpp")
    )
    if not os.path.isfile(newTBPath):
        newTBFile = open(newTBPath, "w")
        newTBFile.write(formattedTBContent.format(modulename=modulename))
        newTBFile.close()
    else:
        print("\t- No override exist Testbench!")

    #
    moduleTemplateFIle = open(
        f"{Template.TEMPLATEFOLDER.value}/{Template.MODULEFILENAME.value}", "r"
    )
    formattedModuleContent = moduleTemplateFIle.read()
    moduleTemplateFIle.close()

    #
    newModuleContentPath = os.path.join(
        newModulePath, f"{ModuleNamePrefix.VERIFIED.value}{modulename}.v"
    )
    if not os.path.isfile(newModuleContentPath):
        newModuleFile = open(newModuleContentPath, "w+")
        newModuleFile.write(formattedModuleContent.format(modulename=modulename))
        newModuleFile.close()
    else:
        print("\t- No override exist Module Verilog!")

    newLLMModuleContentPath = os.path.join(
        newModulePath, f"{ModuleNamePrefix.LLM.value}{modulename}.v"
    )
    if not os.path.isfile(newLLMModuleContentPath):
        open(newLLMModuleContentPath, "w+").close()
    else:
        print("\t- No override exist LLM-Generated Module Verilog!")

    # category
    newCategoryPath = os.path.join(newModulePath, Template.CATEGORYFILENAME.value)
    if not os.path.isfile(newCategoryPath):
        categoryName = input("Categories: ")
        categoryFile = open(newCategoryPath, "w")
        categoryFile.write(categoryName)
        categoryFile.close()

    else:
        print("\t- No override exist category!")

    print(f"New module folder is created at {newModulePath}")


def makeWorkingFolder(
    modulePaths: typing.List[str],
    workFolderName=Template.TEMPORARYWORKFOLDERNAME.value,
    moduleNamePrefix=ModuleNamePrefix.VERIFIED.value,
):

    # if os.path.isdir(workFolderName):
    #     shutil.rmtree(workFolderName)
    if not os.path.isdir(workFolderName):
        os.mkdir(workFolderName)

    for modulePath in modulePaths:
        moduleNormPath = os.path.normpath(modulePath)
        moduleName = os.path.basename(moduleNormPath)

        moduleNameWorkPath = os.path.join(workFolderName, moduleName)

        # if not os.path.isdir(moduleNameWorkPath):
        #     os.mkdir(moduleNameWorkPath)
        # elif input(f'Delete exist work dir "{moduleNameWorkPath}"? (y/n) ') == "y":
        if os.path.isdir(moduleNameWorkPath):
            shutil.rmtree(moduleNameWorkPath)
        os.mkdir(moduleNameWorkPath)

        tbModuleFileName = Template.TBFILENAME.value.replace(".txt", ".cpp")
        tbModulePath = os.path.join(modulePath, tbModuleFileName)
        tbWorkPath = os.path.join(moduleNameWorkPath, tbModuleFileName)
        os.link(tbModulePath, tbWorkPath)

        moduleSourcePath = os.path.join(modulePath, f"{moduleNamePrefix}{moduleName}.v")
        moduleWorkPath = os.path.join(workFolderName, moduleName, f"{moduleName}.v")
        os.link(moduleSourcePath, moduleWorkPath)

def makeMEICWorkingFolder(
    modulePaths: typing.List[str],
    workFolderName=Template.TEMPORARYWORKFOLDERNAME.value,
    moduleNamePrefix=ModuleNamePrefix.LLM.value,
    referenceModuleDir=Template.MODULEFOLDER.value,
):

    if not os.path.isdir(workFolderName):
        os.mkdir(workFolderName)

    for modulePath in modulePaths:
        moduleNormPath = os.path.normpath(modulePath)
        moduleName = os.path.basename(moduleNormPath)

        moduleNameWorkPath = os.path.join(workFolderName, moduleName)
        referenceModuleNameWorkPath = os.path.join(referenceModuleDir, moduleName)
        

        if os.path.isdir(moduleNameWorkPath):
            shutil.rmtree(moduleNameWorkPath)
        os.mkdir(moduleNameWorkPath)

        tbModuleFileName = Template.TBFILENAME.value.replace(".txt", ".cpp")
        tbModulePath = os.path.join(referenceModuleNameWorkPath, tbModuleFileName)
        tbWorkPath = os.path.join(moduleNameWorkPath, tbModuleFileName)
        os.link(tbModulePath, tbWorkPath)

        moduleSourcePath = os.path.join(modulePath, f"{moduleNamePrefix}{moduleName}.v")
        moduleWorkPath = os.path.join(workFolderName, moduleName, f"{moduleName}.v")

        if not os.path.isfile(moduleSourcePath):
            open(moduleSourcePath, 'w+').close()

        os.link(moduleSourcePath, moduleWorkPath)


def generate(modulePaths: list):
    moduleNormPaths = [os.path.normpath(modulePath) for modulePath in modulePaths]
    # moduleNormPaths = [re.sub(rf"^{Template.MODULEFOLDER.value}", Template.TEMPORARYWORKFOLDERNAME.value, os.path.normpath(modulePath)) for modulePath in modulePaths]

    for moduleNormPath in moduleNormPaths:
        moduleName = os.path.basename(moduleNormPath)
        # descriptionContent = open()
        descriptionFile = open(
            os.path.join(moduleNormPath, Template.DESCRIPTIONFILENAME.value), "r"
        )
        descritionContent = descriptionFile.read()
        descriptionFile.close()

        print("Generate content for ", moduleNormPath)
        llmtext = llmGenerate(descritionContent)
        lllmcode = md_code_extract(llmtext)

        # write and cache llm chat
        cacheFolder = os.path.join(moduleNormPath, Template.LLMCACHEFOLDER.value)
        if not os.path.exists(cacheFolder):
            os.mkdir(cacheFolder)
        cacheFile = open(
            os.path.join(cacheFolder, f"{datetime.datetime.now().isoformat()}.v"), "w+"
        )
        cacheFile.write(lllmcode)
        cacheFile.close()

        llmCodeFile = open(
            os.path.join(moduleNormPath, f"{ModuleNamePrefix.LLM.value}{moduleName}.v"),
            "w+",
        )
        llmCodeFile.write(lllmcode)
        llmCodeFile.close()


def runFlow(
    modulePaths: typing.List[str],
    workFolderName=Template.TEMPORARYWORKFOLDERNAME.value,
    moduleNamePrefix=ModuleNamePrefix.VERIFIED.value,
    desciptionType='txt',
    nodebug=False,
    llm_model="gpt-4o-mini-2024-07-18",
):
    moduleGlobPaths = []
    for modulePath in modulePaths:
        moduleGlobPaths += glob.glob(modulePath)

    moduleNormPaths = [os.path.normpath(modulePath) for modulePath in moduleGlobPaths]
    
    defaultInputDirYAll = {
            'yall': True,
            'nall': False
        }
    customInputDirective = {
        'syntax_compile': {
            'yall': False,
            'nall': True
        },
        'syntax_compile_route': defaultInputDirYAll,
        'tb_simulation_route': defaultInputDirYAll,
        'chatbot_code_generator': defaultInputDirYAll,
        "__next__": defaultInputDirYAll
    } if nodebug else {}

    moduletqdm = tqdm(total=len(moduleGlobPaths), desc='Module')

    #
    # log file
    # create file if not exist
    if not os.path.isfile('reports/log/log.txt'):
        open('reports/log/log.txt', 'w+').close()
    # clear file
    with open('reports/log/log.txt', 'w+') as file:
        file.write('')

    for moduleNormPath in moduleNormPaths:

        moduletqdm.update(1)
        moduleName = os.path.basename(moduleNormPath)

        #
        with open('reports/log/log.txt', 'a') as file:
            print(f"### Log for module \"{moduleName}\"", sep='\n', file=file)
        
        makeWorkingFolder([moduleNormPath], workFolderName, moduleNamePrefix)

        #
        print("flow here", moduleNormPath, moduleName)
        llmCodeAgent = LLMCodeAgent(
            modulePath=moduleNormPath,
            workFolderName=workFolderName,
            llm_model=llm_model,
            model_provider="openai",
            temperature=0,
            descriptionType=desciptionType,
            customInputDirective=customInputDirective
        )
        llmCodeAgent()
    
    #
    # history log
    # mkdir if not exist
    if not os.path.isdir('reports/log/.history'):
        os.mkdir('reports/log/.history')
    
    history_tag = datetime.datetime.now().isoformat()
    shutil.copyfile('reports/log/log.txt', f'reports/log/.history/log_{llm_model}_{history_tag}.txt')

def runMeicFlow(
    modulePaths: typing.List[str],
    workFolderName=Template.MEIC_TEMPORARYWORKFOLDERNAME.value,
    moduleNamePrefix=ModuleNamePrefix.LLM.value,
    desciptionType='txt',
    nodebug=False,
    llm_model="gpt-4o-mini-2024-07-18",
):
    moduleGlobPaths = []
    for modulePath in modulePaths:
        moduleGlobPaths += glob.glob(modulePath)

    moduleNormPaths = [os.path.normpath(modulePath) for modulePath in moduleGlobPaths]

    defaultInputDirYAll = {
            'yall': True,
            'nall': False
        }
    customInputDirective = {
        'syntax_compile': {
            'yall': False,
            'nall': True
        },
        'syntax_compile_route': defaultInputDirYAll,
        'tb_simulation_route': defaultInputDirYAll,
        'chatbot_code_generator': defaultInputDirYAll,
        "__next__": defaultInputDirYAll
    } if nodebug else {}

    moduletqdm = tqdm(total=len(moduleGlobPaths), desc='Module')

    #
    # log file
    # create file if not exist
    if not os.path.isfile('reports/log/log_meic.txt'):
        open('reports/log/log_meic.txt', 'w+').close()
    # clear file
    with open('reports/log/log_meic.txt', 'w+') as file:
        file.write('')

    for moduleNormPath in moduleNormPaths:

        moduletqdm.update(1)
        moduleName = os.path.basename(moduleNormPath)

        #
        # check if module is available in module path
        if not os.path.isdir(os.path.join(Template.MODULEFOLDER.value, moduleName)):
            print(f'MEIC module {moduleName} not found in refence module path.')
            continue

        #
        with open('reports/log/log.txt', 'a') as file:
            print(f"### Log for module \"{moduleName}\"", sep='\n', file=file)
        
        makeMEICWorkingFolder([moduleNormPath], workFolderName, moduleNamePrefix)

        #
        print("flow here", moduleNormPath, moduleName)
        llmCodeAgent = MEICLLMCodeAgent(
            modulePath=moduleNormPath,
            workFolderName=workFolderName,
            llm_model=llm_model,
            model_provider="openai",
            temperature=0,
            descriptionType=desciptionType,
            customInputDirective=customInputDirective
        )
        llmCodeAgent()
    
    # #
    # history log
    # mkdir if not exist
    if not os.path.isdir('reports/log/.history'):
        os.mkdir('reports/log/.history')
    
    history_tag = datetime.datetime.now().isoformat()
    shutil.copyfile('reports/log/log_meic.txt', f'reports/log/.history/log_meic_{llm_model}_{history_tag}.txt')

if __name__ == "__main__":
    args = parser.parse_args()
    match args.command:
        case Commands.CREATEMODULE.value:
            createmodule()
        case Commands.RUNWORK.value:
            runFlow(args.modules, *(generateWorkFolderArgument(args.llm) + (args.descriptiontype, args.nodebug)))
        case Commands.RUNMEIC.value:
            runMeicFlow(args.modules, desciptionType=args.descriptiontype, nodebug=args.nodebug)
        case Commands.MAKEWORK.value:
            makeWorkingFolder(args.modules, *generateWorkFolderArgument(args.llm))
        case Commands.GENERATE.value:
            generate(args.modules)
        case Commands.RAG.value:
            ragCreate(args.ragfile)

    print("your args", args)
