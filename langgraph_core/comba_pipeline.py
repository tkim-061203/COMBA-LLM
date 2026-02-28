"""
COMBA-PROMPT Full Verification Pipeline — LangGraph Implementation.

Track 1: 7 nodes, 5 conditional edges, Rollback Manager, EDTM, Iteration Control.

Flow:
  NL → [Converter] → XML → [Generator] → Verilog (GVD)
    → [SC] → pass? → [TB] → pass? → END ✅
              ↓ fail          ↓ fail
         [TED_SC]→[Correcter]→[SC]  (loop)
                          [TED_TB]→[Correcter]→[SC]  (loop)

Usage:
  # With real LLM
  python comba_pipeline.py "Design an 8-bit adder"

  # E2E test with stub
  python -m pytest test_pipeline.py -v
"""

import os
import re
import json
import subprocess
import shutil
import tempfile
from typing import Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END

from prompts import converterPromptTemplate, generatorPromptTemplate, correcterPromptTemplate

# ──────────────────────────────────────────────────────────────
# Configuration Constants
# ──────────────────────────────────────────────────────────────
MAX_SC_TRIALS = 10       # Max syntax-check correction cycles
MAX_TS_TRIALS = 5        # Max testbench correction cycles
MAX_TOTAL_ITER = 20      # Absolute hard cap on total iterations
EDTM_MAX_RETRIES = 3     # Max retries for the same exception signature

# Verilator flags matching the original Makefile
VERILATOR_WNO = ["DECLFILENAME"]
VERILATOR_WERROR = ["UNDRIVEN", "MULTIDRIVEN"]


# ──────────────────────────────────────────────────────────────
# 1. COMBAState — TypedDict with ~20 fields
# ──────────────────────────────────────────────────────────────
class COMBAState(TypedDict):
    # ── Input/Output ──
    nl_input: str                              # Natural language description
    xml_description: Optional[str]             # COMBA XML output
    module_name: Optional[str]                 # Extracted module name

    # ── Generated Verilog ──
    gvd: Optional[str]                         # Generated Verilog Description (current)
    sgvd: Optional[str]                        # Saved GVD (rollback snapshot)

    # ── Syntax Check (SC) ──
    sc_log: Optional[str]                      # SC raw log output
    sc_exception: Optional[str]                # Topmost parsed SC exception
    sc_exception_count: int                    # Number of SC exceptions in current run
    sc_prev_exception_count: int               # Exception count before correction

    # ── Testbench Simulation (TS) ──
    tb_log: Optional[str]                      # TB simulation raw log
    tb_failure: Optional[str]                  # Topmost parsed TB failure

    # ── Debugging Prompts ──
    edp: Optional[str]                         # Exception Debugging Prompt (from SC)
    tdp: Optional[str]                         # Testbench Debugging Prompt (from TB)

    # ── Control ──
    edtm: dict                                 # Exception-Debugging Trial Management
    phase: str                                 # Current phase: "sc" or "ts"
    sc_trial: int                              # SC trial counter
    ts_trial: int                              # TS trial counter
    total_iter: int                            # Total iteration counter
    rollback_triggered: bool                   # Rollback triggered this iteration?

    # ── Result ──
    final_status: Optional[str]                # "pass", "fail_sc", "fail_ts", "max_iter"
    error: Optional[str]                       # Runtime error message
    work_dir: Optional[str]                    # Working directory for Verilator


def make_initial_state(nl_input: str = "", module_name: str = "") -> COMBAState:
    """Create a fresh initial state with all fields zeroed."""
    return COMBAState(
        nl_input=nl_input,
        xml_description=None,
        module_name=module_name or None,
        gvd=None,
        sgvd=None,
        sc_log=None,
        sc_exception=None,
        sc_exception_count=0,
        sc_prev_exception_count=0,
        tb_log=None,
        tb_failure=None,
        edp=None,
        tdp=None,
        edtm={},
        phase="sc",
        sc_trial=0,
        ts_trial=0,
        total_iter=0,
        rollback_triggered=False,
        final_status=None,
        error=None,
        work_dir=None,
    )


