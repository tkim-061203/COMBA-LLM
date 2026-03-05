"""
COMBA-PROMPT Templates for Verilog Code Generation & Debugging.

Templates:
  - converterPromptTemplate  — NL → COMBA XML (with few-shot)
  - generatorPromptTemplate  — COMBA XML → Verilog (with few-shot)
  - edpPromptTemplate        — EDP: fix syntax errors (COMBA Figure 6)
  - tdpPromptTemplate        — TDP: fix functional failures
  - correcterPromptTemplate  — Generic correcter (legacy compat)
"""

from langchain_core.prompts import ChatPromptTemplate

# ══════════════════════════════════════════════════════════════
# FEW-SHOT EXAMPLES (from RTLLM 29 modules)
# ══════════════════════════════════════════════════════════════

# ── Example 1: Simple combinational (adder_8bit) ──
FEWSHOT_XML_ADDER = """\
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
</module>"""

FEWSHOT_VERILOG_ADDER = """\
module adder_8bit(
    input [7:0] a, b,
    input cin,
    output [7:0] sum,
    output cout
);
    wire [7:0] c;
    full_adder FA0 (.a(a[0]), .b(b[0]), .cin(cin), .sum(sum[0]), .cout(c[0]));
    full_adder FA1 (.a(a[1]), .b(b[1]), .cin(c[0]), .sum(sum[1]), .cout(c[1]));
    full_adder FA2 (.a(a[2]), .b(b[2]), .cin(c[1]), .sum(sum[2]), .cout(c[2]));
    full_adder FA3 (.a(a[3]), .b(b[3]), .cin(c[2]), .sum(sum[3]), .cout(c[3]));
    full_adder FA4 (.a(a[4]), .b(b[4]), .cin(c[3]), .sum(sum[4]), .cout(c[4]));
    full_adder FA5 (.a(a[5]), .b(b[5]), .cin(c[4]), .sum(sum[5]), .cout(c[5]));
    full_adder FA6 (.a(a[6]), .b(b[6]), .cin(c[5]), .sum(sum[6]), .cout(c[6]));
    full_adder FA7 (.a(a[7]), .b(b[7]), .cin(c[6]), .sum(sum[7]), .cout(c[7]));
    assign cout = c[7];
endmodule

module full_adder (input a, b, cin, output sum, cout);
    assign {cout, sum} = a + b + cin;
endmodule
"""

# ── Example 2: Sequential (counter_12) ──
FEWSHOT_XML_COUNTER = """\
<module id="counter_12">
    <description>Implement a module of a counter design that counts from 0 to 11. Controlled by valid_count signal.</description>
    <ports>
        <input id="rst_n">Reset signal (active low)</input>
        <input id="clk">Clock signal.</input>
        <input id="valid_count">Signal to enable counting.</input>
        <output id="out">4-bit output representing the current count value.</output>
    </ports>
    <implementation>If the reset signal is active (!rst_n), the counter resets to 0. If valid_count is 1, the counter increments. When count reaches 11, it wraps to 0.</implementation>
</module>"""

FEWSHOT_VERILOG_COUNTER = """\
module counter_12(
    input rst_n,
    input clk,
    input valid_count,
    output reg [3:0] out
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            out <= 4'b0000;
        else if (valid_count) begin
            if (out == 4'd11)
                out <= 4'b0000;
            else
                out <= out + 1;
        end
    end
endmodule
"""

# ── Example 3: FSM with logic_description ──
FEWSHOT_XML_FSM = """\
<module id="fsm">
    <description>Implement a Mealy FSM that detects sequence 10011.</description>
    <ports>
        <input id="IN">Input signal.</input>
        <input id="CLK">Clock signal.</input>
        <input id="RST">Reset signal.</input>
        <output id="MATCH">Match output.</output>
    </ports>
    <parameter_description>
        <parameter id="s0" value="0">Initial state.</parameter>
        <parameter id="s1" value="1">After detecting 1.</parameter>
        <parameter id="s2" value="2">After 10.</parameter>
        <parameter id="s3" value="3">After 100.</parameter>
        <parameter id="s4" value="4">After 1001.</parameter>
    </parameter_description>
    <logic_description>
        <description>FSM with current state and next state logic.</description>
        <logic type="sequential_logic" id="ST_cr">Current state register, updated on posedge CLK.</logic>
        <logic type="combinational_logic" id="ST_nt">Next state logic based on IN and ST_cr.</logic>
        <logic type="combinational_logic" id="MATCH">Active when ST_cr is s4 and IN is 1.</logic>
    </logic_description>
    <implementation>Mealy FSM detecting 10011. MATCH=1 when sequence detected.</implementation>
</module>"""


# ══════════════════════════════════════════════════════════════
# 1. CONVERTER: Natural Language → COMBA XML Description
# ══════════════════════════════════════════════════════════════

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
   - `<parameter id="name" value="value">description</parameter>`
5. `<logic_description>` (optional) — Detailed signal-level behavior:
   - `<logic type="sequential_logic" id="signal">` — reg, updated in always @(posedge clk)
   - `<logic type="combinational_logic" id="signal">` — wire or always(*)
   - `<logic type="sequential_logic_operation" id="op">` — sequential operation block
   - `<logic type="combinational_logic_operation" id="op">` — assign statement
6. `<implementation>` — Detailed implementation description
7. `<task>` (optional) — Defaults to "Give me the complete Verilog code."

## Example 1: Simple combinational
```xml
""" + FEWSHOT_XML_ADDER + """
```

## Example 2: Sequential module
```xml
""" + FEWSHOT_XML_COUNTER + """
```

## Example 3: FSM with logic_description
```xml
""" + FEWSHOT_XML_FSM + """
```

Output ONLY the XML content, no markdown fences, no explanation.
"""

converterPromptTemplate = ChatPromptTemplate([
    ("system", CONVERTER_SYSTEM_PROMPT),
    ("placeholder", "{conversation}"),
    ("user", "{user_input}"),
])


# ══════════════════════════════════════════════════════════════
# 2. GENERATOR: COMBA XML Description → Verilog Code
# ══════════════════════════════════════════════════════════════

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

## Example 1: Combinational (adder_8bit)
XML:
```xml
""" + FEWSHOT_XML_ADDER + """
```
Verilog:
```verilog
""" + FEWSHOT_VERILOG_ADDER + """
```

## Example 2: Sequential (counter_12)
XML:
```xml
""" + FEWSHOT_XML_COUNTER + """
```
Verilog:
```verilog
""" + FEWSHOT_VERILOG_COUNTER + """
```

Return ONLY the Verilog code, no markdown fences, no explanation.
Ensure the file ends with a newline character.
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
