import os, glob, sys, ast, json, tempfile, subprocess, re
import numpy as np

def module_extraction(example_code, format_code=False):
    if format_code:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".v") as fp:
            fp.write(example_code.encode(encoding='utf-8'))
            fp.close()
            sub_run = subprocess.run(['verible-verilog-format', fp.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # example_code = sub_run.stdout.decode("utf-8")
            with open(fp.name, 'r') as file:
                example_code = file.read()
    
        subprocess.run(['rm', '-f', fp.name])
    code_lines = example_code.splitlines()
    regex_stage = 0
    regexes = [r'^.*module\s+', r'^.*module$']
    
    module_def_span = np.array([None, None, None, None])
    num_indexs = 0
    comment_stage = 0
    multiline_comment = [False, -1]
    all_comment_ranges = []
    for i in range(len(code_lines)):
        line = code_lines[i]
        num_indexs += (i > 0) # plus previous \n
        if comment_stage == 0:
            line_for_comment = str(line)
            comment_ranges = []
            comment_num_indexs = 0
            while True:
                double_slash_index = line_for_comment.find("//")
                double_slash_index = [double_slash_index, double_slash_index]
                
                single_slash_index = line_for_comment.find("/*")
                single_slash_index = [single_slash_index, single_slash_index]
                
                single_slash_end_index = line_for_comment.rfind("*/")
                single_slash_end_index = [single_slash_end_index, single_slash_end_index]

                #
                # Handle for case of multi-line comment
                if multiline_comment[0]:
                    if (double_slash_index[0] != -1 and single_slash_end_index[0] != -1):
                        if (double_slash_index[0] < single_slash_end_index[0]) or (double_slash_index[0] - single_slash_end_index[0] == 1):
                            double_slash_index[0] = -1
                        # else: No else!!!                            
                else:
                    if double_slash_index[0] != -1 and single_slash_index[0] != -1: # fix all cases of comment!!
                        if double_slash_index[0] < single_slash_index[0]:
                            single_slash_index[0] = -1
                        else:
                            double_slash_index[0] = -1
                    if (double_slash_index[0] != -1 and single_slash_end_index[0] != -1):
                        if double_slash_index[0] < single_slash_end_index[0]:
                            single_slash_end_index[0] = -1
                    if single_slash_end_index[0] > -1 and single_slash_index[0] > -1 and (single_slash_end_index[0] - single_slash_index[0] == 1):
                        single_slash_end_index[0] = single_slash_end_index[1] = -1
                #
                # handle for start comment
                # start_comment_index = double_slash_index if double_slash_index != None else single_slash_index if single_slash_index != None else None
                if multiline_comment[0]:
                    if single_slash_end_index[0] != -1:
                        multiline_comment[0] = False

                        len_of_old_line = len(line_for_comment)
                        comment_ranges.append([0, single_slash_end_index[0] + 1])
                        comment_ranges[-1][0] += comment_num_indexs
                        comment_ranges[-1][1] += comment_num_indexs
                        
                        line_for_comment = line_for_comment[single_slash_end_index[0]+2:]
                        comment_num_indexs += len_of_old_line - len(line_for_comment)
                    elif multiline_comment[1] != i:
                        len_of_old_line = len(line_for_comment)
                        if len_of_old_line:
                            comment_ranges.append([0, len_of_old_line - 1])
                            comment_ranges[-1][0] += comment_num_indexs
                            comment_ranges[-1][1] += comment_num_indexs
                            
                            line_for_comment = line_for_comment[:0]
                            comment_num_indexs += len_of_old_line - len(line_for_comment)
                        break
                else:
                    if single_slash_end_index[0] != -1:
                        if (double_slash_index[0] != -1 and double_slash_index[0] > single_slash_end_index[0]) or (single_slash_index[0] != -1 and single_slash_index[0] > single_slash_end_index[0]) or (double_slash_index[0] == -1 and single_slash_index[0] == -1):
                            raise Exception(f"Error end of multiline comment!!!\n{example_code}")
                
                if not multiline_comment[0]:
                    if double_slash_index[0] != -1:
                        len_of_old_line = len(line_for_comment)
                        comment_ranges.append([double_slash_index[0], len_of_old_line - 1])
                        comment_ranges[-1][0] += comment_num_indexs
                        comment_ranges[-1][1] += comment_num_indexs
                        
                        line_for_comment = line_for_comment[:double_slash_index[0]]
                        comment_num_indexs += len_of_old_line - len(line_for_comment)
                    if single_slash_index[0] != -1 and single_slash_end_index[0] == -1:
                        multiline_comment[0] = True
                        multiline_comment[1] = i

                        len_of_old_line = len(line_for_comment)
                        comment_ranges.append([single_slash_index[0], len_of_old_line - 1])
                        comment_ranges[-1][0] += comment_num_indexs
                        comment_ranges[-1][1] += comment_num_indexs
                        
                        line_for_comment = line_for_comment[:single_slash_index[0]]
                        comment_num_indexs += len_of_old_line - len(line_for_comment)
                        
                    elif single_slash_index[0] != -1 and single_slash_end_index[0] != -1:
                        len_of_old_line = len(line_for_comment)
                        comment_ranges.append([single_slash_index[0], single_slash_end_index[0]+1])
                        comment_ranges[-1][0] += comment_num_indexs
                        comment_ranges[-1][1] += comment_num_indexs
                        
                        line_for_comment = line_for_comment[:single_slash_index[0]] + line_for_comment[single_slash_end_index[0]+2:]
                        comment_num_indexs += len_of_old_line - len(line_for_comment)
                        
                if double_slash_index[1] != -1 or single_slash_index[1] != -1 or single_slash_end_index[1] != -1:
                    continue
                else:
                    break
                
        # if len(comment_ranges):
        #     print(comment_ranges, i)

        section_start_idx = 0
        cur_section = ''
        all_comment_ranges.append(comment_ranges[:])
        if len(comment_ranges): # sort for correct order
            comment_ranges.sort(key=lambda item: item[0])
            
        while section_start_idx < len(line):
            old_section_start_idx = section_start_idx
            if len(comment_ranges):
                cur_section = line[section_start_idx:comment_ranges[0][0]]
                section_start_idx += comment_ranges[0][1] + 1
                comment_ranges.pop(0)
            else:
                cur_section = line[section_start_idx:]
                section_start_idx += len(cur_section)
        
            #
            if regex_stage == 0:
                for regex in regexes:
                    module_match = re.match(regex, cur_section)
                    if module_match != None:
                        regex_stage += 1
                        span = module_match.span()
                        module_def_span = np.vstack((module_def_span, [span[0] + num_indexs, span[1] + num_indexs, None, None]))
                        break
            if regex_stage == 1:
                semicon_pos = cur_section.find(";")
                if semicon_pos != -1:
                    module_def_span[-1][-2] = num_indexs + semicon_pos + 1
                    regex_stage += 1
            if regex_stage == 2:
                find_start = 0
                while True:
                    endmodule_word = "endmodule"
                    endmodule_pos = cur_section.find(endmodule_word, find_start)
                    endmodule_pos_end = endmodule_pos + len(endmodule_word)
                    if endmodule_pos != -1:
                        left_endmodule = False
                        right_endmodule = False

                        #
                        if endmodule_pos == 0:
                            left_endmodule = True
                        elif endmodule_pos > 0:
                            left_ord = ord(cur_section[endmodule_pos - 1] )
                            if not ((left_ord >= 65 and left_ord <= 90) or (left_ord >= 97 and left_ord <= 122) or left_ord == 95):
                                left_endmodule = True

                        #
                        if endmodule_pos_end < len(cur_section):
                            right_ord = ord(cur_section[endmodule_pos_end])
                            if not ((right_ord >= 65 and right_ord <= 90) or (right_ord >= 97 and right_ord <= 122) or right_ord == 95):
                                right_endmodule = True
                        elif endmodule_pos_end == len(cur_section):
                            right_endmodule = True

                        if left_endmodule and right_endmodule:
                            module_def_span[-1][-1] = num_indexs + endmodule_pos + 1
                            regex_stage = 0
                            break
                        else:
                            find_start += endmodule_pos_end
                    else:
                        break
                            # if left_ord == 13 or left_ord == 10 or left_ord == 9 or left_ord == 12 or left_ord == 32:
                            #     left_endmodule = True
                        # module_def_span[-1][-1] = num_indexs + endmodule_pos + 1
                        # regex_stage = 0
    
            num_indexs += section_start_idx - old_section_start_idx
    if len(module_def_span.shape) < 2:
        error_txt = f"Module span is all null {len(example_code)}: {example_code}"
        
        raise Exception(error_txt)
        
    module_def_span = np.delete(module_def_span, 0, 0)
    module_wrapper = ""
    module_definition = []
    module_output_code = []
    for span in module_def_span:
        if None in span:
            raise Exception(f"Span Error!! {len(example_code)}: {example_code}")
        module_definition += [example_code[span[0]:span[2]]]
        module_output_code += [example_code[span[2]:span[3]+8]]
        
    module_definition_with_upper_comments = []
    for i in range(len(module_def_span)):
        span = module_def_span[i]
        if i == 0:
            span[0] = 0
        else:
            span[0] = module_def_span[i-1][-1] + 1
        module_definition_with_upper_comments += [example_code[span[0]:span[2]]]
        
    return (module_definition, module_output_code, module_definition_with_upper_comments, module_def_span, all_comment_ranges)


model_name = sys.argv[1]
design_paths = glob.glob("./Prob*")

for design_path in design_paths:
	report_file_path = glob.glob(f'{design_path}/reports/report_{model_name}*.json')
	if len(report_file_path):
		report_file_path = report_file_path[0]
	else:
		print('Failed report', design_path)
		continue

	with open(report_file_path, 'r') as file:
		report_dict = json.load(file)

	for i in range(len(report_dict['state_trial'])):
	# for state_trial in report_dict['state_trial']:
		state_trial = report_dict['state_trial'][i]
		final_code = state_trial['generated_code']['code'] if not len(state_trial['lastTBSimulationSuccessStatus']) else state_trial['lastTBSimulationSuccessStatus'][-1]['generated_code']['code']
		final_code = final_code.replace('\\n', '\n')
		# final_description = 
		user_input = state_trial['user_input']

		design_name = os.path.basename(design_path)
		with open(f'{design_path}/{design_name}_sample{i+1:02d}_response.txt', 'w+') as file:
			# file.write(user_input)
			try:
				module_definition, module_output_code, module_definition_with_upper_comments, module_def_span, all_comment_ranges = module_extraction(final_code)
			except:
				print(f'Extraction failed, {i+1}, {design_name}')
				module_output_code = [final_code]
			code_completion = module_output_code[0]
			file.write(code_completion)
		with open(f'{design_path}/{design_name}_sample{i+1:02d}_prompt.txt', 'w+') as file:
			file.write(final_code)
            
		# with open(f'{design_path}/{design_name}_sample{i+1:02d}.sv', 'w+') as file:
               
		# print(design_path)
	