# Further

- Templating the creation of new module.
- Templating Makefile: run command of verilator

# 0.1.0

`04-03-2025`

- Generate raw Verilog
  - Default system prompt
  - No context holder.
  - Get description of each module?
- Markdown Code Extraction

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
