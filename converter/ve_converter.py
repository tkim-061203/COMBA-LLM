import glob, os

source_path = "verilog-eval/dataset_code-complete-iccad2023"

dest_path = "../VE_code_completion"

def mysort(x):
    base = os.path.basename(x)
    num = base.split('_')[0]
    return num

prob_paths = glob.glob(f'{source_path}/Prob*_prompt.txt')
prob_paths.sort(key=mysort)

for prob_path in prob_paths:
	module_name = os.path.basename(prob_path).replace('_prompt.txt', '')
	module_new_rel_dir = os.path.join(dest_path, module_name)

	os.makedirs(module_new_rel_dir, exist_ok=True)
    
	prob_dirpath = os.path.dirname(prob_path)
    
	with open(prob_path, 'r') as file:
		prompt_content = file.read()
		with open(f'{module_new_rel_dir}/design_description.ve.txt', 'w+') as file2:
			file2.write(prompt_content)
	
	with open(f'{prob_dirpath}/{module_name}_ref.sv') as file:
		prompt_content = file.read()
		with open(f'{module_new_rel_dir}/verified_{module_name}.v', 'w+') as file2:
			file2.write(prompt_content)
