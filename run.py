from multiprocessing import Pool
from dotenv import load_dotenv
load_dotenv()

import argparse, os, shutil, typing, glob, sys
import datetime
from scripts.langchain_groq_util import generate as llmGenerate
from scripts.utils import md_code_extract, generateWorkFolderArgument, generateMEICWorkFolderArgument
from scripts.constants import Commands, ModuleNamePrefix, Template
# from scripts.rag import ragCreate
from scripts.codeAgent import LLMCodeAgent
from scripts.MEICCodeAgent import MEICLLMCodeAgent

from tqdm import tqdm

from langchain_core.rate_limiters import InMemoryRateLimiter

rate_limiter = InMemoryRateLimiter(
    requests_per_second=1.6,  # <-- Can only make a request once every 10 seconds!!
    check_every_n_seconds=0.1,  # Wake up every 100 ms to check whether allowed to make a request,
    max_bucket_size=10000,  # Controls the maximum burst size.
)

srcDir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(f"{srcDir}/scripts"))
sys.path.insert(0, srcDir)

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
parser_runGenericWork = subparsers.add_parser(
    Commands.RUNGENERIC.value, help="Run projects with verilog module in general"
)
parser_runGenericWork.add_argument("modules", nargs="*")
parser_runGenericWork.add_argument(
    "--llm", action="store_true", help="Run LLM Working Directory"
)
parser_runGenericWork.add_argument(
    "--descriptiontype", default='xml', help="Description type", nargs='?', type=str
)
parser_runGenericWork.add_argument(
    "--nodebug", action="store_true", help="No Debug with yes/no input"
)
parser_runGenericWork.add_argument(
    "--moduletask", default='VE_code_completion', help="Module task", nargs='?', type=str
)
parser_runGenericWork.add_argument(
    "--temperature", default=0, help="LLM temperature", type=float
)
parser_runGenericWork.add_argument(
    "--samples", default=1, help="LLM Samples", type=int
)
parser_runGenericWork.add_argument(
    "--examples", default=0, help="LLM examples", type=int
)
parser_runGenericWork.add_argument(
    "--generatecodeonly", action="store_true", help="Generate code only, no post processing"
)

#
parser_makeWork = subparsers.add_parser(
    Commands.MAKEWORK.value, help="Make projects with verilog module"
)
parser_makeWork.add_argument("modules", nargs="*")
parser_makeWork.add_argument(
    "--llm", action="store_true", help="Make LLM Working Directory"
)
parser_runGenericWork.add_argument(
    "--lintonly", action="store_true", help="Lint only"
)

parser_generate = subparsers.add_parser(
    Commands.GENERATE.value, help="Generate Verilog module"
)
parser_generate.add_argument("modules", nargs="*")

parser_rag = subparsers.add_parser(Commands.RAG.value, help="RAG Interface")
parser_rag.add_argument("ragfile")

# ── LangGraph COMBA Pipeline ──
parser_langgraph = subparsers.add_parser(
    "langgraph", help="Run full COMBA v2 pipeline (LangGraph) on modules"
)
parser_langgraph.add_argument("modules", nargs="*")
parser_langgraph.add_argument(
    "--descriptiontype", default="xml", help="Description type: xml or txt", type=str
)
parser_langgraph.add_argument(
    "--samples", default=1, help="Number of repeat trials per module", type=int
)

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

def makeGenericWorkingFolder(
    modulePaths: typing.List[str],
    # workFolderName=Template.TEMPORARYWORKFOLDERNAME.value,
    moduleNamePrefix=ModuleNamePrefix.LLM.value,
    referenceModuleDir=Template.MODULEFOLDER.value,
):

    # if not os.path.isdir(workFolderName):
    #     os.mkdir(workFolderName)

    for modulePath in modulePaths:
        moduleNormPath = os.path.normpath(modulePath)
        moduleName = os.path.basename(moduleNormPath)

        moduleNameWorkPath = moduleName
        referenceModuleNameWorkPath = os.path.join(referenceModuleDir, moduleName)
        

        if os.path.isdir(moduleNameWorkPath):
            shutil.rmtree(moduleNameWorkPath)
        os.mkdir(moduleNameWorkPath)

        tbModuleFileName = Template.TBFILENAME.value.replace(".txt", ".cpp")
        tbModulePath = os.path.join(referenceModuleNameWorkPath, tbModuleFileName)
        tbWorkPath = os.path.join(moduleNameWorkPath, tbModuleFileName)
        if os.path.isdir(tbModulePath):
            os.link(tbModulePath, tbWorkPath)

        moduleWorkPath = os.path.join(moduleName, f"{moduleName}.v")
        open(moduleWorkPath, 'w+').close()



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

