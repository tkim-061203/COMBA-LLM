"""
pre_sc_check.py — Pre-Syntax-Check Structural Validator
=========================================================
Runs BEFORE Verilator to catch obvious structural issues.
Saves Verilator compile time and gives targeted retry prompts.

Checks:
  1. module / endmodule presence and pairing
  2. Port declaration completeness
  3. begin/end balance
  4. Common syntax patterns (missing semicolons at end of assign)
  5. Wire/reg type consistency (output used in always → must be reg)
  6. Sensitivity list presence for always blocks

Usage:
    from pre_sc_check import PreSCValidator
    validator = PreSCValidator()
    result = validator.validate(code, module_name="alu")
    if result.passed:
        # proceed to Verilator
    else:
        # result.issues contains fixable issues
        # result.auto_fix_prompt for LLM retry
        # result.auto_fixed_code if auto-fixable
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ─────────────────────────────────────────────
# Issue Severity
# ─────────────────────────────────────────────

class Severity(Enum):
    FATAL = "fatal"       # Will definitely fail Verilator
    WARNING = "warning"   # Likely to cause issues
    INFO = "info"         # Style issue, won't fail compile


# ─────────────────────────────────────────────
# Issue Types
# ─────────────────────────────────────────────

class IssueType(Enum):
    MISSING_MODULE = "missing_module"
    MISSING_ENDMODULE = "missing_endmodule"
    UNBALANCED_BEGIN_END = "unbalanced_begin_end"
    MISSING_SEMICOLON = "missing_semicolon_after_assign"
    OUTPUT_NOT_REG = "output_used_in_always_but_declared_as_wire"
    NO_SENSITIVITY_LIST = "always_block_missing_sensitivity_list"
    MISSING_PORT_DIRECTION = "port_missing_direction_declaration"
    DUPLICATE_MODULE = "duplicate_module_definition"
    EMPTY_ALWAYS_BLOCK = "always_block_with_no_body"
    BLOCKING_IN_SEQUENTIAL = "blocking_assignment_in_clocked_always"
    NONBLOCKING_IN_COMBINATIONAL = "nonblocking_in_combinational_always"
    UNDECLARED_SIGNAL_IN_ASSIGN = "possible_undeclared_signal"


@dataclass
class Issue:
    issue_type: IssueType
    severity: Severity
    line_num: Optional[int]
    description: str
    suggestion: str
    auto_fixable: bool = False


@dataclass
class PreSCResult:
    passed: bool                        # True if no FATAL issues
    issues: list[Issue] = field(default_factory=list)
    auto_fixed_code: Optional[str] = None   # If auto-fixable issues exist
    auto_fix_prompt: Optional[str] = None   # LLM retry prompt for non-auto-fixable
    fatal_count: int = 0
    warning_count: int = 0


# ─────────────────────────────────────────────
# Patterns
# ─────────────────────────────────────────────

# Always block with posedge/negedge → sequential
SEQUENTIAL_ALWAYS_RE = re.compile(
    r'always\s*@\s*\(\s*(posedge|negedge)\s+\w+',
    re.MULTILINE
)

# Always block with * or signal list → combinational
COMBINATIONAL_ALWAYS_RE = re.compile(
    r'always\s*@\s*\(\s*(\*|[^)]*(?!posedge|negedge)[^)]*)\s*\)',
    re.MULTILINE
)

# Always without sensitivity list (Verilog-2001 issue)
ALWAYS_NO_SENS_RE = re.compile(
    r'always\s+begin',
    re.MULTILINE
)

# Output port names
OUTPUT_PORT_RE = re.compile(
    r'output\s+(?:reg\s+)?(?:\[[\d:]+\]\s+)?(\w+)',
    re.MULTILINE
)

# Output declared as reg
OUTPUT_REG_RE = re.compile(
    r'output\s+reg\s+',
    re.MULTILINE
)

# Blocking assignment in always block: =
BLOCKING_ASSIGN_RE = re.compile(
    r'(\w+)\s*=[^=]',
)

# Non-blocking assignment: <=
NONBLOCKING_ASSIGN_RE = re.compile(
    r'(\w+)\s*<=',
)


# ─────────────────────────────────────────────
# Main Validator
# ─────────────────────────────────────────────

class PreSCValidator:
    """
    Pre-Verilator structural validation.
    Catches obvious issues that would waste compile cycles.
    """

    def validate(self, code: str, module_name: Optional[str] = None) -> PreSCResult:
        issues: list[Issue] = []
        lines = code.split('\n')

        # ── Check 1: module/endmodule ──
        self._check_module_structure(code, lines, module_name, issues)

        # ── Check 2: begin/end balance ──
        self._check_begin_end_balance(code, lines, issues)

        # ── Check 3: Always block issues ──
        self._check_always_blocks(code, lines, issues)

        # ── Check 4: Output reg consistency ──
        self._check_output_reg(code, lines, issues)

        # ── Check 5: Common syntax patterns ──
        self._check_common_syntax(code, lines, issues)

        # Build result
        fatal_count = sum(1 for i in issues if i.severity == Severity.FATAL)
        warning_count = sum(1 for i in issues if i.severity == Severity.WARNING)

        result = PreSCResult(
            passed=(fatal_count == 0),
            issues=issues,
            fatal_count=fatal_count,
            warning_count=warning_count,
        )

        # Try auto-fix for simple issues
        if issues and all(i.auto_fixable for i in issues if i.severity == Severity.FATAL):
            result.auto_fixed_code = self._try_auto_fix(code, issues)

        # Build LLM retry prompt for non-auto-fixable
        if not result.passed and result.auto_fixed_code is None:
            result.auto_fix_prompt = self._build_retry_prompt(code, issues, module_name)

        return result

    # ─────────────────────────────────────────
    # Individual Checks
    # ─────────────────────────────────────────

    def _check_module_structure(self, code, lines, module_name, issues):
        """Check module/endmodule presence and pairing."""
        module_count = len(re.findall(r'\bmodule\b', code))
        endmodule_count = len(re.findall(r'\bendmodule\b', code))

        if module_count == 0:
            issues.append(Issue(
                IssueType.MISSING_MODULE, Severity.FATAL, None,
                "No 'module' keyword found",
                "Add module declaration at the beginning",
            ))
            return

        if endmodule_count == 0:
            issues.append(Issue(
                IssueType.MISSING_ENDMODULE, Severity.FATAL, None,
                "No 'endmodule' keyword found — code may be truncated",
                "Add 'endmodule' at the end",
                auto_fixable=True,
            ))

        if module_count > 1:
            issues.append(Issue(
                IssueType.DUPLICATE_MODULE, Severity.WARNING, None,
                f"Found {module_count} module definitions — expected 1",
                "Remove extra module definitions (testbench, helpers)",
            ))

        if module_count != endmodule_count:
            issues.append(Issue(
                IssueType.MISSING_ENDMODULE, Severity.FATAL, None,
                f"Mismatched: {module_count} module(s) vs {endmodule_count} endmodule(s)",
                "Ensure each 'module' has a matching 'endmodule'",
            ))

    def _check_begin_end_balance(self, code, lines, issues):
        """Check begin/end block balance."""
        begin_count = len(re.findall(r'\bbegin\b', code))
        # Count 'end' not followed by module/case/function/etc
        end_standalone = len(re.findall(
            r'\bend\b(?!module|case|function|task|generate|primitive|table|specify|config)',
            code
        ))

        if begin_count != end_standalone:
            # Find approximate location of mismatch
            depth = 0
            mismatch_line = None
            for i, line in enumerate(lines):
                depth += len(re.findall(r'\bbegin\b', line))
                depth -= len(re.findall(
                    r'\bend\b(?!module|case|function|task|generate|primitive|table|specify|config)',
                    line
                ))
                if depth < 0:
                    mismatch_line = i + 1
                    break

            issues.append(Issue(
                IssueType.UNBALANCED_BEGIN_END, Severity.FATAL,
                mismatch_line,
                f"Unbalanced: {begin_count} begin vs {end_standalone} end",
                "Check nested if/else and case blocks for missing begin/end",
            ))

    def _check_always_blocks(self, code, lines, issues):
        """Check always block issues."""
        # Always without sensitivity list
        for match in ALWAYS_NO_SENS_RE.finditer(code):
            line_num = code[:match.start()].count('\n') + 1
            issues.append(Issue(
                IssueType.NO_SENSITIVITY_LIST, Severity.FATAL,
                line_num,
                f"Line {line_num}: 'always begin' without sensitivity list",
                "Use 'always @(*)' for combinational or 'always @(posedge clk)' for sequential",
            ))

        # Empty always blocks
        empty_always = re.findall(
            r'always\s*@\s*\([^)]*\)\s*;\s*$',
            code, re.MULTILINE
        )
        for match in empty_always:
            issues.append(Issue(
                IssueType.EMPTY_ALWAYS_BLOCK, Severity.WARNING, None,
                "Found always block terminated by semicolon (empty body)",
                "Remove the semicolon and add begin/end with logic",
            ))

        # Blocking in sequential (common mistake)
        seq_blocks = list(SEQUENTIAL_ALWAYS_RE.finditer(code))
        for seq_match in seq_blocks:
            # Find the block content after this always
            block_start = seq_match.end()
            # Simple heuristic: find next 'end' at same depth
            block_text = code[block_start:block_start + 500]  # rough window

            # Check for blocking assignment (= without <=)
            # This is a heuristic — may have false positives from comparisons
            assign_lines = re.findall(r'^\s*(\w+)\s*=\s*[^=]', block_text, re.MULTILINE)
            if assign_lines:
                # Filter out known non-assignment patterns
                real_assigns = [a for a in assign_lines
                                if a not in ('if', 'else', 'case', 'for', 'while', 'integer')]
                if real_assigns:
                    issues.append(Issue(
                        IssueType.BLOCKING_IN_SEQUENTIAL, Severity.WARNING, None,
                        f"Blocking assignment (=) found in clocked always block for signals: {real_assigns[:3]}",
                        "Use non-blocking (<=) in sequential always blocks",
                    ))

    def _check_output_reg(self, code, lines, issues):
        """Check that outputs used in always blocks are declared as reg."""
        # Get all output names
        outputs = OUTPUT_PORT_RE.findall(code)
        has_output_reg = bool(OUTPUT_REG_RE.search(code))

        # Check if outputs appear on LHS of assignments in always blocks
        always_blocks = re.findall(
            r'always\s*@[\s\S]*?(?:end\b)',
            code
        )
        for block in always_blocks:
            for out in outputs:
                # Check if output is assigned in this always block
                if re.search(rf'\b{re.escape(out)}\s*<=', block) or \
                   re.search(rf'\b{re.escape(out)}\s*=[^=]', block):
                    # Check if this output is declared as reg
                    if not re.search(
                        rf'output\s+reg\s+(?:\[[\d:]+\]\s+)?{re.escape(out)}\b', code
                    ) and not re.search(
                        rf'reg\s+(?:\[[\d:]+\]\s+)?{re.escape(out)}\b', code
                    ):
                        issues.append(Issue(
                            IssueType.OUTPUT_NOT_REG, Severity.FATAL, None,
                            f"Output '{out}' assigned in always block but not declared as reg",
                            f"Change 'output ... {out}' to 'output reg ... {out}'",
                        ))

    def _check_common_syntax(self, code, lines, issues):
        """Check common syntax issues."""
        for i, line in enumerate(lines):
            stripped = line.strip()

            # Assign without semicolon (but not if it's a multiline)
            if stripped.startswith('assign ') and not stripped.endswith(';') \
               and not stripped.endswith(','):
                # Check if next line continues
                if i + 1 < len(lines) and not lines[i + 1].strip().startswith(('?', ':', '|', '&', '+', '-', '^')):
                    issues.append(Issue(
                        IssueType.MISSING_SEMICOLON, Severity.WARNING,
                        i + 1,
                        f"Line {i+1}: 'assign' statement may be missing semicolon",
                        "Add ';' at the end of the assign statement",
                    ))

    # ─────────────────────────────────────────
    # Auto-fix (for simple cases)
    # ─────────────────────────────────────────

    def _try_auto_fix(self, code: str, issues: list[Issue]) -> Optional[str]:
        """Try to auto-fix simple issues. Returns fixed code or None."""
        fixed = code

        for issue in issues:
            if not issue.auto_fixable:
                continue

            if issue.issue_type == IssueType.MISSING_ENDMODULE:
                if not fixed.rstrip().endswith('endmodule'):
                    fixed = fixed.rstrip() + '\nendmodule\n'

        # Verify fix didn't break anything
        if fixed != code:
            return fixed
        return None

    # ─────────────────────────────────────────
    # LLM Retry Prompt
    # ─────────────────────────────────────────

    def _build_retry_prompt(
        self, code: str, issues: list[Issue], module_name: Optional[str]
    ) -> str:
        """Build targeted retry prompt based on specific issues found."""
        fatal_issues = [i for i in issues if i.severity == Severity.FATAL]

        issue_text = "\n".join(
            f"  - {i.description} → {i.suggestion}"
            for i in fatal_issues
        )

        return (
            f"Your Verilog code for module '{module_name or 'unknown'}' has "
            f"structural issues that will cause compilation failure:\n\n"
            f"{issue_text}\n\n"
            f"Please fix these issues and output the COMPLETE corrected module.\n"
            f"Output ONLY Verilog code, no explanation."
        )


# ─────────────────────────────────────────────
# Convenience
# ─────────────────────────────────────────────

def pre_validate(code: str, module_name: Optional[str] = None) -> PreSCResult:
    """One-liner convenience wrapper."""
    return PreSCValidator().validate(code, module_name)


# ─────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    validator = PreSCValidator()

    # Test 1: Clean code
    print("=== Test 1: Clean code ===")
    r = validator.validate("""
