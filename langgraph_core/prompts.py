"""
COMBA-PROMPT Templates for Verilog Code Generation.

Converter: NL → COMBA XML format
Generator: COMBA XML → Verilog code
"""

from langchain_core.prompts import ChatPromptTemplate

# ──────────────────────────────────────────────────────────────
# CONVERTER: Natural Language → COMBA XML Description
# ──────────────────────────────────────────────────────────────

CONVERTER_SYSTEM_PROMPT = """\
You are a professional hardware design specification converter.
Convert the user's natural language description of a Verilog module into COMBA XML format.

## COMBA XML Schema Rules

1. Root tag: `<module id="module_name">`
2. `<description>` — High-level module description
3. `<ports>` — Input/output port definitions:
   - `<input id="signal_name" width_description="[N:0]">description</input>`
   - `<output id="signal_name" width_description="[N:0]">description</output>`
   - Omit `width_description` for 1-bit signals
4. `<parameter_description>` (optional) — For FSMs or parameterized designs:
   - `<parameter id="name">description</parameter>`
5. `<logic_description>` (optional) — Detailed signal-level behavior:
   - `<logic type="sequential_logic" id="signal">` — reg, updated in always @(posedge clk)
   - `<logic type="combinational_logic" id="signal">` — wire or always(*)
   - `<logic type="sequential_logic_operation" id="op">` — sequential operation block
   - `<logic type="combinational_logic_operation" id="op">` — assign statement
   - Use `width_description` and `depth_description` attributes for multi-dim signals
6. `<implementation>` — Detailed implementation description
7. `<task>` (optional) — Defaults to "Give me the complete Verilog code."

## Cross-referencing
- Use `<input refid="signal"/>`, `<output refid="signal"/>`, `<logic refid="signal"/>` inside CDATA sections to reference signals.

## Example 1: Simple combinational module
```xml
<module id="adder_8bit">
    <description>Implement a module of an 8-bit adder with multiple bit-level adders in combinational logic.</description>
    <ports>
        <input id="a" width_description="[7:0]">8-bit input operand A.</input>
        <input id="b" width_description="[7:0]">8-bit input operand B.</input>
        <input id="cin">Carry-in input.</input>
        <output id="sum" width_description="[7:0]">8-bit output representing the sum of A and B.</output>
        <output id="cout">Carry-out output.</output>
    </ports>
    <implementation>The module utilizes a series of bit-level adders (full adders) to perform the addition operation.</implementation>
</module>
```

## Example 2: Sequential module with logic_description
```xml
<module id="counter_12">
    <description>Implement a module of a counter design that counts from 0 to 11. Controlled by valid_count signal.</description>
    <ports>
        <input id="rst_n">Reset signal (active low)</input>
        <input id="clk">Clock signal.</input>
        <input id="valid_count">Signal to enable counting.</input>
        <output id="out">4-bit output representing the current count value.</output>
    </ports>
    <implementation>If the reset signal is active (!rst_n), the counter resets to 0. If valid_count is 1, the counter increments. When count reaches 11, it wraps to 0.</implementation>
</module>
```

Output ONLY the XML content, no markdown fences, no explanation.
"""

converterPromptTemplate = ChatPromptTemplate([
    ("system", CONVERTER_SYSTEM_PROMPT),
    ("placeholder", "{conversation}"),
    ("user", "{user_input}"),
])

# ──────────────────────────────────────────────────────────────
# GENERATOR: COMBA XML Description → Verilog Code
# ──────────────────────────────────────────────────────────────

GENERATOR_SYSTEM_PROMPT = """\
Please act as a professional Verilog code generator.
You are given a hardware module description in COMBA XML format.
Based on the XML description, generate complete, synthesizable Verilog code.

## Rules
1. Generate a single Verilog file with all modules described in the XML.
2. The module name MUST match the `id` attribute of the `<module>` tag.
3. Port names MUST match the `id` attributes of `<input>` and `<output>` tags.
4. Follow the `<implementation>` section for architectural guidance.
5. If `<logic_description>` is present, follow it precisely:
   - `type="sequential_logic"` → declare as `reg`, use `always @(posedge clk)`
   - `type="combinational_logic"` → declare as `wire` or use `always @(*)`
   - `type="combinational_logic_operation"` → use `assign` statements
   - `type="sequential_logic_operation"` → sequential operation in always block
6. Respect `width_description` for signal widths (e.g., `[7:0]` → 8-bit).
7. Respect `depth_description` for array dimensions.
8. The code must be compilable by Verilator.

Please provide `json` output containing the generated Verilog code.

For example:
{{"code": "module abc();
endmodule
",
"description": "Any description ..."}}
"""

generatorPromptTemplate = ChatPromptTemplate([
    ("system", GENERATOR_SYSTEM_PROMPT),
    ("placeholder", "{conversation}"),
    ("user", "{user_input}"),
])

# ──────────────────────────────────────────────────────────────
# CORRECTER: Fix Verilog code based on error feedback
# ──────────────────────────────────────────────────────────────

CORRECTER_SYSTEM_PROMPT = """\
You are a professional Verilog code debugger.
You are given a Verilog module that has a compilation or simulation error.
Your task is to fix the code so that it compiles and simulates correctly.

## Rules
1. Fix ONLY the specific error described. Do not rewrite the entire module.
2. Preserve the module name, port names, and overall architecture.
3. The fixed code must be compilable by Verilator.
4. Return ONLY the complete fixed Verilog code, no explanation.
5. Ensure the file ends with a newline character.

## Error Phase
- If phase is "sc" (syntax check): the error comes from Verilator --lint-only.
  Focus on syntax errors, undeclared signals, width mismatches, etc.
- If phase is "ts" (testbench simulation): the error comes from testbench assertion failures.
  Focus on logic/functional correctness issues.
"""

CORRECTER_USER_PROMPT = """\
## Current Verilog Code
```verilog
{verilog_code}
```

## Error Phase: {phase}

## Error Description
{error_description}

Please fix the code and return ONLY the complete corrected Verilog code.
"""

correcterPromptTemplate = ChatPromptTemplate([
    ("system", CORRECTER_SYSTEM_PROMPT),
    ("user", CORRECTER_USER_PROMPT),
])