def runGenericFlow(
    modulePaths: typing.List[str],
    workFolderName=Template.MEIC_TEMPORARYWORKFOLDERNAME.value,
    moduleNamePrefix=ModuleNamePrefix.LLM.value,
    desciptionType='txt',
    nodebug=False,
    llm_model="gpt-4o-mini-2024-07-18",
    moduleTask="VE_code_completion",
    lintOnly=True,
    temperature:float=0,
    examples=0,
    samples=1,
    generateCodeOnly=False
):
    moduleTaskAbsPath = os.path.join(srcDir, moduleTask)
    moduleGlobPaths = []
    
    for modulePath in modulePaths:
        moduleGlobPaths += glob.glob(os.path.join(srcDir,modulePath))

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

    # moduletqdm = tqdm(total=len(moduleGlobPaths), desc='Module')

    #
    # log file
    # create file if not exist
    os.makedirs('reports/log', exist_ok=True)
    if not os.path.isfile('reports/log/log.txt'):
        open('reports/log/log.txt', 'w+').close()
    # clear file
    with open('reports/log/log.txt', 'w+') as file:
        file.write('')

    # for moduleNormPath in moduleNormPaths:
    global do_process
    def do_process(moduleNormPath):

        # moduletqdm.update(1)
        moduleName = os.path.basename(moduleNormPath)

        #
        with open('reports/log/log.txt', 'a') as file:
            print(f"### Log for module \"{moduleName}\"", sep='\n', file=file)
        
        makeGenericWorkingFolder([moduleNormPath], moduleNamePrefix, moduleTaskAbsPath)

        #
        print("flow here", moduleNormPath, moduleName)
        llmCodeAgent = MEICLLMCodeAgent(
            srcDir=srcDir,
            modulePath=moduleNormPath,
            llm_model=llm_model,
            model_provider="openai",
            descriptionType=desciptionType,
            customInputDirective=customInputDirective,
            lintOnly=lintOnly,
            moduleTaskAbsPath=moduleTaskAbsPath,
            temperature=temperature,
            examples=examples,
            rate_limiter=rate_limiter,
            generateCodeOnly=generateCodeOnly
        )
        llmCodeAgent(samples=samples)
    
    num_core = 1# int(os.cpu_count() / 2)
    my_range = moduleNormPaths
    with Pool(processes=num_core) as pool:
        for i in tqdm(iterable=pool.imap_unordered(do_process, my_range), total=len(my_range)):
            pass

    # #
    # history log
    # mkdir if not exist
    os.makedirs('reports/log/.history', exist_ok=True)
    # if not os.path.isdir('reports/log/.history'):
    #     os.mkdir('reports/log/.history')
    
    history_tag = datetime.datetime.now().isoformat()
    shutil.copyfile('reports/log/log.txt', f'reports/log/.history/log_{llm_model}_{history_tag}.txt')

# ──────────────────────────────────────────────────────────────
# LangGraph COMBA v2 Pipeline Runner
# ──────────────────────────────────────────────────────────────

