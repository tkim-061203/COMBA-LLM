"""
extraction_guard.py — Verilog Extraction Guard
================================================
Replaces patch-based approach with whole-file extraction.

3-stage pipeline (inspired by REFINE-Verilog):
  1. Over Context Detection  — detect incomplete/bloated output
  2. Generation Prompt Extraction — isolate code from LLM noise
  3. Logic Keywords Check — verify structural completeness

Usage:
    from extraction_guard import ExtractionGuard
    guard = ExtractionGuard()
    result = guard.extract(llm_raw_output, module_name="alu")
    if result.success:
        clean_code = result.code
    else:
        # result.failure_reason tells what went wrong
        # result.retry_prompt gives a follow-up prompt to re-query LLM
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────
# Data Types
# ─────────────────────────────────────────────

class FailureReason(Enum):
    NO_MODULE = "no_module_keyword_found"
    NO_ENDMODULE = "no_endmodule_keyword_found"
    MODULE_NAME_MISMATCH = "module_name_does_not_match_expected"
    OVER_CONTEXT = "output_too_long_or_repetitive"
    NO_LOGIC_KEYWORDS = "missing_assign_or_always_block"
    MULTIPLE_MODULES = "multiple_module_definitions_found"
    EMPTY_BODY = "module_body_is_empty"
    UNBALANCED_BEGIN_END = "unbalanced_begin_end_blocks"


@dataclass
class ExtractionResult:
    success: bool
    code: Optional[str] = None
    failure_reason: Optional[FailureReason] = None
    retry_prompt: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────
# Regex Patterns
# ─────────────────────────────────────────────

# Match module ... endmodule block (greedy for last endmodule)
MODULE_BLOCK_RE = re.compile(
    r'(module\s+\w+[\s\S]*?endmodule)',
    re.MULTILINE
)

# Match module declaration line
MODULE_DECL_RE = re.compile(
    r'module\s+(\w+)\s*[\(#]',
    re.MULTILINE
)

# Markdown code fence removal
CODE_FENCE_RE = re.compile(
    r'```(?:verilog|v|systemverilog)?\s*\n([\s\S]*?)```',
    re.MULTILINE
)

# Alpaca-style marker (used in fine-tuned models)
ALPACA_RESPONSE_RE = re.compile(
    r'###\s*Response:\s*\n([\s\S]*)',
    re.MULTILINE
)

# Logic keywords that indicate real behavioral code
LOGIC_KEYWORDS = {'always', 'always_comb', 'always_ff', 'always_latch', 'assign', 'initial'}

# Detect repetitive patterns (over-context)
REPETITIVE_LINE_THRESHOLD = 0.4  # >40% duplicate lines = over-context

# Max reasonable output length for RTLLM modules
MAX_OUTPUT_LINES = 500


# ─────────────────────────────────────────────
# Retry Prompt Templates
# ─────────────────────────────────────────────

RETRY_PROMPTS = {
    FailureReason.NO_MODULE: (
        "Your previous output did not contain a valid Verilog module. "
        "Please output the COMPLETE Verilog module starting with "
        "'module {module_name}' and ending with 'endmodule'. "
        "Output ONLY the Verilog code, no explanation."
    ),
    FailureReason.NO_ENDMODULE: (
        "Your previous output contains 'module' but is missing 'endmodule'. "
        "The module definition was incomplete or truncated. "
        "Please output the COMPLETE module from 'module' to 'endmodule'. "
        "Output ONLY the Verilog code, no explanation."
    ),
    FailureReason.MODULE_NAME_MISMATCH: (
        "Your previous output defined module '{found_name}' but the expected "
        "module name is '{module_name}'. Please regenerate with the correct "
        "module name '{module_name}'. Output ONLY the Verilog code."
    ),
    FailureReason.OVER_CONTEXT: (
        "Your previous output was too long or contained repetitive patterns. "
        "Please generate a concise Verilog module '{module_name}'. "
        "Avoid repeating wire/reg declarations. "
        "Output ONLY the Verilog code, no explanation."
    ),
    FailureReason.NO_LOGIC_KEYWORDS: (
        "Your previous output for module '{module_name}' compiled structurally "
        "but contained no behavioral logic (no 'assign', 'always', or 'initial' blocks). "
        "Please provide a COMPLETE implementation with actual logic. "
        "Output ONLY the Verilog code, no explanation."
    ),
    FailureReason.MULTIPLE_MODULES: (
        "Your previous output contained multiple module definitions. "
        "Please output ONLY the single module '{module_name}'. "
        "Do not include testbenches or helper modules. "
        "Output ONLY the Verilog code, no explanation."
    ),
    FailureReason.EMPTY_BODY: (
        "Your previous output for module '{module_name}' had an empty body "
        "with no logic between module declaration and endmodule. "
        "Please provide a COMPLETE implementation. "
        "Output ONLY the Verilog code, no explanation."
    ),
    FailureReason.UNBALANCED_BEGIN_END: (
        "Your previous output for module '{module_name}' has unbalanced "
        "begin/end blocks. Please carefully check all begin/end pairs "
        "and output the corrected COMPLETE module. "
        "Output ONLY the Verilog code, no explanation."
    ),
}


# ─────────────────────────────────────────────
# Main Class
# ─────────────────────────────────────────────

class ExtractionGuard:
    """
    3-stage extraction pipeline:
      Stage 1: Over Context Detection
      Stage 2: Generation Prompt Extraction (isolate module...endmodule)
      Stage 3: Logic Keywords Check + structural validation
    """

    def __init__(self, max_lines: int = MAX_OUTPUT_LINES):
        self.max_lines = max_lines

    def extract(
        self,
        raw_output: str,
        module_name: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Main entry point. Returns ExtractionResult with clean code or retry prompt.

        Args:
            raw_output: Raw LLM output string
            module_name: Expected module name (optional, for validation)
        """
        if not raw_output or not raw_output.strip():
            return self._fail(
                FailureReason.NO_MODULE,
                module_name=module_name
            )

        # ── Stage 1: Over Context Detection ──
        result = self._stage1_over_context(raw_output, module_name)
        if result is not None:
            return result

        # ── Stage 2: Generation Prompt Extraction ──
        code, result = self._stage2_extract_code(raw_output, module_name)
        if result is not None:
            return result

        # ── Stage 3: Logic Keywords Check + Structural Validation ──
        result = self._stage3_validate(code, module_name)
        if result is not None:
            return result

        # All checks passed
        return ExtractionResult(
            success=True,
            code=code,
            warnings=self._collect_warnings(code),
        )

    # ─────────────────────────────────────────
    # Stage 1: Over Context Detection
    # ─────────────────────────────────────────

    def _stage1_over_context(
        self, raw: str, module_name: Optional[str]
    ) -> Optional[ExtractionResult]:
        """Detect overly long or repetitive output."""
        lines = raw.strip().split('\n')

        # Check total length
        if len(lines) > self.max_lines:
            return self._fail(
                FailureReason.OVER_CONTEXT,
                module_name=module_name
            )

        # Check repetitive lines (symptom of LLM looping)
        if len(lines) > 20:
            stripped = [l.strip() for l in lines if l.strip()]
            if stripped:
                unique_ratio = len(set(stripped)) / len(stripped)
                if unique_ratio < (1 - REPETITIVE_LINE_THRESHOLD):
                    return self._fail(
                        FailureReason.OVER_CONTEXT,
                        module_name=module_name
                    )

        return None  # pass

    # ─────────────────────────────────────────
    # Stage 2: Generation Prompt Extraction
    # ─────────────────────────────────────────

    def _stage2_extract_code(
        self, raw: str, module_name: Optional[str]
    ) -> tuple[Optional[str], Optional[ExtractionResult]]:
        """
        Extract Verilog code from LLM noise.
        Priority: code fence > Alpaca marker > raw module block
        Returns (extracted_code, error_result_if_failed)
        """
        text = raw

        # Try extracting from markdown code fences first
        fence_match = CODE_FENCE_RE.search(text)
        if fence_match:
            text = fence_match.group(1)

        # Try Alpaca-style marker
        elif ALPACA_RESPONSE_RE.search(text):
            alpaca_match = ALPACA_RESPONSE_RE.search(text)
            text = alpaca_match.group(1)

        # Find all module...endmodule blocks
        blocks = MODULE_BLOCK_RE.findall(text)

        if not blocks:
            # Check if module keyword exists but no endmodule
            if re.search(r'\bmodule\b', text):
                return None, self._fail(
                    FailureReason.NO_ENDMODULE,
                    module_name=module_name
                )
            return None, self._fail(
                FailureReason.NO_MODULE,
                module_name=module_name
            )

        # If module_name given, try to find the matching block
        if module_name and len(blocks) > 1:
            matched = [b for b in blocks if re.search(
                rf'module\s+{re.escape(module_name)}\b', b
            )]
            if matched:
                code = matched[0]
            else:
                # Multiple modules, none match — report mismatch
                found_names = MODULE_DECL_RE.findall(text)
                return None, self._fail(
                    FailureReason.MODULE_NAME_MISMATCH,
                    module_name=module_name,
                    found_name=found_names[0] if found_names else "unknown"
                )
        elif len(blocks) > 1:
            # Multiple modules, no expected name — warn but take first
            code = blocks[0]
        else:
            code = blocks[0]

        # Validate module name if expected
        if module_name:
            decl_match = MODULE_DECL_RE.search(code)
            if decl_match:
                found = decl_match.group(1)
                if found != module_name:
                    return None, self._fail(
                        FailureReason.MODULE_NAME_MISMATCH,
                        module_name=module_name,
                        found_name=found
                    )

        return code.strip(), None

    # ─────────────────────────────────────────
    # Stage 3: Logic Keywords Check + Structural
    # ─────────────────────────────────────────

    def _stage3_validate(
        self, code: str, module_name: Optional[str]
    ) -> Optional[ExtractionResult]:
        """Validate extracted code has real logic and balanced structure."""

        # Check for empty body
        # Remove module declaration and endmodule, see if anything left
        body = re.sub(r'module\s+\w+[\s\S]*?;', '', code, count=1)
        body = re.sub(r'endmodule\s*$', '', body).strip()

        # Remove port/wire/reg declarations to check for actual logic
        logic_body = re.sub(
            r'^\s*(input|output|inout|wire|reg|integer|parameter|localparam|genvar)\b.*$',
            '', body, flags=re.MULTILINE
        ).strip()

        if not logic_body:
            return self._fail(
                FailureReason.EMPTY_BODY,
                module_name=module_name
            )

        # Logic keywords check
        has_logic = any(
            re.search(rf'\b{kw}\b', code) for kw in LOGIC_KEYWORDS
        )
        if not has_logic:
            return self._fail(
                FailureReason.NO_LOGIC_KEYWORDS,
                module_name=module_name
            )

        # Balanced begin/end check
        begin_count = len(re.findall(r'\bbegin\b', code))
        end_count = len(re.findall(r'\bend\b', code))
        # Note: 'end' also matches 'endmodule', 'endcase', etc.
        # So we only count standalone 'end' (not end*)
        end_standalone = len(re.findall(r'\bend\b(?!module|case|function|task|generate|primitive|table|specify|config)', code))

        if begin_count != end_standalone:
            return self._fail(
                FailureReason.UNBALANCED_BEGIN_END,
                module_name=module_name
            )

        return None  # pass

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    def _fail(
        self,
        reason: FailureReason,
        module_name: Optional[str] = None,
        found_name: Optional[str] = None,
    ) -> ExtractionResult:
        """Build failure result with retry prompt."""
        template = RETRY_PROMPTS.get(reason, "")
        retry = template.format(
            module_name=module_name or "unknown",
            found_name=found_name or "unknown",
        )
        return ExtractionResult(
            success=False,
            failure_reason=reason,
            retry_prompt=retry,
        )

    def _collect_warnings(self, code: str) -> list[str]:
        """Non-fatal warnings for the extracted code."""
        warnings = []

        # Check for common issues that won't prevent compilation
        if '`timescale' in code:
            warnings.append("Contains `timescale directive — may conflict with TB")

        if re.search(r'//.*TODO', code, re.IGNORECASE):
            warnings.append("Contains TODO comments — may indicate incomplete logic")

        if code.count('module') > 1:
            warnings.append("May contain sub-module definitions")

        return warnings


