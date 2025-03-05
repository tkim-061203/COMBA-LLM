import argparse, os, shutil, subprocess, typing, re
import datetime
from scripts.langchain_groq_util import generate as llmGenerate
from scripts.utils import md_code_extract, generateWorkFolderArgument
from scripts.constants import Commands, ModuleNamePrefix, Template



parser = argparse.ArgumentParser(
                    prog='LLM Prompt Template',
                    description='What the program does',
                    epilog='Text at the bottom of help')

subparsers = parser.add_subparsers(dest="command")
parser_createmodule = subparsers.add_parser(Commands.CREATEMODULE.value, help='Create new module project')

parser_runWork = subparsers.add_parser(Commands.RUNWORK.value, help='Run projects with verilog module')
parser_runWork.add_argument('modules',nargs="*")
parser_runWork.add_argument('--llm', action='store_true', help='Run LLM Working Directory')

parser_makeWork = subparsers.add_parser(Commands.MAKEWORK.value, help='Make projects with verilog module')
parser_makeWork.add_argument('modules',nargs="*")
parser_makeWork.add_argument('--llm', action='store_true', help='Make LLM Working Directory')

parser_generate = subparsers.add_parser(Commands.GENERATE.value, help='Generate Verilog module')
parser_generate.add_argument('modules',nargs="*")

args = parser.parse_args()

def createmodule():
    modulename = input("Module name: ")
    newModulePath = os.path.join(Template.MODULEFOLDER.value, modulename)

    if not os.path.isdir(newModulePath):
        os.mkdir(newModulePath)
    
    #
    descriptionTemplateFIle = open(f"{Template.TEMPLATEFOLDER.value}/{Template.DESCRIPTIONFILENAME.value}", "r")
    formattedDescriptionContent = descriptionTemplateFIle.read()
    descriptionTemplateFIle.close()

    #
    newDescriptonPath = os.path.normpath(os.path.join(newModulePath, Template.DESCRIPTIONFILENAME.value))
    if not os.path.isfile(newDescriptonPath):
        newDescriptionFile = open(newDescriptonPath, "w")
        newDescriptionFile.write(formattedDescriptionContent)
        newDescriptionFile.close()
    else:
        print("\t- No override exist Description!")

    #
    tbTemplateFIle = open(f"{Template.TEMPLATEFOLDER.value}/{Template.TBFILENAME.value}", "r")
    formattedTBContent = tbTemplateFIle.read()
    tbTemplateFIle.close()

    #
    newTBPath = os.path.join(newModulePath, Template.TBFILENAME.value.replace(".txt", ".cpp"))
    if not os.path.isfile(newTBPath):
        newTBFile = open(newTBPath, "w")
        newTBFile.write(formattedTBContent.format(modulename=modulename))
        newTBFile.close()
    else:
        print("\t- No override exist Testbench!")

    #
    moduleTemplateFIle = open(f"{Template.TEMPLATEFOLDER.value}/{Template.MODULEFILENAME.value}", "r")
    formattedModuleContent = moduleTemplateFIle.read()
    moduleTemplateFIle.close()

    #
    newModuleContentPath = os.path.join(newModulePath, f"{ModuleNamePrefix.VERIFIED.value}{modulename}.v")
    if not os.path.isfile(newModuleContentPath):
        newModuleFile = open(newModuleContentPath, "w+")
        newModuleFile.write(formattedModuleContent.format(modulename=modulename))
        newModuleFile.close()
    else:
        print("\t- No override exist Module Verilog!")
    
    newLLMModuleContentPath = os.path.join(newModulePath, f"{ModuleNamePrefix.LLM.value}{modulename}.v")
    if not os.path.isfile(newLLMModuleContentPath):
        newLLMModuleFile = open(newLLMModuleContentPath, "w+").close()
    else:
        print("\t- No override exist LLM-Generated Module Verilog!")
    
    newCategoryPath = os.path.join(newModulePath, Template.CATEGORYFILENAME.value)
    if not os.path.isfile(newCategoryPath):
        open(newCategoryPath,'w').close()

    print(f"New module folder is created at {newModulePath}")

