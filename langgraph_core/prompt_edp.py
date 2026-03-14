"""
COMBA-PROMPT: Exception-Debugging Prompt Template (EDP)
Updated: Added error-aware constraint injection for "Cannot find module" errors.
"""

import re

EDP_SYSTEM_PROMPT = """\
You are a Verilog syntax debugging expert.
You receive a Verilog module that failed Verilator syntax checking.
Your task is to fix the TOPMOST error precisely.

## Rules
1. Fix ONLY the topmost error. Other errors may cascade from it.
2. Preserve the module name, port names, and overall architecture.
3. Common Verilator errors and fixes:
   - "Signal not found" → declare the signal as wire/reg
   - "Width mismatch" / "WIDTHTRUNC" → adjust signal widths
   - "PINMISSING" → add the missing port connection
   - "MULTIDRIVEN" → remove duplicate drivers
   - "UNDRIVEN" → ensure all signals are driven
4. Return ONLY the complete fixed Verilog code, no explanation.
5. Do NOT wrap in markdown code fences.
"""

# Constraint injected when error classifier detects missing sub-module
MISSING_MODULE_CONSTRAINT = """\

## CRITICAL CONSTRAINT (Missing Sub-module Detected)
The error is caused by instantiating a sub-module that does NOT exist.
You MUST:
- REMOVE ALL sub-module instantiations (e.g., adder_4, full_adder, half_adder).
- REWRITE the logic using BEHAVIORAL style: assign statements or always blocks.
- Use arithmetic/bitwise operators (+, -, &, |, ^, ~) to implement equivalent logic INLINE.
- The entire design must be SELF-CONTAINED in a single module.
- Do NOT instantiate ANY external module.
"""

EDP_USER_TEMPLATE = """\
## Module: {module_name}
## Phase: Syntax Check | Trial {trial}/{max_trial}

### Current Verilog Code
```verilog
{gvd}
```

### Topmost Verilator Error
  Type: {exceptionType}
  Title: {exceptionTitle}
  Content: {exceptionContent}
  Location: {logContent}

### Additional Context
{custom_vector}

Fix the topmost error and return the complete corrected Verilog code.
"""

# Regex pattern to detect "Cannot find file containing module" errors
MISSING_MODULE_PATTERN = re.compile(
    r"Cannot find file containing module", re.IGNORECASE
)


def classify_error_needs_behavioral(sc_log: str) -> bool:
    """Check if syntax error is caused by missing sub-module instantiation.
    
    Args:
        sc_log: Full syntax compilation log from Verilator.
        
    Returns:
        True if error is "Cannot find module" type.
    """
    return bool(MISSING_MODULE_PATTERN.search(sc_log))


def build_edp_prompt(
    module_name: str,
    gvd: str,
    exceptionType: str,
    exceptionTitle: str,
    exceptionContent: str,
    logContent: str,
    custom_vector: str,
    sc_log: str,
    trial: int = 1,
    max_trial: int = 10,
) -> list[dict]:
    """Build messages for EDP (Syntax Debug).
    
    If error classifier detects missing sub-module, injects behavioral
    constraint into system prompt to force LLM to rewrite in RTL style.
    
    Args:
        module_name: Name of the Verilog module.
        gvd: Current Generated Verilog Design code.
        exceptionType: Error or Warning.
        exceptionTitle: e.g., WIDTHEXPAND, etc.
        exceptionContent: Description of the error.
        logContent: Location in code.
        custom_vector: Additional Verilator docs context.
        sc_log: Full syntax compilation log.
        trial: Current trial number.
        max_trial: Maximum trials allowed.
    
    Returns:
        List of message dicts for LLM API call.
    """
    system = EDP_SYSTEM_PROMPT
    
    # Error classifier: inject behavioral constraint if missing module
    if classify_error_needs_behavioral(sc_log):
        system += MISSING_MODULE_CONSTRAINT
    
    user = EDP_USER_TEMPLATE.format(
        module_name=module_name,
        gvd=gvd,
        exceptionType=exceptionType,
        exceptionTitle=exceptionTitle,
        exceptionContent=exceptionContent,
        logContent=logContent,
        custom_vector=custom_vector,
        trial=trial,
        max_trial=max_trial,
    )
    
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
