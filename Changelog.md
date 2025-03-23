# Rework 3.0: Langraph

## Limit

- Loop call
- No iteration
- Refine based on exception only.
- Initial generation is only at the start. No flow integration for the generator.

## Further

- Compilation Structure for submodule of a complex module.
- Another LLM for Stating the current module/submodule.
- Aticulate waveform.vcd

## 2.1.0

- Change initial prompt.
- Ignore EOFNEWLINE of Verilator
- REGEX for case:

```
make: *** [.llmwork/adder_8bit/lint] Error 1
compile: NO EXCEPTION NOW! ###Verilating for adder_8bit###
%Error: Specified --top-module 'adder_8bit' was not found in design.
%Error: Exiting due to 1 error(s)
```

- Ignore Verilator Warning: GENUNNAMED

## 2.0.0

- Speed up with Langraph

- No iteration for framework.
  - Only for looping.
- Memory

- Init: Chat with initial code.
- Single module compilation only.
- Prompt Template for the Code Fixer LLM.
  - Json/dict format for the output
# Purpose

- Improve RTLLM
- Mechanism: LLM-powered Verilog Syntax Checking.

# Limitations

- Only for LLM-powered Syntax Checking.
- No middleware.
- Specibility:
  - Iteration for querying LLM and Syntax checking. With log infomation
- NO agent framework
- No abstract class for LLM call or role change

# Further

- Format the input of module folder.
- Descriptions of components in a module folder.
- GUI for mannagement.
- Templating the creation of new module. [x]
- Templating Makefile: run command of verilator [x]
- LLM Generation History [x].
- Click alternative to ArgumentParser.
- Tuple alternative for speeding!

# 0.3.0

- Import an PDF as RAG source.
- Warning extraction from log

# 0.2.0

`06-03-2025`

# 0.1.0

`04-03-2025`

- Generate raw Verilog
  - Default system prompt
  - No context holder.
  - Get description of each module?
- Markdown Code Extraction.
- Single Module Composition.
  - Store LLM output to file. llmgen.v. and history cache
    - cache by datetime.
- Parameterizing `makeWorkingFolder`.
  - Modify `createModule`.
  - create `.llmwork` or `.work`.
  - generate LLM content if no content?

# 0.0.0

`02-03-2025`

- Dockerfile for Yosys and Verilator Image.
- Bash Shell for Container run.
  - tool input.
  - pwd for -v
- Python command to create new module

  - new folder and check exist folder
  - new design description in template.
  - no template for verified verilog and testbench.
  - simple module template
  - no override exist file, not content

- Python command to run a module.

  - template: .work folder

- Template for category

  - category file
  - workfolder:
    - hardlink with modules in modules folder.
  - Testbench with TODO index.

- Functions:
  - Make works folder.
  - Run make module after check work folders
