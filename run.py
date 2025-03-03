import argparse, os, shutil, subprocess, typing, re

modulefolder="modules"
templatefolder="template"
descriptionFileName="design_description.txt"
tbFileName="tb.txt"
moduleFileName="module.txt"
temporaryWorkFolderName=".work"
categoryFileName = "category"

parser = argparse.ArgumentParser(
                    prog='DESLAPP Template',
                    description='What the program does',
                    epilog='Text at the bottom of help')
# parser.add_argument('command', choices=["createmodule"])           # positional argument
# parser.add_argument('-c', '--count')      # option that takes a value
# parser.add_argument('-v', '--verbose',
#                     action='store_true')  # on/off flag
subparsers = parser.add_subparsers(dest="command")
parser_createmodule = subparsers.add_parser('createmodule', help='Create new module project')

parser_runverified = subparsers.add_parser('runverified', help='Run projects with verified verilog module')
parser_runverified.add_argument('modules',nargs="*")

parser_makeverified = subparsers.add_parser('makeverified', help='Create work folder for projects with verified verilog module')
parser_makeverified.add_argument('modules',nargs="*")

args = parser.parse_args()

def createmodule():
    modulename = input("Module name: ")
    newModulePath = os.path.join(modulefolder, modulename)

    if not os.path.isdir(newModulePath):
        os.mkdir(newModulePath)
    
    #
    descriptionTemplateFIle = open(f"{templatefolder}/{descriptionFileName}", "r")
    formattedDescriptionContent = descriptionTemplateFIle.read()
    descriptionTemplateFIle.close()

    #
    newDescriptonPath = os.path.normpath(os.path.join(newModulePath, descriptionFileName))
    if not os.path.isfile(newDescriptonPath):
        newDescriptionFile = open(newDescriptonPath, "w")
        newDescriptionFile.write(formattedDescriptionContent)
        newDescriptionFile.close()
    else:
        print("\t- No override exist Description!")

    #
    tbTemplateFIle = open(f"{templatefolder}/{tbFileName}", "r")
    formattedTBContent = tbTemplateFIle.read()
    tbTemplateFIle.close()

    #
    newTBPath = os.path.join(newModulePath, tbFileName.replace(".txt", ".cpp"))
    if not os.path.isfile(newTBPath):
        newTBFile = open(newTBPath, "w")
        newTBFile.write(formattedTBContent.format(modulename=modulename))
        newTBFile.close()
    else:
        print("\t- No override exist Testbench!")

    #
    moduleTemplateFIle = open(f"{templatefolder}/{moduleFileName}", "r")
    formattedModuleContent = moduleTemplateFIle.read()
    moduleTemplateFIle.close()

    #
    newModuleContentPath = os.path.join(newModulePath, f"verified_{modulename}.v")
    if not os.path.isfile(newModuleContentPath):
        newModuleFile = open(newModuleContentPath, "w")
        newModuleFile.write(formattedModuleContent.format(modulename=modulename))
        newModuleFile.close()
    else:
        print("\t- No override exist Module Verilog!")
    
    newCategoryPath = os.path.join(newModulePath, categoryFileName)
    if not os.path.isfile(newCategoryPath):
        open(newCategoryPath,'w').close()

    print(f"New module folder is created at {newModulePath}")

def runverified(modulePaths:typing.List[str]):
    # makeverified(modules)
    moduleNormPaths = [os.path.normpath(modulePath) for modulePath in modulePaths]
    for moduleNormPath in moduleNormPaths:
        moduleName = os.path.basename(moduleNormPath)
        moduleNameWorkPath = os.path.join(temporaryWorkFolderName,moduleName)
        if not os.path.isdir(moduleNameWorkPath):
            makeverified([moduleNormPath])
    
    moduleWorkList = ' '.join([re.sub(fr'^{modulefolder}', temporaryWorkFolderName, moduleNormPath) for moduleNormPath in moduleNormPaths])
    
    result = subprocess.run(['make', moduleWorkList], stdout=subprocess.PIPE)
    print('code:', result.returncode, '\nmess:', result.stdout.decode('utf-8'))

def makeverified(modulePaths:list):
    if os.path.isdir(temporaryWorkFolderName):
        shutil.rmtree(temporaryWorkFolderName)
    
    os.mkdir(temporaryWorkFolderName)
    for modulePath in modulePaths:
        moduleNormPath = os.path.normpath(modulePath)
        moduleName = os.path.basename(moduleNormPath)

        moduleNameWorkPath = os.path.join(temporaryWorkFolderName,moduleName)

        if not os.path.isdir(moduleNameWorkPath):
            os.mkdir(moduleNameWorkPath)

        tbModuleFileName = tbFileName.replace(".txt", ".cpp")
        tbModulePath = os.path.join(modulePath, tbModuleFileName)
        tbWorkPath = os.path.join(moduleNameWorkPath, tbModuleFileName)
        os.link(tbModulePath, tbWorkPath)

        moduleVerifiedPath = os.path.join(modulePath, f"verified_{moduleName}.v")
        moduleWorkPath = os.path.join(temporaryWorkFolderName, moduleName, f"{moduleName}.v")
        os.link(moduleVerifiedPath, moduleWorkPath)


        


match args.command:
    case 'createmodule':
        createmodule()
    case 'runverified':
        runverified(args.modules)
        pass
    case 'makeverified':
        makeverified(args.modules)
        pass

print("your args", args)