# ─────────────────────────────────────────────
# Convenience function
# ─────────────────────────────────────────────

def extract_verilog(raw_output: str, module_name: Optional[str] = None) -> ExtractionResult:
    """One-liner convenience wrapper."""
    return ExtractionGuard().extract(raw_output, module_name)


# ─────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    guard = ExtractionGuard()

    # Test 1: Clean code
    print("=== Test 1: Clean code ===")
    r = guard.extract("""
module adder_8bit(
    input [7:0] a, b,
    input cin,
    output [7:0] sum,
    output cout
);
    assign {cout, sum} = a + b + cin;
endmodule
""", module_name="adder_8bit")
    print(f"  success={r.success}, warnings={r.warnings}")

    # Test 2: Code with markdown fence + explanation
    print("\n=== Test 2: Markdown fence ===")
    r = guard.extract("""
Here is the corrected Verilog code:

```verilog
module alu(
    input [7:0] a, b,
    input [2:0] op,
    output reg [7:0] result
);
    always @(*) begin
        case(op)
            3'b000: result = a + b;
            3'b001: result = a - b;
            default: result = 8'b0;
        endcase
    end
endmodule
```

This fixes the missing case statement.
""", module_name="alu")
    print(f"  success={r.success}")
    if r.success:
        print(f"  code starts with: {r.code[:40]}...")

    # Test 3: No module keyword
    print("\n=== Test 3: No module ===")
    r = guard.extract("I cannot generate Verilog code for this.", module_name="alu")
    print(f"  success={r.success}, reason={r.failure_reason}")
    print(f"  retry_prompt={r.retry_prompt[:60]}...")

    # Test 4: Missing endmodule
    print("\n=== Test 4: Missing endmodule ===")
    r = guard.extract("module test(\n  input a\n);\n  assign b = a;", module_name="test")
    print(f"  success={r.success}, reason={r.failure_reason}")

    # Test 5: Empty body
    print("\n=== Test 5: Empty body ===")
    r = guard.extract("""
module empty(input a, output b);
endmodule
""", module_name="empty")
    print(f"  success={r.success}, reason={r.failure_reason}")

    # Test 6: Module name mismatch
    print("\n=== Test 6: Name mismatch ===")
    r = guard.extract("""
module wrong_name(input a, output b);
    assign b = a;
endmodule
""", module_name="correct_name")
    print(f"  success={r.success}, reason={r.failure_reason}")

    print("\n✅ All extraction guard tests completed.")