def runLangGraphFlow(
    modulePaths: typing.List[str],
    descriptionType: str = "xml",
    samples: int = 1,
):
    """
    Run the full COMBA v2 pipeline (LangGraph) on each module.

    For each module in modulePaths:
      1. Read design_description.{xml|txt}
      2. Build initial COMBAState
      3. Run build_comba_graph(llm).invoke(state)
      4. Save JSON report to modules/{name}/reports/
    """
    import re as _re
    sys.path.insert(0, os.path.join(srcDir, "langgraph_core"))
    from comba_pipeline import build_comba_graph, make_initial_state
    from llm_interface import COMBALlm

    # Init LLM and graph once
    llm = COMBALlm.from_env()
    graph = build_comba_graph(llm)
    print(f"[LangGraph] Pipeline ready: {llm}")

    moduleGlobPaths = []
    for modulePath in modulePaths:
        moduleGlobPaths += glob.glob(modulePath)

    moduleNormPaths = [os.path.normpath(mp) for mp in moduleGlobPaths]
    total = len(moduleNormPaths)
    print(f"[LangGraph] Running {total} modules × {samples} sample(s)")

    all_results = {}

    for idx, moduleNormPath in enumerate(moduleNormPaths, 1):
        moduleName = os.path.basename(moduleNormPath)
        print(f"\n{'═' * 60}")
        print(f"  [{idx}/{total}] Module: {moduleName}")
        print(f"{'═' * 60}")

        # Read description
        if descriptionType == "xml":
            desc_file = os.path.join(moduleNormPath, "design_description.xml")
        else:
            desc_file = os.path.join(moduleNormPath, "design_description.txt")

        if not os.path.isfile(desc_file):
            print(f"  ⚠️ Description file not found: {desc_file}, skipping")
            continue

        with open(desc_file, "r", encoding="utf-8") as f:
            description = f.read()

        sample_results = []

        for sample_idx in range(1, samples + 1):
            if samples > 1:
                print(f"  ── Sample {sample_idx}/{samples} ──")

            # Build initial state
            state = make_initial_state(nl_input=description, module_name=moduleName)

            # If XML description, skip converter
            if descriptionType == "xml":
                state["xml_description"] = description

            # Run pipeline
            try:
                config = {"recursion_limit": 100}
                final = graph.invoke(state, config)

                result = {
                    "module_name": moduleName,
                    "description_type": descriptionType,
                    "final_status": final.get("final_status", "unknown"),
                    "sc_trial": final.get("sc_trial", 0),
                    "ts_trial": final.get("ts_trial", 0),
                    "total_iter": final.get("total_iter", 0),
                    "gvd": final.get("gvd", ""),
                    "xml_description": final.get("xml_description", ""),
                    "sc_log": final.get("sc_log", ""),
                    "tb_log": final.get("tb_log", ""),
                    "error": final.get("error"),
                }

                status = result["final_status"]
                emoji = "🎉" if status == "pass" else "❌"
                print(f"  {emoji} Result: {status} | SC:{result['sc_trial']} TS:{result['ts_trial']}")

            except Exception as e:
                result = {
                    "module_name": moduleName,
                    "description_type": descriptionType,
                    "final_status": "error",
                    "error": str(e),
                    "sc_trial": 0, "ts_trial": 0, "total_iter": 0,
                    "gvd": "", "xml_description": "", "sc_log": "", "tb_log": "",
                }
                print(f"  ❌ Pipeline error: {e}")

            sample_results.append(result)

        # Save report
        reports_dir = os.path.join(moduleNormPath, "reports")
        os.makedirs(reports_dir, exist_ok=True)

        report_path = os.path.join(
            reports_dir, f"report_langgraph.{descriptionType}.json"
        )

        report_data = {
            "module_name": moduleName,
            "description_type": descriptionType,
            "samples": sample_results if samples > 1 else sample_results[0],
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        print(f"  📄 Report saved: {report_path}")
        all_results[moduleName] = report_data

    # Summary
    print(f"\n{'═' * 60}")
    print("  SUMMARY")
    print(f"{'═' * 60}")
    pass_count = 0
    for name, data in all_results.items():
        r = data["samples"] if isinstance(data["samples"], dict) else data["samples"][0]
        status = r.get("final_status", "?")
        if status == "pass":
            pass_count += 1
        emoji = "✅" if status == "pass" else "❌"
        print(f"  {emoji} {name}: {status} (SC:{r.get('sc_trial',0)} TS:{r.get('ts_trial',0)})")
    print(f"\n  Pass rate: {pass_count}/{total} ({pass_count/total*100:.1f}%)")

    # Save global summary
    os.makedirs("reports", exist_ok=True)
    summary_path = f"reports/summary_langgraph.{descriptionType}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"  📄 Global summary: {summary_path}")


if __name__ == "__main__":
    args = parser.parse_args()
    match args.command:
        case Commands.CREATEMODULE.value:
            createmodule()
        case Commands.RUNWORK.value:
            runFlow(args.modules, *(generateWorkFolderArgument(args.llm) + (args.descriptiontype, args.nodebug)))
        case Commands.RUNGENERIC.value:
            runGenericFlow(args.modules,
                           desciptionType=args.descriptiontype,
                           nodebug=args.nodebug,
                           moduleTask=args.moduletask,
                           lintOnly=args.lintonly,
                           temperature=args.temperature,
                           samples=args.samples,
                           examples=args.examples,
                           generateCodeOnly=args.generatecodeonly)
        case Commands.MAKEWORK.value:
            makeWorkingFolder(args.modules, *generateWorkFolderArgument(args.llm))
        case Commands.GENERATE.value:
            generate(args.modules)
        case "langgraph":
            runLangGraphFlow(
                args.modules,
                descriptionType=args.descriptiontype,
                samples=args.samples,
            )
        # case Commands.RAG.value:
        #     ragCreate(args.ragfile)

    print("your args", args)
