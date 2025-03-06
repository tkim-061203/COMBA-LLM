# Purpose

- Improve RTLLM
- Mechanism: LLM-powered Verilog Syntax Checking.

# Limitations

- Only for LLM-powered Syntax Checking.
- No middleware.
- Specibility:
  - Iteration for querying LLM and Syntax checking. With log infomation

# Further

- Format the input of module folder.
- Descriptions of components in a module folder.
- GUI for mannagement.
- Templating the creation of new module. [x]
- Templating Makefile: run command of verilator [x]
- LLM Generation History [x].

# Next abstraction

- ?

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