def runLinting(modulePaths:typing.List[str], workFolderName=Template.TEMPORARYWORKFOLDERNAME.value, moduleNamePrefix=ModuleNamePrefix.VERIFIED.value):
    # makeverified(modules)
    moduleNormPaths = [os.path.normpath(modulePath) for modulePath in modulePaths]
    
    generateYN = {
        'yesall': False,
        'noall': False
    }
    for moduleNormPath in moduleNormPaths:
        moduleName = os.path.basename(moduleNormPath)
        moduleNameWorkPath = os.path.join(workFolderName,moduleName)
        if not os.path.isdir(moduleNameWorkPath):
            makeWorkingFolder([moduleNormPath], workFolderName, moduleNamePrefix)
        
        moduleSourcePath = os.path.join(moduleNormPath, f"{moduleNamePrefix}{moduleName}.v")
        if workFolderName == Template.TEMPORARYLLMWORKFOLDERNAME.value and moduleNamePrefix == ModuleNamePrefix.LLM.value:
            moduleSourceFile = open(moduleSourcePath, 'w+')
            moduleSourceFileContent = moduleSourceFile.read()
            moduleSourceFile.close()
            if not moduleSourceFileContent:
                while not generateYN['noall']:
                    choice = input('Empty LLM Verilog content. Do you want to generate LLM code? (y: yes, Y: yes all, n: no, N: no all): ') if not generateYN['yesall'] else 'y'
                    if re.compile('^([yYnN])$').match(choice):
                        # print('Your choice is correct', choice)
                        match choice:
                            case 'Y':
                                generateYN['yesall'] = True
                                continue
                            case 'N':
                                generateYN['noall'] = True
                                continue
                            case 'y':
                                generate([moduleNormPath])
                                break
                            case 'n':
                                break
                    else:
                        print('Your choice is incorrect', choice)

            
            
    moduleWorkList = ' '.join([re.sub(fr'^{Template.MODULEFOLDER.value}', workFolderName, moduleNormPath) for moduleNormPath in moduleNormPaths])
    
    result = subprocess.run(['make', moduleWorkList, f'WORKDIR={workFolderName}'], stdout=subprocess.PIPE)
    print('Return code:', result.returncode, '\nmess:', result.stdout.decode('utf-8'))

def makeWorkingFolder(modulePaths:typing.List[str], workFolderName=Template.TEMPORARYWORKFOLDERNAME.value, moduleNamePrefix=ModuleNamePrefix.VERIFIED.value):
    if os.path.isdir(workFolderName):
        shutil.rmtree(workFolderName)
    
    os.mkdir(workFolderName)
    for modulePath in modulePaths:
        moduleNormPath = os.path.normpath(modulePath)
        moduleName = os.path.basename(moduleNormPath)

        moduleNameWorkPath = os.path.join(workFolderName,moduleName)

        if not os.path.isdir(moduleNameWorkPath):
            os.mkdir(moduleNameWorkPath)

        tbModuleFileName = Template.TBFILENAME.value.replace(".txt", ".cpp")
        tbModulePath = os.path.join(modulePath, tbModuleFileName)
        tbWorkPath = os.path.join(moduleNameWorkPath, tbModuleFileName)
        os.link(tbModulePath, tbWorkPath)

        moduleSourcePath = os.path.join(modulePath, f"{moduleNamePrefix}{moduleName}.v")
        moduleWorkPath = os.path.join(workFolderName, moduleName, f"{moduleName}.v")
        os.link(moduleSourcePath, moduleWorkPath)



def generate(modulePaths:list):
    moduleNormPaths = [os.path.normpath(modulePath) for modulePath in modulePaths]
    # moduleNormPaths = [re.sub(rf"^{Template.MODULEFOLDER.value}", Template.TEMPORARYWORKFOLDERNAME.value, os.path.normpath(modulePath)) for modulePath in modulePaths]

    for moduleNormPath in moduleNormPaths:
        moduleName = os.path.basename(moduleNormPath)
        # descriptionContent = open()
        descriptionFile = open(os.path.join(moduleNormPath, Template.DESCRIPTIONFILENAME.value), 'r')
        descritionContent = descriptionFile.read()
        descriptionFile.close()
        
        print('Generate content for ', moduleNormPath)
        llmtext = llmGenerate(descritionContent)
        lllmcode = md_code_extract(llmtext)

        # write and cache llm chat
        cacheFolder = os.path.join(moduleNormPath, Template.LLMCACHEFOLDER.value)
        if not os.path.exists(cacheFolder):
            os.mkdir(cacheFolder)
        cacheFile = open(os.path.join(cacheFolder, f"{datetime.datetime.now().isoformat()}.v"), 'w+')
        cacheFile.write(lllmcode)
        cacheFile.close()

        llmCodeFile = open(os.path.join(moduleNormPath, f"{ModuleNamePrefix.LLM.value}{moduleName}.v"), 'w+')
        llmCodeFile.write(lllmcode)
        llmCodeFile.close()

match args.command:
    case Commands.CREATEMODULE.value:
        createmodule()
    # case Commands.RUNVERIFIED.value:
    #     runLinting(args.modules)
    # case Commands.MAKEVERIFIED.value:
    #     makeWorkingFolder(args.modules)
    case Commands.RUNWORK.value:
        runLinting(args.modules, *generateWorkFolderArgument(args.llm))
    case Commands.MAKEWORK.value:
        makeWorkingFolder(args.modules, *generateWorkFolderArgument(args.llm))
    case Commands.GENERATE.value:
        generate(args.modules)

print("your args", args)

