"""
COMBA-PROMPT: Generation Prompt Template (Process ⓪)
Updated: Added behavioral/RTL constraint to prevent sub-module hallucination.
"""

GENERATOR_SYSTEM_PROMPT = """\
You are a professional Verilog designer.
Generate Verilog RTL code based on the following XML specification.
Output ONLY the Verilog code, no explanation.

## CONSTRAINTS
- Use ONLY behavioral/RTL-level descriptions (assign, always blocks, operators).
- Do NOT instantiate any sub-modules unless their full implementation is explicitly provided in the specification.
- If the description mentions "bit-level adders", "sub-components", or "hierarchical modules", implement the equivalent logic INLINE using arithmetic/bitwise operators (+, -, &, |, ^, ~).
- All logic must be SELF-CONTAINED within a single module definition.
- Do NOT assume the existence of any external module (e.g., full_adder, adder_4, half_adder).
"""

GENERATOR_USER_TEMPLATE = """\
{xml_description}
"""


def build_generation_prompt(xml_description: str) -> list[dict]:
    """Build messages for Process 0 (Generation).
    
    Args:
        xml_description: XML-based module specification.
    
    Returns:
        List of message dicts for LLM API call.
    """
    return [
        {"role": "system", "content": GENERATOR_SYSTEM_PROMPT},
        {"role": "user", "content": GENERATOR_USER_TEMPLATE.format(
            xml_description=xml_description
        )},
    ]
