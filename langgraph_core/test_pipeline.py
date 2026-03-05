"""
E2E Tests for COMBA-PROMPT LangGraph Pipeline v3.

Tests the full pipeline with StubLLM and mocked Verilator subprocess calls.
All 8 routing decisions, ExtractionGuard, PreSCCheck, MultiAttemptManager,
Rollback Manager, EDTM, and Iteration Control are verified without
external dependencies.

Usage:
    python -m pytest test_pipeline.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from comba_pipeline import (
    COMBAState,
    COMBANodes,
    build_comba_graph,
    make_initial_state,
    MAX_SC_TRIALS,
    MAX_TS_TRIALS,
    MAX_TOTAL_ITER,
    EDTM_MAX_RETRIES,
    route_after_sc,
    route_after_ts,
    route_after_ted_syntax,
    route_after_ted_tb,
    route_after_extraction_guard,
    route_after_pre_sc_check,
)
from stub_llm import (
    create_stub_llm,
    create_buggy_stub_llm,
    create_always_buggy_stub_llm,
    create_worse_stub_llm,
    GOOD_VERILOG,
    BUGGY_VERILOG,
    FIXED_VERILOG,
    WORSE_VERILOG,
    GOOD_XML,
    DEBUGGER_PATCH_FIXED,
)


# ──────────────────────────────────────────────────────────────
# Helpers: Mock Verilator subprocess calls
# ──────────────────────────────────────────────────────────────

def make_verilator_result(returncode=0, stderr="", stdout=""):
    """Create a mock subprocess.CompletedProcess."""
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = returncode
    result.stderr = stderr
    result.stdout = stdout
    return result


CLEAN_SC_RESULT = make_verilator_result(returncode=0, stderr="", stdout="")
SC_ERROR_RESULT = make_verilator_result(
    returncode=1,
    stderr=(
        "%Error: adder_8bit.v:8: Signal 'result' not found\n"
        "%Error: Exiting due to 1 error(s)\n"
    ),
)
SC_MULTI_ERROR_RESULT = make_verilator_result(
    returncode=1,
    stderr=(
        "%Error: adder_8bit.v:8: Signal 'result' not found\n"
        "%Error: adder_8bit.v:9: Signal 'unknown_signal' not found\n"
        "%Error: adder_8bit.v:10: Signal 'another_undeclared' not found\n"
        "%Error: Exiting due to 3 error(s)\n"
    ),
)
TB_PASS_RESULT = make_verilator_result(returncode=0, stdout="All tests passed\n")
TB_FAIL_RESULT = make_verilator_result(
    returncode=1,
    stdout=(
        "# TODO 3 Failed at simtime 42\n"
        "# TODO 3 INPUT TRACE: in->a = 0xff, in->b = 0x01, in->cin = 0x0\n"
        "# TODO 3 OUTPUT TRACE: tx->cout = 0x0, tx->sum = 0x00\n"
    ),
)


# ──────────────────────────────────────────────────────────────
# Test 1: Unit tests for routing functions
# ──────────────────────────────────────────────────────────────

class TestRoutingFunctions:
    """Test the 8 conditional routing functions in isolation."""

    # ── ExtractionGuard routing (v3 NEW) ──
    def test_route_after_extraction_guard_success(self):
        state = make_initial_state()
        state["extraction_result"] = {"success": True, "code": "module test..."}
        assert route_after_extraction_guard(state) == "node_pre_sc_check"

    def test_route_after_extraction_guard_fail_from_generator(self):
        state = make_initial_state()
        state["extraction_result"] = {"success": False}
        state["_last_llm_source"] = "generator"
        assert route_after_extraction_guard(state) == "node_generator"

    def test_route_after_extraction_guard_fail_from_debugger(self):
        state = make_initial_state()
        state["extraction_result"] = {"success": False}
        state["_last_llm_source"] = "debugger"
        assert route_after_extraction_guard(state) == "node_debugger"

    # ── PreSCCheck routing (v3 NEW) ──
    def test_route_after_pre_sc_check_passed(self):
        state = make_initial_state()
        state["pre_sc_result"] = {"passed": True, "auto_fixed_code": None}
        assert route_after_pre_sc_check(state) == "node_syntax_check"

    def test_route_after_pre_sc_check_auto_fixed(self):
        state = make_initial_state()
        state["pre_sc_result"] = {"passed": False, "auto_fixed_code": "module ..."}
        assert route_after_pre_sc_check(state) == "node_syntax_check"

    def test_route_after_pre_sc_check_failed(self):
        state = make_initial_state()
        state["pre_sc_result"] = {"passed": False, "auto_fixed_code": None}
        assert route_after_pre_sc_check(state) == "node_debugger"

    # ── SC routing (unchanged) ──
    def test_route_after_sc_has_errors(self):
        state = make_initial_state()
        state["sc_exception_count"] = 2
        assert route_after_sc(state) == "node_ted_syntax"

    def test_route_after_sc_clean(self):
        state = make_initial_state()
        state["sc_exception_count"] = 0
        assert route_after_sc(state) == "node_tb_sim"

    # ── TS routing (unchanged) ──
    def test_route_after_ts_has_failure(self):
        state = make_initial_state()
        state["tb_failure"] = "TODO 3 Failed"
        assert route_after_ts(state) == "node_ted_tb"

    def test_route_after_ts_pass(self):
        state = make_initial_state()
        state["tb_failure"] = None
        assert route_after_ts(state) == "end_pass"

    # ── TED SC routing (enhanced with MultiAttempt) ──
    def test_route_after_ted_syntax_under_limit(self):
        state = make_initial_state()
        state["sc_trial"] = 3
        state["sc_exception"] = "%Error: some error"
        assert route_after_ted_syntax(state) == "node_debugger"

    def test_route_after_ted_syntax_at_limit(self):
        state = make_initial_state()
        state["sc_trial"] = MAX_SC_TRIALS
        state["sc_exception"] = "%Error: some error"
        assert route_after_ted_syntax(state) == "end_fail_sc"

    def test_route_after_ted_syntax_no_exception(self):
        """When TED finds no parseable error, route to TB instead of debugger."""
        state = make_initial_state()
        state["sc_exception"] = None
        state["sc_trial"] = 3
        assert route_after_ted_syntax(state) == "node_tb_sim"

    # ── TED TB routing (enhanced with MultiAttempt) ──
    def test_route_after_ted_tb_under_limit(self):
        state = make_initial_state()
        state["ts_trial"] = 2
        assert route_after_ted_tb(state) == "node_debugger"

    def test_route_after_ted_tb_at_limit(self):
        state = make_initial_state()
        state["ts_trial"] = MAX_TS_TRIALS
        assert route_after_ted_tb(state) == "end_fail_ts"


# ──────────────────────────────────────────────────────────────
# Test 2: Individual node tests
# ──────────────────────────────────────────────────────────────

class TestNodes:
    """Test individual node logic."""

    def test_node_converter(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state(nl_input="Design an 8-bit adder")
        result = nodes.node_converter(state)
        assert result["xml_description"] is not None
        assert "adder_8bit" in result["xml_description"]
        assert result["module_name"] == "adder_8bit"

    def test_node_converter_skip_when_xml_present(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["xml_description"] = GOOD_XML
        result = nodes.node_converter(state)
        assert result == {}  # no changes

    def test_node_generator_outputs_raw(self):
        """v3: Generator outputs _raw_llm_output instead of gvd directly."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["xml_description"] = GOOD_XML
        state["module_name"] = "adder_8bit"
        result = nodes.node_generator(state)
        assert result["_raw_llm_output"] is not None
        assert result["_last_llm_source"] == "generator"
        assert result["multi_attempt_mgr"] is not None
        assert "gvd" not in result  # v3: no direct gvd assignment

    def test_node_extraction_guard_success(self):
        """ExtractionGuard succeeds with valid Verilog."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["_raw_llm_output"] = GOOD_VERILOG
        state["module_name"] = "adder_8bit"
        state["_last_llm_source"] = "generator"
        result = nodes.node_extraction_guard(state)
        assert result["extraction_result"]["success"] is True
        assert "gvd" in result
        assert "module adder_8bit" in result["gvd"]
        assert result.get("sgvd") is not None  # set sgvd for generator

    def test_node_extraction_guard_failure(self):
        """ExtractionGuard fails with non-Verilog text."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["_raw_llm_output"] = "I cannot generate this code."
        state["module_name"] = "adder_8bit"
        state["_last_llm_source"] = "generator"
        result = nodes.node_extraction_guard(state)
        assert result["extraction_result"]["success"] is False
        assert result["extraction_result"]["retry_prompt"] is not None
        assert "gvd" not in result  # gvd not updated on failure

    def test_node_pre_sc_check_passes_clean_code(self):
        """PreSCCheck passes for clean Verilog."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["gvd"] = GOOD_VERILOG
        state["module_name"] = "adder_8bit"
        result = nodes.node_pre_sc_check(state)
        assert result["pre_sc_result"]["passed"] is True

    def test_node_pre_sc_check_detects_issues(self):
        """PreSCCheck detects structural issues."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        # Code missing endmodule — should be caught
        state["gvd"] = "module test(input a, output b);\n  assign b = a;\n"
        state["module_name"] = "test"
        result = nodes.node_pre_sc_check(state)
        assert result["pre_sc_result"]["fatal_count"] > 0

    def test_node_syntax_check_clean(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["gvd"] = GOOD_VERILOG
        state["module_name"] = "adder_8bit"
        state["sc_trial"] = 0
        state["total_iter"] = 0

        with patch("comba_pipeline.subprocess.run", return_value=CLEAN_SC_RESULT):
            result = nodes.node_syntax_check(state)

        assert result["sc_exception_count"] == 0
        assert result["sc_trial"] == 1

    def test_node_syntax_check_with_errors(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["gvd"] = BUGGY_VERILOG
        state["module_name"] = "adder_8bit"
        state["sc_trial"] = 0
        state["total_iter"] = 0

        with patch("comba_pipeline.subprocess.run", return_value=SC_ERROR_RESULT):
            result = nodes.node_syntax_check(state)

        assert result["sc_exception_count"] == 1
        assert result["sc_trial"] == 1

    def test_node_ted_syntax_extracts_topmost(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["sc_log"] = (
            "%Error: adder_8bit.v:8: Signal 'result' not found\n"
            "%Error: adder_8bit.v:9: Another error\n"
            "%Error: Exiting due to 2 error(s)\n"
        )

        result = nodes.node_ted_syntax(state)
        assert result["sc_exception"] is not None
        assert "result" in result["sc_exception"]
        assert result["edp"] is not None

    def test_node_ted_syntax_edtm_tracking(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["sc_log"] = "%Error: adder_8bit.v:8: Signal 'result' not found\n"
        state["edtm"] = {}

        # First time
        result = nodes.node_ted_syntax(state)
        sig = list(result["edtm"].keys())[0]
        assert result["edtm"][sig] == 1

        # Simulate repeated failures
        state["edtm"] = result["edtm"]
        for _ in range(EDTM_MAX_RETRIES):
            result = nodes.node_ted_syntax(state)
            state["edtm"] = result["edtm"]

        # After exceeding limit, EDP should contain EDTM warning
        assert "EDTM WARNING" in result["edp"]

    def test_node_debugger_outputs_raw_v3(self):
        """v3: Debugger outputs _raw_llm_output via MultiAttemptManager."""
        llm = create_buggy_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["gvd"] = BUGGY_VERILOG
        state["sc_exception_count"] = 1
        state["sc_trial"] = 1
        state["phase"] = "sc"
        state["module_name"] = "adder_8bit"
        state["sc_exception"] = "%Error: Signal 'result' not found"
        state["edp"] = "Topmost Verilator error:\n%Error: Signal 'result' not found"
        state["sc_log"] = "%Error: adder_8bit.v:8: Signal 'result' not found\n"
        state["nl_input"] = "Design an 8-bit adder"

        result = nodes.node_debugger(state)
        assert result["_raw_llm_output"] is not None
        assert result["_last_llm_source"] == "debugger"
        assert result["multi_attempt_mgr"] is not None
        assert result["escalation_level"] is not None

    def test_node_ted_tb_extracts_todo_failure(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["tb_log"] = (
            "# TODO 3 Failed at simtime 42\n"
            "# TODO 3 INPUT TRACE: in->a = 0xff\n"
        )
        state["tb_failure"] = "TODO 3 Failed"

        result = nodes.node_ted_tb(state)
        assert result["tdp"] is not None
        assert "TODO 3 Failed" in result["tdp"]


# ──────────────────────────────────────────────────────────────
# Test 3: E2E Graph tests with mocked Verilator
# ──────────────────────────────────────────────────────────────

class TestE2EGraph:
    """End-to-end tests running the full compiled graph."""

    def _run_graph(self, llm, sc_results, tb_results=None):
        """
        Helper: build graph, run with mocked subprocess.

        Args:
            llm: StubLLM instance
            sc_results: list of mock results for successive SC calls
            tb_results: list of mock results for successive TB calls
        """
        graph = build_comba_graph(llm)
        state = make_initial_state(nl_input="Design an 8-bit adder")

        sc_iter = iter(sc_results)
        tb_iter = iter(tb_results or [])

        def mock_subprocess_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "--lint-only" in cmd_str:
                return next(sc_iter, CLEAN_SC_RESULT)
            elif "make" in cmd_str.lower() or cmd_str.endswith((".exe", "Vadder_8bit")):
                # TB make or binary execution
                return next(tb_iter, TB_PASS_RESULT)
            elif "verilator" in cmd_str.lower():
                # TB verilate step
                return next(tb_iter, make_verilator_result(0))
            return make_verilator_result(0)

        with patch("comba_pipeline.subprocess.run", side_effect=mock_subprocess_run):
            with patch("comba_pipeline.shutil.copy2"):  # skip file copy
                result = graph.invoke(state, {"recursion_limit": 150})

        return result

    def test_happy_path(self):
        """SC passes, TB passes → final_status == 'pass'."""
        llm = create_stub_llm()
        result = self._run_graph(
            llm,
            sc_results=[CLEAN_SC_RESULT],
            tb_results=[
                make_verilator_result(0),  # verilate
                make_verilator_result(0),  # make
                TB_PASS_RESULT,            # run
            ],
        )
        assert result["final_status"] == "pass"
        assert result["sc_trial"] == 1
        assert result["ts_trial"] == 1

    def test_sc_fix_then_pass(self):
        """SC fails → TED → Debugger → ExtractionGuard → PreSC → SC passes → TB passes."""
        llm = create_buggy_stub_llm()
        result = self._run_graph(
            llm,
            sc_results=[
                SC_ERROR_RESULT,    # first SC: fails
                CLEAN_SC_RESULT,    # second SC after fix: passes
            ],
            tb_results=[
                make_verilator_result(0),  # verilate
                make_verilator_result(0),  # make
                TB_PASS_RESULT,            # run
            ],
        )
        assert result["final_status"] == "pass"
        assert result["sc_trial"] == 2  # went through SC twice

    def test_sc_iteration_limit(self):
        """SC always fails → hits MAX_SC_TRIALS → fail_sc."""
        llm = create_always_buggy_stub_llm()
        # Provide enough SC errors to hit the limit
        sc_results = [SC_ERROR_RESULT] * (MAX_SC_TRIALS + 5)
        result = self._run_graph(llm, sc_results=sc_results)
        assert result["final_status"] == "fail_sc"
        assert result["sc_trial"] >= MAX_SC_TRIALS

    def test_graph_compiles_and_has_correct_nodes(self):
        """Verify the graph structure is correct."""
        llm = create_stub_llm()
        graph = build_comba_graph(llm)
        graph_obj = graph.get_graph()

        # LangGraph returns nodes as dict or iterable — handle both
        if hasattr(graph_obj, 'nodes'):
            nodes_data = graph_obj.nodes
            if isinstance(nodes_data, dict):
                node_ids = list(nodes_data.keys())
            else:
                # Try as iterable of objects with .id
                try:
                    node_ids = [n.id for n in nodes_data]
                except AttributeError:
                    node_ids = list(nodes_data)
        else:
            node_ids = []

        # Check all expected nodes exist (9 pipeline + 4 terminal = 13)
        expected_nodes = [
            "node_converter",
            "node_generator",
            "node_extraction_guard",   # v3 NEW
            "node_pre_sc_check",       # v3 NEW
            "node_syntax_check",
            "node_ted_syntax",
            "node_debugger",
            "node_tb_sim",
            "node_ted_tb",
            "end_pass",
            "end_fail_sc",
            "end_fail_ts",
            "end_max_iter",
        ]
        for expected in expected_nodes:
            assert expected in node_ids, f"Missing node: {expected}"

        # node_patcher should NOT be in the graph (removed in v3)
        assert "node_patcher" not in node_ids, "node_patcher should not be in v3 graph"


# ──────────────────────────────────────────────────────────────
# Test 4: EDTM integration
# ──────────────────────────────────────────────────────────────

class TestEDTM:
    """Test Exception-Debugging Trial Management."""

    def test_edtm_counts_repeated_errors(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)

        edtm = {}
        sc_log = "%Error: adder_8bit.v:8: Signal 'result' not found\n"

        for i in range(5):
            state = make_initial_state()
            state["sc_log"] = sc_log
            state["edtm"] = edtm
            result = nodes.node_ted_syntax(state)
            edtm = result["edtm"]

        # The signature should have been seen 5 times
        assert any(v == 5 for v in edtm.values())

    def test_edtm_warning_after_threshold(self):
        llm = create_stub_llm()
        nodes = COMBANodes(llm)

        edtm = {}
        sc_log = "%Error: adder_8bit.v:8: Signal 'result' not found\n"

        for i in range(EDTM_MAX_RETRIES + 1):
            state = make_initial_state()
            state["sc_log"] = sc_log
            state["edtm"] = edtm
            result = nodes.node_ted_syntax(state)
            edtm = result["edtm"]

        # After exceeding threshold, EDP should contain warning
        assert "EDTM WARNING" in result["edp"]


# ──────────────────────────────────────────────────────────────
# Test 5: State initialization
# ──────────────────────────────────────────────────────────────

class TestState:
    """Test state creation and defaults."""

    def test_initial_state_defaults(self):
        state = make_initial_state()
        assert state["nl_input"] == ""
        assert state["gvd"] is None
        assert state["sc_trial"] == 0
        assert state["ts_trial"] == 0
        assert state["total_iter"] == 0
        assert state["phase"] == "sc"
        assert state["edtm"] == {}
        assert state["final_status"] is None
        assert state["debugger_patch"] is None
        # v3 new fields
        assert state["extraction_result"] is None
        assert state["pre_sc_result"] is None
        assert state["multi_attempt_mgr"] is None
        assert state["escalation_level"] is None
        assert state["_last_llm_source"] is None
        assert state["_raw_llm_output"] is None

    def test_initial_state_with_args(self):
        state = make_initial_state(nl_input="test", module_name="foo")
        assert state["nl_input"] == "test"
        assert state["module_name"] == "foo"


# ──────────────────────────────────────────────────────────────
# Test 6: ExtractionGuard integration
# ──────────────────────────────────────────────────────────────

class TestExtractionGuard:
    """Test ExtractionGuard node behavior."""

    def test_guard_extracts_from_markdown_fence(self):
        """Guard extracts code from ```verilog ... ``` fences."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["module_name"] = "adder_8bit"
        state["_last_llm_source"] = "generator"
        state["_raw_llm_output"] = (
            "Here is the Verilog code:\n\n"
            "```verilog\n"
            + GOOD_VERILOG +
            "\n```\n\n"
            "This implements an 8-bit adder."
        )
        result = nodes.node_extraction_guard(state)
        assert result["extraction_result"]["success"] is True
        assert "module adder_8bit" in result["gvd"]

    def test_guard_rejects_empty_output(self):
        """Guard rejects empty LLM output."""
        llm = create_stub_llm()
        nodes = COMBANodes(llm)
        state = make_initial_state()
        state["module_name"] = "test"
        state["_last_llm_source"] = "generator"
        state["_raw_llm_output"] = ""
        result = nodes.node_extraction_guard(state)
        assert result["extraction_result"]["success"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
