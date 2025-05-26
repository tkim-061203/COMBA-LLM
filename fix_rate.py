#!/usr/bin/env python
# coding: utf-8

# # Fix Rate

# In[19]:


import glob, os, json, subprocess, re


# In[16]:


from scripts.constants import Template, ModuleNamePrefix
from scripts.lazy import getTemplateFilenamePath
from run import makeWorkingFolder


# In[17]:


def makeFileRun(workPath='', moduleName='', command='lint'):
    moduleWorkPath = os.path.join(workPath, moduleName)

    commandArgs = ["make", f"WORKDIR={workPath}"]

    commandArgs += [moduleWorkPath + (f'/obj_dir/V{moduleName}' if command=='V' else f'/{command}')]
    
    if command == 'V':
        commandArgs += ['CFLAGS=-DNO_FALTAL_TB']
        # print('makeFileRun', command, commandArgs)
    compilationCpltProcess = subprocess.run(
        commandArgs,
        stdout=subprocess.PIPE,
    )
    return (compilationCpltProcess.stdout.decode("utf8"), compilationCpltProcess.returncode)


# In[18]:


llm_model="gpt-4o-mini-2024-07-18"
modulePaths = glob.glob('modules/*')
# modulePaths = glob.glob('modules/div_8bit')
moduleGlobPaths = []
for modulePath in modulePaths:
    moduleGlobPaths += glob.glob(modulePath)

moduleNormPaths = [os.path.normpath(modulePath) for modulePath in moduleGlobPaths]
myexit_str = """#define myexit(condition, content)   \\
    {                                \\
        assert(condition &&content); \\
    }"""