module adder_8bit(
    input [7:0] a, b,
    input cin,
    output [7:0] sum,
    output cout
);
    assign {cout, sum} = a + b + cin;
endmodule
""", module_name="adder_8bit")
    print(f"  passed={r.passed}, fatals={r.fatal_count}, warnings={r.warning_count}")

    # Test 2: Missing endmodule
    print("\n=== Test 2: Missing endmodule ===")
    r = validator.validate("""
module test(input a, output b);
    assign b = a;
""", module_name="test")
    print(f"  passed={r.passed}, fatals={r.fatal_count}")
    if r.auto_fixed_code:
        print(f"  auto_fixed ends with: ...{r.auto_fixed_code[-30:]}")

    # Test 3: Output not reg
    print("\n=== Test 3: Output not declared as reg ===")
    r = validator.validate("""
module counter(
    input clk, rst,
    output [3:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 4'b0;
        else
            count <= count + 1;
    end
endmodule
""", module_name="counter")
    print(f"  passed={r.passed}")
    for issue in r.issues:
        print(f"  issue: {issue.issue_type.value} ({issue.severity.value})")

    # Test 4: Unbalanced begin/end
    print("\n=== Test 4: Unbalanced begin/end ===")
    r = validator.validate("""
module fsm(input clk, rst, input x, output reg y);
    reg [1:0] state;
    always @(posedge clk) begin
        if (rst) begin
            state <= 2'b00;
        else begin
            state <= state + 1;
        end
    end
endmodule
""", module_name="fsm")
    print(f"  passed={r.passed}")
    for issue in r.issues:
        if issue.severity == Severity.FATAL:
            print(f"  FATAL: {issue.description}")

    # Test 5: Always without sensitivity list
    print("\n=== Test 5: Always without sensitivity ===")
    r = validator.validate("""
module bad(input a, output reg b);
    always begin
        b = a;
    end
endmodule
""", module_name="bad")
    print(f"  passed={r.passed}")
    for issue in r.issues:
        print(f"  issue: {issue.description}")

    # Test 6: Blocking in sequential
    print("\n=== Test 6: Blocking in sequential ===")
    r = validator.validate("""
module seq(input clk, input [7:0] d, output reg [7:0] q);
    always @(posedge clk) begin
        q = d;
    end
endmodule
""", module_name="seq")
    print(f"  passed={r.passed}, warnings={r.warning_count}")
    for issue in r.issues:
        if issue.severity == Severity.WARNING:
            print(f"  WARNING: {issue.description}")

    print("\n✅ All pre-SC validation tests completed.")