# ──────────────────────────────────────────────────────────────
# 2. Seven Nodes
# ──────────────────────────────────────────────────────────────
class COMBANodes:
    """
    Encapsulates the 7 pipeline nodes.

    Args:
        llm: A LangChain-compatible chat model (or StubLLM for testing).
    """

    def __init__(self, llm):
        self._llm = llm

    # ──────────────────────────────────────────────────────────
    # Node 1: Converter — NL → XML
    # ──────────────────────────────────────────────────────────
    def node_converter(self, state: COMBAState) -> dict:
        """Convert natural language description to COMBA XML format."""
        print("\n" + "=" * 60)
        print("🔄 NODE: Converter (NL → XML)")
        print("=" * 60)

        # If XML already provided, skip
        if state.get("xml_description"):
            print("[SKIP] XML already present.")
            return {}

        result = converterPromptTemplate.invoke({
            "user_input": state["nl_input"],
            "conversation": [],
        })
        response = self._llm.invoke(result)
        xml_text = response.content.strip()

        # Clean markdown fences if LLM wraps them
        if xml_text.startswith("```"):
            lines = xml_text.split("\n")
            xml_text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        # Extract module name from XML
        match = re.search(r'<module\s+id="([^"]+)"', xml_text)
        module_name = match.group(1) if match else "unknown_module"

        print(f"  ✅ Generated XML for module: {module_name}")

        return {
            "xml_description": xml_text,
            "module_name": module_name,
        }

    # ──────────────────────────────────────────────────────────
    # Node 2: Generator — XML → Verilog
    # ──────────────────────────────────────────────────────────
    def node_generator(self, state: COMBAState) -> dict:
        """Generate Verilog code from COMBA XML description."""
        print("\n" + "=" * 60)
        print("⚡ NODE: Generator (XML → Verilog)")
        print("=" * 60)

        xml_desc = state["xml_description"]
        result = generatorPromptTemplate.invoke({
            "user_input": xml_desc,
            "conversation": [],
        })
        response = self._llm.invoke(result)
        content = response.content.strip()

        # Extract Verilog code — try JSON first, fallback to markdown/raw
        code = self._extract_verilog(content)

        # Ensure trailing newline (Verilator EOFNEWLINE)
        if code and not code.endswith("\n"):
            code += "\n"

        print(f"  ✅ Generated {len(code.splitlines())} lines of Verilog")

        return {
            "gvd": code,
            "sgvd": code,          # initial snapshot for rollback
            "phase": "sc",
            "sc_trial": 0,
            "ts_trial": 0,
            "total_iter": 0,
        }

    # ──────────────────────────────────────────────────────────
    # Node 3: Syntax Check — Verilator --lint-only
    # ──────────────────────────────────────────────────────────
    def node_syntax_check(self, state: COMBAState) -> dict:
        """Run Verilator lint-only syntax check on current GVD."""
        print("\n" + "=" * 60)
        print(f"🔍 NODE: Syntax Check (SC trial #{state['sc_trial'] + 1})")
        print("=" * 60)

        module_name = state["module_name"]
        gvd = state["gvd"]

        # Create temp work dir, write the .v file
        work_dir = state.get("work_dir")
        if not work_dir:
            work_dir = tempfile.mkdtemp(prefix=f"comba_{module_name}_")

        verilog_path = os.path.join(work_dir, f"{module_name}.v")
        with open(verilog_path, "w", encoding="utf-8") as f:
            f.write(gvd)

        # Build verilator command
        wno_flags = [f"-Wno-{w}" for w in VERILATOR_WNO]
        werror_flags = [f"-Werror-{w}" for w in VERILATOR_WERROR]
        cmd = [
            "verilator",
            "--lint-only",
            "-Wall",
            "-Wno-fatal",
            "--x-assign", "0",
            "--x-initial", "0",
            *wno_flags,
            *werror_flags,
            "-cc",
            f"{module_name}.v",
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            sc_log = result.stderr + result.stdout
        except FileNotFoundError:
            sc_log = "%Error: verilator not found in PATH"
        except subprocess.TimeoutExpired:
            sc_log = "%Error: verilator timed out after 30s"

        # Count errors (lines starting with %Error)
        error_lines = [
            line for line in sc_log.splitlines()
            if line.strip().startswith("%Error")
            and "Exiting due to" not in line
        ]
        exception_count = len(error_lines)

        print(f"  SC log: {len(sc_log.splitlines())} lines, {exception_count} errors")

        return {
            "sc_log": sc_log,
            "sc_exception_count": exception_count,
            "sc_trial": state["sc_trial"] + 1,
            "total_iter": state["total_iter"] + 1,
            "work_dir": work_dir,
        }

    # ──────────────────────────────────────────────────────────
    # Node 4: TED Syntax — Parse topmost SC error → EDP
    # ──────────────────────────────────────────────────────────
    def node_ted_syntax(self, state: COMBAState) -> dict:
        """
        Topmost Exception Detection for Syntax Check.
        Parse sc_log → extract topmost %Error → create EDP.
        Update EDTM tracker.
        """
        print("\n" + "=" * 60)
        print("🔎 NODE: TED Syntax (Parse topmost SC error)")
        print("=" * 60)

        sc_log = state["sc_log"] or ""
        edtm = dict(state.get("edtm", {}))   # shallow copy

        # Extract topmost %Error line (first non-"Exiting" error)
        topmost_error = None
        for line in sc_log.splitlines():
            stripped = line.strip()
            if stripped.startswith("%Error") and "Exiting due to" not in stripped:
                topmost_error = stripped
                break

        if not topmost_error:
            print("  ⚠️ No parseable error found in SC log")
            return {
                "sc_exception": None,
                "edp": None,
                "phase": "sc",
            }

        # Create exception signature for EDTM (normalize line numbers)
        sig = re.sub(r':\d+:', ':N:', topmost_error)
        sig = re.sub(r'\s+', ' ', sig).strip()

        # Update EDTM counter
        edtm[sig] = edtm.get(sig, 0) + 1

        # Check if this exception has been retried too many times
        if edtm[sig] > EDTM_MAX_RETRIES:
            print(f"  ⛔ EDTM: Exception seen {edtm[sig]} times, marking unresolvable")
            # Format EDP to indicate the issue so the correcter tries a different approach
            edp = (
                f"[EDTM WARNING: This error has been seen {edtm[sig]} times. "
                f"Previous fixes did not resolve it. Try a fundamentally different approach.]\n"
                f"Topmost Verilator error:\n{topmost_error}"
            )
        else:
            edp = f"Topmost Verilator error:\n{topmost_error}"

        print(f"  📋 EDP: {topmost_error[:80]}...")
        print(f"  📊 EDTM count for this sig: {edtm[sig]}")

        return {
            "sc_exception": topmost_error,
            "edp": edp,
            "edtm": edtm,
            "phase": "sc",
        }

    # ──────────────────────────────────────────────────────────
    # Node 5: Correcter — Fix code using EDP or TDP
    # ──────────────────────────────────────────────────────────
    def node_correcter(self, state: COMBAState) -> dict:
        """
        Correcter node with Rollback Manager.
        Takes EDP (SC phase) or TDP (TS phase) + current GVD → fix.
        If resulting code is worse (more exceptions), rollback.
        """
        print("\n" + "=" * 60)
        print(f"🔧 NODE: Correcter (phase={state['phase']})")
        print("=" * 60)

        phase = state["phase"]
        current_gvd = state["gvd"]
        error_desc = state["edp"] if phase == "sc" else state["tdp"]

        if not error_desc:
            print("  ⚠️ No error description available, skipping correction")
            return {}

        # ── Rollback Manager: Save snapshot ──
        sgvd = current_gvd
        sc_prev_exception_count = state["sc_exception_count"]

        # ── Call LLM to fix ──
        result = correcterPromptTemplate.invoke({
            "verilog_code": current_gvd,
            "error_description": error_desc,
            "phase": phase,
        })
        response = self._llm.invoke(result)
        fixed_code = response.content.strip()

        # Clean markdown fences
        fixed_code = self._extract_verilog(fixed_code)

        # Ensure trailing newline
        if fixed_code and not fixed_code.endswith("\n"):
            fixed_code += "\n"

        # If the LLM returned empty or very short code, don't apply
        if not fixed_code or len(fixed_code.strip()) < 20:
            print("  ⚠️ Correcter returned invalid code, keeping previous version")
            return {"rollback_triggered": True}

        print(f"  ✅ Correcter produced {len(fixed_code.splitlines())} lines")

        return {
            "gvd": fixed_code,
            "sgvd": sgvd,
            "sc_prev_exception_count": sc_prev_exception_count,
            "rollback_triggered": False,
        }

    # ──────────────────────────────────────────────────────────
    # Node 6: Testbench Simulation — Verilator full build+run
    # ──────────────────────────────────────────────────────────
    def node_tb_sim(self, state: COMBAState) -> dict:
        """Run full Verilator build + testbench simulation."""
        print("\n" + "=" * 60)
        print(f"🧪 NODE: TB Simulation (TS trial #{state['ts_trial'] + 1})")
        print("=" * 60)

        module_name = state["module_name"]
        work_dir = state["work_dir"]
        gvd = state["gvd"]

        # Write current GVD to work dir
        verilog_path = os.path.join(work_dir, f"{module_name}.v")
        with open(verilog_path, "w", encoding="utf-8") as f:
            f.write(gvd)

        # Copy testbench if not already there
        # Look for tb.cpp in the modules directory
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tb_src = os.path.join(project_root, "modules", module_name, "tb.cpp")
        tb_dst = os.path.join(work_dir, "tb.cpp")
        if os.path.isfile(tb_src) and not os.path.isfile(tb_dst):
            shutil.copy2(tb_src, tb_dst)

        wno_flags = [f"-Wno-{w}" for w in VERILATOR_WNO]
        werror_flags = [f"-Werror-{w}" for w in VERILATOR_WERROR]

        # Step 1: Verilator compile
        verilate_cmd = [
            "verilator",
            "-Wall", "-Wno-fatal",
            "--trace",
            "--x-assign", "0", "--x-initial", "0",
            "-cc", "--top-module", module_name,
            f"{module_name}.v",
            "--exe", "tb.cpp",
            *wno_flags,
            *werror_flags,
        ]

        tb_log_parts = []
        try:
            # Verilate
            r1 = subprocess.run(
                verilate_cmd, cwd=work_dir,
                capture_output=True, text=True, timeout=60,
            )
            tb_log_parts.append(f"[VERILATE]\n{r1.stderr}{r1.stdout}")

            if r1.returncode != 0:
                tb_log_parts.append("[VERILATE FAILED]")
                return {
                    "tb_log": "\n".join(tb_log_parts),
                    "tb_failure": "Verilator compilation failed during TB build",
                    "ts_trial": state["ts_trial"] + 1,
                    "total_iter": state["total_iter"] + 1,
                    "phase": "ts",
                }

            # Step 2: make binary
            obj_dir = os.path.join(work_dir, "obj_dir")
            make_cmd = ["make", "-C", obj_dir, "-f", f"V{module_name}.mk", f"V{module_name}"]
            r2 = subprocess.run(
                make_cmd, cwd=work_dir,
                capture_output=True, text=True, timeout=120,
            )
            tb_log_parts.append(f"[MAKE]\n{r2.stderr}{r2.stdout}")

            if r2.returncode != 0:
                tb_log_parts.append("[MAKE FAILED]")
                return {
                    "tb_log": "\n".join(tb_log_parts),
                    "tb_failure": "Make failed during TB binary build",
                    "ts_trial": state["ts_trial"] + 1,
                    "total_iter": state["total_iter"] + 1,
                    "phase": "ts",
                }

            # Step 3: run testbench binary
            binary = os.path.join(obj_dir, f"V{module_name}")
            if os.name == "nt":
                binary += ".exe"

            r3 = subprocess.run(
                [binary], cwd=work_dir,
                capture_output=True, text=True, timeout=60,
            )
            tb_log_parts.append(f"[RUN]\n{r3.stderr}{r3.stdout}")

            if r3.returncode != 0:
                tb_log_parts.append(f"[RUN FAILED] exit code {r3.returncode}")

        except FileNotFoundError as e:
            tb_log_parts.append(f"%Error: command not found: {e}")
        except subprocess.TimeoutExpired:
            tb_log_parts.append("%Error: TB simulation timed out")

        tb_log = "\n".join(tb_log_parts)

        # Detect failures: assertion errors, TODO Failed messages
        failure = None
        for line in tb_log.splitlines():
            stripped = line.strip()
            if "Failed" in stripped or "failed" in stripped:
                failure = stripped
                break
            if "Assertion" in stripped and "failed" in stripped.lower():
                failure = stripped
                break

        if not failure and "[RUN FAILED]" in tb_log:
            failure = "Testbench exited with non-zero code"

        status_msg = "PASS ✅" if not failure else f"FAIL: {failure[:60]}"
        print(f"  TB result: {status_msg}")

        return {
            "tb_log": tb_log,
            "tb_failure": failure,
            "ts_trial": state["ts_trial"] + 1,
            "total_iter": state["total_iter"] + 1,
            "phase": "ts",
        }

    # ──────────────────────────────────────────────────────────
    # Node 7: TED TB — Parse topmost TB failure → TDP
    # ──────────────────────────────────────────────────────────
    def node_ted_tb(self, state: COMBAState) -> dict:
        """
        Topmost Exception Detection for Testbench.
        Parse tb_log → extract topmost failure → TDP.
        """
        print("\n" + "=" * 60)
        print("🔎 NODE: TED TB (Parse topmost TB failure)")
        print("=" * 60)

        tb_log = state["tb_log"] or ""

        # Extract topmost failure line
        topmost_failure = None
        for line in tb_log.splitlines():
            stripped = line.strip()
            # Look for TODO X Failed pattern (COMBA TB convention)
            if re.search(r'TODO\s+\d+\s+Failed', stripped):
                topmost_failure = stripped
                break
            # Also catch assertion failures
            if "Assertion" in stripped and "failed" in stripped.lower():
                topmost_failure = stripped
                break

        if not topmost_failure:
            # Fallback: use the tb_failure from state
            topmost_failure = state.get("tb_failure", "Unknown testbench failure")

        tdp = f"Topmost testbench failure:\n{topmost_failure}"

        # Include traces (lines after the failure for context)
        trace_lines = []
        found = False
        for line in tb_log.splitlines():
            if found and len(trace_lines) < 5:
                if "TRACE" in line or "INPUT" in line or "OUTPUT" in line:
                    trace_lines.append(line.strip())
            if topmost_failure and topmost_failure in line:
                found = True

        if trace_lines:
            tdp += "\n\nDebug traces:\n" + "\n".join(trace_lines)

        print(f"  📋 TDP: {topmost_failure[:80]}")

        return {
            "tdp": tdp,
            "phase": "ts",
        }

    # ──────────────────────────────────────────────────────────
    # Utility: Extract Verilog from LLM response
    # ──────────────────────────────────────────────────────────
    def _extract_verilog(self, content: str) -> str:
        """Extract Verilog code from various LLM output formats."""
        # Try JSON format first
        try:
            data = json.loads(content)
            code = data.get("code", "")
            if code:
                return code
        except (json.JSONDecodeError, AttributeError):
            pass

        # Try markdown code block
        code_match = re.search(
            r'```(?:verilog|v)?\s*\n(.*?)\n```',
            content, re.DOTALL
        )
        if code_match:
            return code_match.group(1)

        # Raw content — if it looks like Verilog
        if "module " in content or "endmodule" in content:
            return content

        return content


# ──────────────────────────────────────────────────────────────
# 3. Five Conditional Edges (Routing Functions)
# ──────────────────────────────────────────────────────────────

def route_after_sc(state: COMBAState) -> str:
    """After Syntax Check: has errors? → TED_SC, else → TB."""
    if state["sc_exception_count"] > 0:
        return "node_ted_syntax"
    return "node_tb_sim"


def route_after_ts(state: COMBAState) -> str:
    """After TB Sim: has failures? → TED_TB, else → END (pass!)."""
    if state.get("tb_failure"):
        return "node_ted_tb"
    # All pass!
    return "end_pass"


def route_after_ted_syntax(state: COMBAState) -> str:
    """After TED Syntax: check SC trial limit → correcter or give up."""
    if state["sc_trial"] >= MAX_SC_TRIALS:
        return "end_fail_sc"
    return "node_correcter"


def route_after_ted_tb(state: COMBAState) -> str:
    """After TED TB: check TS trial limit → correcter or give up."""
    if state["ts_trial"] >= MAX_TS_TRIALS:
        return "end_fail_ts"
    return "node_correcter"


def route_after_correcter(state: COMBAState) -> str:
    """After Correcter: check total iteration limit → SC or give up."""
    if state["total_iter"] >= MAX_TOTAL_ITER:
        return "end_max_iter"
    return "node_syntax_check"


# ──────────────────────────────────────────────────────────────
# Terminal Nodes (set final_status)
# ──────────────────────────────────────────────────────────────

def end_pass(state: COMBAState) -> dict:
    """All checks passed!"""
    print("\n🎉 PIPELINE COMPLETE: ALL PASS!")
    return {"final_status": "pass"}


def end_fail_sc(state: COMBAState) -> dict:
    """SC trial limit reached."""
    print(f"\n❌ PIPELINE FAILED: SC trial limit ({MAX_SC_TRIALS}) reached")
    return {"final_status": "fail_sc"}


def end_fail_ts(state: COMBAState) -> dict:
    """TS trial limit reached."""
    print(f"\n❌ PIPELINE FAILED: TS trial limit ({MAX_TS_TRIALS}) reached")
    return {"final_status": "fail_ts"}


def end_max_iter(state: COMBAState) -> dict:
    """Total iteration limit reached."""
    print(f"\n❌ PIPELINE FAILED: Total iteration limit ({MAX_TOTAL_ITER}) reached")
    return {"final_status": "max_iter"}


# ──────────────────────────────────────────────────────────────
# 4. Build Graph
# ──────────────────────────────────────────────────────────────

def build_comba_graph(llm):
    """
    Build the full COMBA verification pipeline as a LangGraph.

    Graph topology:
        START → converter → generator → syntax_check
               ┌──────────────────────────────────┐
               ↓                                   │
        syntax_check ──(pass)──→ tb_sim            │
               │                   │               │
               ↓ (fail)            ↓ (fail)        │
        ted_syntax            ted_tb               │
               │                   │               │
               ↓                   ↓               │
        correcter ─────────────────────────────────┘
               │
               ↓ (max_iter)
              END

    Args:
        llm: LangChain-compatible chat model.

    Returns:
        Compiled LangGraph StateGraph.
    """
    nodes = COMBANodes(llm)

    builder = StateGraph(COMBAState)

    # ── Add all nodes ──
    builder.add_node("node_converter", nodes.node_converter)
    builder.add_node("node_generator", nodes.node_generator)
    builder.add_node("node_syntax_check", nodes.node_syntax_check)
    builder.add_node("node_ted_syntax", nodes.node_ted_syntax)
    builder.add_node("node_correcter", nodes.node_correcter)
    builder.add_node("node_tb_sim", nodes.node_tb_sim)
    builder.add_node("node_ted_tb", nodes.node_ted_tb)

    # Terminal nodes
    builder.add_node("end_pass", end_pass)
    builder.add_node("end_fail_sc", end_fail_sc)
    builder.add_node("end_fail_ts", end_fail_ts)
    builder.add_node("end_max_iter", end_max_iter)

    # ── Linear edges ──
    builder.add_edge(START, "node_converter")
    builder.add_edge("node_converter", "node_generator")
    builder.add_edge("node_generator", "node_syntax_check")

    # Terminal → END
    builder.add_edge("end_pass", END)
    builder.add_edge("end_fail_sc", END)
    builder.add_edge("end_fail_ts", END)
    builder.add_edge("end_max_iter", END)

    # ── Conditional edges (5 routing decisions) ──
    builder.add_conditional_edges(
        "node_syntax_check",
        route_after_sc,
        {"node_ted_syntax": "node_ted_syntax", "node_tb_sim": "node_tb_sim"},
    )

    builder.add_conditional_edges(
        "node_tb_sim",
        route_after_ts,
        {"node_ted_tb": "node_ted_tb", "end_pass": "end_pass"},
    )

    builder.add_conditional_edges(
        "node_ted_syntax",
        route_after_ted_syntax,
        {"node_correcter": "node_correcter", "end_fail_sc": "end_fail_sc"},
    )

    builder.add_conditional_edges(
        "node_ted_tb",
        route_after_ted_tb,
        {"node_correcter": "node_correcter", "end_fail_ts": "end_fail_ts"},
    )

    builder.add_conditional_edges(
        "node_correcter",
        route_after_correcter,
        {"node_syntax_check": "node_syntax_check", "end_max_iter": "end_max_iter"},
    )

    return builder.compile()


# ──────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="COMBA-PROMPT Full Verification Pipeline"
    )
    parser.add_argument(
        "description", nargs="?",
        help="Natural language description of the Verilog module",
    )
    parser.add_argument(
        "--xml", type=str,
        help="Path to existing COMBA XML file (skip converter)",
    )
    parser.add_argument(
        "--stub", action="store_true",
        help="Use StubLLM instead of real LLM (for testing)",
    )
    args = parser.parse_args()

    if not args.description and not args.xml:
        parser.error("Provide a description or --xml <path>")

    # Select LLM
    if args.stub:
        from stub_llm import create_stub_llm
        llm = create_stub_llm()
    else:
        from langchain_openai import ChatOpenAI
        base_url = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
        api_key = os.environ.get("LLM_API_KEY", "ollama")
        model = os.environ.get("LLM_MODEL", "qwen2.5-coder:7b")
        llm = ChatOpenAI(base_url=base_url, api_key=api_key, model=model, temperature=0.1)

    # Build state
    state = make_initial_state(nl_input=args.description or "")
    if args.xml:
        with open(args.xml, "r", encoding="utf-8") as f:
            state["xml_description"] = f.read()

    # Build and run
    graph = build_comba_graph(llm)
    config = {"recursion_limit": 100}
    final = graph.invoke(state, config)

    print(f"\n{'=' * 60}")
    print(f"Final Status: {final.get('final_status', 'unknown')}")
    print(f"SC Trials: {final.get('sc_trial', 0)}")
    print(f"TS Trials: {final.get('ts_trial', 0)}")
    print(f"Total Iterations: {final.get('total_iter', 0)}")
    print(f"{'=' * 60}")