fix_rate_result = {}
descptionType = 'RTLLM.txt'
for moduleNormPath in moduleNormPaths:
    moduleName = os.path.basename(moduleNormPath)
    report_json_path = glob.glob(os.path.join(moduleNormPath, 'reports', f'*{llm_model}*{descptionType}.json'))
    report_json_path = report_json_path[0] if len(report_json_path) else ''
    print('Process module ', moduleName, report_json_path)

    if not os.path.isfile(report_json_path):
        print(f"JSON Report file not found for module {moduleName}")
        continue

    with open(report_json_path, 'r') as file:
       report_json_dict = json.load(file)

    state_trials = report_json_dict['state_trial']
    total_trials = len(state_trials)
    exception_trials = report_json_dict['exception_trial']
    fix_rate_result[moduleName] = {
        'syntax': 0,
        'tb': 0
    }
    for trial_th in range(total_trials):
        state_trial_dict = state_trials[trial_th]
        syntaxLimitTrialsContent = list(state_trial_dict['syntaxLimitTrials'].keys())
        syntaxLimitTrialsLen = len(syntaxLimitTrialsContent)
        
        #
        # tb trials
        tbLimitTrialsContent = list(state_trial_dict['tbLimitTrials'].keys())
        tbLimitTrialsLen = len(tbLimitTrialsContent)
        #
        exception_rate = 0
        tb_rate = 0

        #
        # last success code
        last_success_code = None

        #
        # if syntax success
        exception_trial = exception_trials[trial_th]
        if exception_trial:
            lastTBSimulationSuccessStatusList = state_trial_dict['lastTBSimulationSuccessStatus']
            lastSyntaxSimilationSuccessStatusList = state_trial_dict['lastSyntaxSimilationSuccessStatus']
            if len(lastTBSimulationSuccessStatusList):
                last_success_code = lastTBSimulationSuccessStatusList[-1]['generated_code']['code']
            elif len(lastSyntaxSimilationSuccessStatusList):
                last_success_code = lastSyntaxSimilationSuccessStatusList[-1]['generated_code']['code']

        if last_success_code == None:
            print(f'The trial {trial_th} of module {moduleName} have no success code!')
        else:
            #
            # write to llm_code of module
            llm_code_file_path = getTemplateFilenamePath(moduleNormPath, 'v', f'{ModuleNamePrefix.LLM.value}{moduleName}')
            if not os.path.isfile(llm_code_file_path):
                print('Unknow LLM code path', llm_code_file_path)
            else:
                with open(llm_code_file_path, 'w') as file:
                    file.write(last_success_code)

                #
                # make work folder
                makeWorkingFolder([moduleNormPath], Template.TEMPORARYLLMWORKFOLDERNAME.value, ModuleNamePrefix.LLM.value)

                (resultSTDOUTUTF8, returncode) = makeFileRun(Template.TEMPORARYLLMWORKFOLDERNAME.value, moduleName)

                ExceptionTrialRegex = re.compile(
                    rf"(?P<exceptionType>Warning|Error)-(?P<exceptionTitle>[A-Z0-9_]*)?-(?P<exceptionContent>.*)",
                    re.MULTILINE,
                )
                # syntax log
                if len(syntaxLimitTrialsContent):
                    for syntaxLimitTrialsContentItem in syntaxLimitTrialsContent:
                        exceptionType = exceptionContent = None
                        ExceptionTrialRegexFindAll = ExceptionTrialRegex.findall(syntaxLimitTrialsContentItem)
                        if len(ExceptionTrialRegexFindAll):
                            exceptionType, _, exceptionContent = ExceptionTrialRegexFindAll[0]
                        if exceptionType != None and exceptionContent != None:
                            ExceptionRegex = re.compile(
                                rf"%({exceptionType})(?P<lineException>(-(?P<exceptionTitle>[A-Z0-9_]*))?:\s(?P<fileName>\w*\.v):(?P<lineNumber>[0-9]*):(?P<posNumber>[0-9]*))?:\s({exceptionContent})",
                                re.MULTILINE,
                            )
                            ExceptionRegexSearch = ExceptionRegex.search(resultSTDOUTUTF8)
                            if ExceptionRegexSearch == None:
                                exception_rate += 1 / syntaxLimitTrialsLen
                            else:
                                print(f'Unfixed exception {ExceptionRegexSearch} for module {moduleName}')
                else: # no syntax trials?
                    exception_rate += 1
                #
                # tb run
                makeFileRun(Template.TEMPORARYLLMWORKFOLDERNAME.value, moduleName, 'V')
                
                for i in range(5):
                    try:
                        (resultSTDOUTUTF8, returncode) = makeFileRun(Template.TEMPORARYLLMWORKFOLDERNAME.value, moduleName, 'docker_run')
                        if returncode:
                            raise Exception(f"Testbench with NO_FALTAL_TB failed! \n{resultSTDOUTUTF8}\n{syntaxLimitTrialsContent}")
                        break
                    except:
                        print('Trial tb run', i)

                TBTrialRegex = re.compile(
                    rf"(?P<todoNum>[0-9]*)-(?P<failureContent>.*)",
                    re.MULTILINE,
                )
                # tb log
                if len(tbLimitTrialsContent):
                    for tbLimitTrialsContentItem in tbLimitTrialsContent:
                        todoNum = failureContent = None
                        TBTrialRegexFindAll = TBTrialRegex.findall(tbLimitTrialsContentItem)
                        if len(TBTrialRegexFindAll):
                            todoNum, failureContent = TBTrialRegexFindAll[0]
                        if todoNum != None and failureContent != None:
                            failureContent = failureContent.replace('\r', '')
                            failureContent = failureContent.replace('\n', '')
                            failureContent = failureContent.replace('"\' failed.', '')
                            
                            if failureContent not in resultSTDOUTUTF8:
                                tb_rate += 1 / tbLimitTrialsLen
        
                            else:
                                print(f'Unfixed tb failed {failureContent} for module {moduleName}')
                else:
                    tb_rate += 1
                    

        print(f"exception_rate of module {moduleName} in {trial_th}th: ", round(exception_rate, 2))
        print(f"tb_rate of module {moduleName} in {trial_th}th: ", round(tb_rate, 2))
        fix_rate_result[moduleName]['syntax'] += (exception_rate / total_trials)
        fix_rate_result[moduleName]['tb'] += (tb_rate / total_trials)
        #
        # tb fix rate
    print(f"Average fix rate of module {moduleName}:", fix_rate_result[moduleName])

print('All fix rate:', fix_rate_result)
os.makedirs('reports/fixrate', exist_ok=True)
with open(f'reports/fixrate/fixrate.{descptionType}.json', 'w+') as file:
    json.dump(fix_rate_result, file, indent=4)


# In[ ]:




