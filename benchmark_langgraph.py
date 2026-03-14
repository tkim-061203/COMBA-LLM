#!/usr/bin/env python3
"""
benchmark_langgraph.py — COMBA-PROMPT Benchmark via LangGraph
==============================================================
- Computes Pass Rate (Table 1) and Fix Rate (Table 2) per COMBA-PROMPT paper
- Fix Rate uses per-exception formula: FRᵢ = Σ[x ∉ E(v*ᵢ)] / |E(Vᵢ)|
- FR = Σ FRᵢ / m  (averaged across m trials)

Output:
  1. Per-trial JSON:  report_langgraph.{type}.trial_{i}.json
  2. Aggregated summary JSON
  3. LaTeX table (Table 1 + Table 2 format)
  4. Markdown README report

Usage:
    python benchmark_langgraph.py --rtllm-dir ./rtllm_suite --trials 5
    python benchmark_langgraph.py --rtllm-dir ./rtllm_suite --backend vllm
"""

import argparse, json, os, sys, time, logging, statistics
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph import build_graph, COMBAState

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# LLM BACKENDS
# ═══════════════════════════════════════════════════════════════

class OllamaLLM:
    def __init__(self, model="qwen2.5-coder:7b", base_url="http://localhost:11434"):
        self.model, self.base_url = model, base_url

    def generate(self, messages: list[dict], model: str = "base") -> str:
        import requests
        r = requests.post(f"{self.base_url}/api/chat",
            json={"model": self.model, "messages": messages, "stream": False,
                  "options": {"temperature": 0.1, "num_predict": 2048}}, timeout=120)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")


class VLLMInterface:
    """vLLM backend — supports both single-server and dual-GPU (2 servers) setup.
    
    Single server (1 GPU, LoRA hot-swap):
        VLLMInterface(base_url="http://localhost:8000/v1")
    
    Dual server (2 GPUs, launch_dual_gpu.sh):
        VLLMInterface(base_url="http://localhost:8000/v1",
                      lora_url="http://localhost:8001/v1")
    """
    def __init__(self, base_url="http://localhost:8000/v1",
                 lora_url=None,
                 base_model="qwen-base", lora_model="debugger"):
        from openai import OpenAI
        self.client_base = OpenAI(base_url=base_url, api_key="not-needed")
        # Dual-GPU: lora_url points to separate server on GPU 1
        # Single-GPU: same server handles both via model name switching
        self.client_lora = OpenAI(base_url=lora_url or base_url, api_key="not-needed")
        self.base_model, self.lora_model = base_model, lora_model
        self.dual_mode = lora_url is not None

    def generate(self, messages: list[dict], model: str = "base") -> str:
        if model == "base":
            client, m = self.client_base, self.base_model
        else:
            client, m = self.client_lora, self.lora_model
        r = client.chat.completions.create(
            model=m, messages=messages, temperature=0.1, max_tokens=2048)
        return r.choices[0].message.content or ""


# ═══════════════════════════════════════════════════════════════
# DESIGN LOADER
# ═══════════════════════════════════════════════════════════════

def load_designs(rtllm_dir: str, filter_names: list[str] | None = None) -> list[dict]:
    designs = []
    if not os.path.isdir(rtllm_dir):
        logger.error(f"RTLLM dir not found: {rtllm_dir}"); return designs
    for name in sorted(os.listdir(rtllm_dir)):
        d = os.path.join(rtllm_dir, name)
        if not os.path.isdir(d): continue
        if filter_names and name not in filter_names: continue
        desc = ""
        for fn in ["description.xml", "description.txt", "prompt.txt"]:
            fp = os.path.join(d, fn)
            if os.path.exists(fp): desc = open(fp).read(); break
        if not desc: continue
        tb = ""
        for fn in ["testbench.cpp", "testbench.cc", "tb.cpp"]:
            fp = os.path.join(d, fn)
            if os.path.exists(fp): tb = fp; break
        designs.append({"name": name, "description": desc, "testbench_path": tb, "dir": d})
    logger.info(f"Loaded {len(designs)} designs from {rtllm_dir}")
    return designs


# ═══════════════════════════════════════════════════════════════
# FIX RATE — EXACT PAPER FORMULA
# ═══════════════════════════════════════════════════════════════
#
# FRᵢ = Σ_{x ∈ E(Vᵢ)} [x ∉ E(v*ᵢ)] / |E(Vᵢ)|
#
# Where:
#   E(Vᵢ)  = set of exceptions in initial GVD of trial i
#   E(v*ᵢ) = set of exceptions in final SGVD of trial i
#   [x ∉ E(v*ᵢ)] = 1 if exception x was fixed, 0 otherwise
#
# If E(Vᵢ) is empty (no initial exceptions), FRᵢ = 1.0
# FR = Σ FRᵢ / m

def compute_fr_trial(initial_exceptions: list[dict], final_exceptions: list[dict],
                     key_fn) -> float:
    """Compute FRᵢ for one trial.
    
    Args:
        initial_exceptions: E(Vᵢ) — exceptions in initial GVD
        final_exceptions: E(v*ᵢ) — exceptions in final SGVD
        key_fn: function to generate unique key from exception dict
    Returns:
        FRᵢ value (0.0 to 1.0)
    """
    if not initial_exceptions:
        return 1.0  # no initial exceptions = perfect

    e_vi = set(key_fn(e) for e in initial_exceptions)     # E(Vᵢ)
    e_vstar = set(key_fn(e) for e in final_exceptions)    # E(v*ᵢ)

    fixed_count = sum(1 for x in e_vi if x not in e_vstar)  # Σ[x ∉ E(v*ᵢ)]
    return fixed_count / len(e_vi)  # / |E(Vᵢ)|


def sc_key(e: dict) -> str:
    """SC exception key: type_title_content."""
    return f"{e.get('exceptionType','')}_{e.get('exceptionTitle','')}_{e.get('exceptionContent','')[:80]}"

def ts_key(f: dict) -> str:
    """TS failure key: todoNum_failureContent."""
    return f"{f.get('todoNum',0)}_{f.get('failureContent','')[:80]}"


# ═══════════════════════════════════════════════════════════════
# SINGLE TRIAL RUN
# ═══════════════════════════════════════════════════════════════

def run_single(app, design: dict, iteration_limit=20,
               sc_trial_limit=5, ts_trial_limit=5) -> dict:
    """Run one design, one trial through LangGraph. Return detailed metrics."""
    t0 = time.time()

    initial: COMBAState = {
        "nl_input": design["description"],
        "testbench_path": design["testbench_path"],
        "custom_vector": {},
        "iteration_limit": iteration_limit,
        "sc_trial_limit": sc_trial_limit,
        "ts_trial_limit": ts_trial_limit,
        "xml_retry_limit": 3,
        "xml_retry_count": 0,
        "phase": "start",
    }

    try:
        result = app.invoke(initial)
    except Exception as e:
        logger.error(f"  CRASH: {design['name']}: {e}")
        result = {"phase": "error", "stop_reason": str(e),
                  "sc_has_errors": True, "ts_has_failures": True,
                  "sc_exceptions": [], "ts_failures": [],
                  "gvd": "", "iteration_count": 0}

    elapsed = time.time() - t0

    # --- Determine pass/fail ---
    sc_pass = not result.get("sc_has_errors", True)
    ts_pass = not result.get("ts_has_failures", True)
    has_tb = bool(design["testbench_path"])

    # --- Compute FR using paper formula ---
    # We need initial exceptions (from first SC) and final exceptions
    # The graph tracks these via EDTM; for FR we compare initial vs final
    # Initial = all unique exceptions ever seen (from edtm keys)
    # Final = exceptions remaining in last SC check
    
    edtm_sc = result.get("edtm_sc", {})
    edtm_ts = result.get("edtm_ts", {})
    final_sc = result.get("sc_exceptions", [])
    final_ts = result.get("ts_failures", [])

    # Reconstruct E(Vᵢ): all exceptions that appeared (EDTM tracked them)
    initial_sc_keys = set(edtm_sc.keys())
    final_sc_keys = set(sc_key(e) for e in final_sc)
    initial_ts_keys = set(edtm_ts.keys())
    final_ts_keys = set(ts_key(f) for f in final_ts)

    # FRᵢ syntax
    if initial_sc_keys:
        sc_fr = sum(1 for k in initial_sc_keys if k not in final_sc_keys) / len(initial_sc_keys)
    else:
        sc_fr = 1.0

    # FRᵢ functional
    if initial_ts_keys:
        ts_fr = sum(1 for k in initial_ts_keys if k not in final_ts_keys) / len(initial_ts_keys)
    else:
        ts_fr = 1.0

    total_sc_exc = len(initial_sc_keys)
    fixed_sc_exc = sum(1 for k in initial_sc_keys if k not in final_sc_keys)
    total_ts_fail = len(initial_ts_keys)
    fixed_ts_fail = sum(1 for k in initial_ts_keys if k not in final_ts_keys)

    return {
        "design": design["name"],
        "sc_pass": sc_pass,
        "ts_pass": ts_pass,
        "has_tb": has_tb,
        "overall_pass": (sc_pass and ts_pass) if has_tb else sc_pass,
        "iterations": result.get("iteration_count", 0),
        # FR metrics (paper formula)
        "sc_fr": round(sc_fr, 4),
        "ts_fr": round(ts_fr, 4),
        "total_sc_exceptions": total_sc_exc,
        "fixed_sc_exceptions": fixed_sc_exc,
        "total_ts_failures": total_ts_fail,
        "fixed_ts_failures": fixed_ts_fail,
        # EDTM detail
        "edtm_sc_trials": dict(edtm_sc),
        "edtm_ts_trials": dict(edtm_ts),
        "sgvd_count": len(result.get("sgvd_versions", [])),
        "stop_reason": result.get("stop_reason", ""),
        "phase": result.get("phase", ""),
        "elapsed_s": round(elapsed, 1),
    }


# ═══════════════════════════════════════════════════════════════
# BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════════════

def run_benchmark(app, designs, trials=5, iteration_limit=20,
                  sc_trial_limit=5, ts_trial_limit=5,
                  output_dir="./benchmark_results") -> dict:
    os.makedirs(output_dir, exist_ok=True)
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    all_results = []  # flat list of all trial results

    for trial in range(1, trials + 1):
        logger.info(f"\n{'='*60}\n  TRIAL {trial}/{trials}\n{'='*60}")
        trial_results = []

        for i, design in enumerate(designs):
            logger.info(f"  [{i+1}/{len(designs)}] {design['name']}...")
            r = run_single(app, design, iteration_limit, sc_trial_limit, ts_trial_limit)
            r["trial"] = trial
            trial_results.append(r)

            st = "PASS" if r["overall_pass"] else "FAIL"
            logger.info(f"    {st} | iter={r['iterations']} | "
                        f"SC_FR={r['sc_fr']:.3f} TS_FR={r['ts_fr']:.3f} | {r['elapsed_s']}s")

        # Save per-trial JSON
        trial_file = os.path.join(output_dir, f"report_langgraph.full.trial_{trial}.json")
        with open(trial_file, "w") as f:
            json.dump(trial_results, f, indent=2)
        logger.info(f"  Saved: {trial_file}")

        # Also save SC-only and TS-only views
        sc_view = [{"design": r["design"], "sc_pass": r["sc_pass"],
                     "sc_fr": r["sc_fr"], "total_sc": r["total_sc_exceptions"],
                     "fixed_sc": r["fixed_sc_exceptions"], "iterations": r["iterations"]}
                    for r in trial_results]
        sc_file = os.path.join(output_dir, f"report_langgraph.syntax.trial_{trial}.json")
        with open(sc_file, "w") as f:
            json.dump(sc_view, f, indent=2)

        ts_view = [{"design": r["design"], "ts_pass": r["ts_pass"],
                     "ts_fr": r["ts_fr"], "total_ts": r["total_ts_failures"],
                     "fixed_ts": r["fixed_ts_failures"]}
                    for r in trial_results if r["has_tb"]]
        ts_file = os.path.join(output_dir, f"report_langgraph.functional.trial_{trial}.json")
        with open(ts_file, "w") as f:
            json.dump(ts_view, f, indent=2)

        all_results.extend(trial_results)

    # ── Aggregated summary ──
    summary = compute_summary(all_results, trials, designs)
    print_summary(summary)

    # Save aggregated JSON
    agg_file = os.path.join(output_dir, f"summary_langgraph_{ts_str}.json")
    with open(agg_file, "w") as f:
        json.dump(summary, f, indent=2)

    # Export LaTeX
    latex_file = os.path.join(output_dir, f"tables_langgraph_{ts_str}.tex")
    write_latex(summary, latex_file)

    # Export Markdown README
    md_file = os.path.join(output_dir, f"README_langgraph_{ts_str}.md")
    write_markdown(summary, md_file)

    logger.info(f"\nAll outputs in: {output_dir}/")
    return summary


# ═══════════════════════════════════════════════════════════════
# COMPUTE SUMMARY
# ═══════════════════════════════════════════════════════════════

def compute_summary(all_results, trials, designs):
    n = len(designs)
    design_names = [d["name"] for d in designs]

    per_design = {}
    for name in design_names:
        runs = [r for r in all_results if r["design"] == name]
        if not runs: continue

        # Pass Rate = fraction of trials that passed
        syntax_pr = sum(1 for r in runs if r["sc_pass"]) / len(runs)
        func_pr = sum(1 for r in runs if r["overall_pass"]) / len(runs)

        # FR = average FRᵢ across trials (paper formula)
        sc_frs = [r["sc_fr"] for r in runs]
        ts_frs = [r["ts_fr"] for r in runs]
        avg_sc_fr = sum(sc_frs) / len(sc_frs)
        avg_ts_fr = sum(ts_frs) / len(ts_frs)

        # Total exceptions across all trials
        tot_sc = sum(r["total_sc_exceptions"] for r in runs)
        fix_sc = sum(r["fixed_sc_exceptions"] for r in runs)
        tot_ts = sum(r["total_ts_failures"] for r in runs)
        fix_ts = sum(r["fixed_ts_failures"] for r in runs)

        mean_iter = sum(r["iterations"] for r in runs) / len(runs)

        per_design[name] = {
            "syntax_pass_rate": round(syntax_pr * 100, 1),
            "func_pass_rate": round(func_pr * 100, 1),
            "syntax_fr": round(avg_sc_fr * 100, 2),
            "func_fr": round(avg_ts_fr * 100, 2),
            "total_sc_exceptions": tot_sc,
            "fixed_sc_exceptions": fix_sc,
            "total_ts_failures": tot_ts,
            "fixed_ts_failures": fix_ts,
            "mean_iterations": round(mean_iter, 1),
            "has_tb": runs[0]["has_tb"],
        }

    # Global averages
    all_syntax_pr = [v["syntax_pass_rate"] for v in per_design.values()]
    all_func_pr = [v["func_pass_rate"] for v in per_design.values()]
    all_sc_fr = [v["syntax_fr"] for v in per_design.values()]
    all_ts_fr = [v["func_fr"] for v in per_design.values() if v["has_tb"]]
    all_iters = [v["mean_iterations"] for v in per_design.values()]

    # Total exceptions (Table 2 bottom row)
    global_tot_sc = sum(v["total_sc_exceptions"] for v in per_design.values())
    global_fix_sc = sum(v["fixed_sc_exceptions"] for v in per_design.values())
    global_tot_ts = sum(v["total_ts_failures"] for v in per_design.values())
    global_fix_ts = sum(v["fixed_ts_failures"] for v in per_design.values())

    return {
        "n_designs": n,
        "n_trials": trials,
        # Table 1: Pass Rate
        "avg_syntax_pass_rate": round(sum(all_syntax_pr) / len(all_syntax_pr), 2) if all_syntax_pr else 0,
        "avg_func_pass_rate": round(sum(all_func_pr) / len(all_func_pr), 2) if all_func_pr else 0,
        "syntax_pr_std": round(statistics.stdev(all_syntax_pr), 2) if len(all_syntax_pr) > 1 else 0,
        "func_pr_std": round(statistics.stdev(all_func_pr), 2) if len(all_func_pr) > 1 else 0,
        # Table 2: Fix Rate
        "avg_syntax_fr": round(sum(all_sc_fr) / len(all_sc_fr), 2) if all_sc_fr else 0,
        "avg_func_fr": round(sum(all_ts_fr) / len(all_ts_fr), 2) if all_ts_fr else 0,
        "total_sc_exceptions": f"{global_fix_sc}/{global_tot_sc}",
        "total_ts_failures": f"{global_fix_ts}/{global_tot_ts}",
        # Misc
        "mean_iterations": round(sum(all_iters) / len(all_iters), 2) if all_iters else 0,
        "pass_100pct": sorted([n for n, v in per_design.items() if v["func_pass_rate"] == 100]),
        "pass_0pct": sorted([n for n, v in per_design.items() if v["func_pass_rate"] == 0]),
        "per_design": per_design,
    }


def print_summary(s):
    print(f"""
{'='*70}
  BENCHMARK RESULTS — COMBA-PROMPT × LangGraph
{'='*70}

=== TABLE 1: PASS RATE ===
  Syntax Pass Rate  : {s['avg_syntax_pass_rate']}% (±{s['syntax_pr_std']}%)
  Function Pass Rate: {s['avg_func_pass_rate']}% (±{s['func_pr_std']}%)
  Mean Iterations   : {s['mean_iterations']}

=== TABLE 2: FIX RATE ===
  Syntax FR (avg)   : {s['avg_syntax_fr']}%
  Function FR (avg) : {s['avg_func_fr']}%
  Total SC Exc.     : {s['total_sc_exceptions']}
  Total TS Fail.    : {s['total_ts_failures']}

=== 100% PASS ({len(s['pass_100pct'])}) ===
  {', '.join(s['pass_100pct']) or 'None'}

=== 0% PASS ({len(s['pass_0pct'])}) ===
  {', '.join(s['pass_0pct']) or 'None'}

=== PER-DESIGN ===
  {'Design':<22} {'Syn%':>5} {'Fun%':>5} {'SynFR':>6} {'FunFR':>6} {'Iters':>5} {'SC':>6} {'TS':>6}
  {'-'*65}""")
    for name in sorted(s["per_design"]):
        d = s["per_design"][name]
        sc_str = f"{d['fixed_sc_exceptions']}/{d['total_sc_exceptions']}"
        ts_str = f"{d['fixed_ts_failures']}/{d['total_ts_failures']}"
        print(f"  {name:<22} {d['syntax_pass_rate']:>4.0f}% {d['func_pass_rate']:>4.0f}% "
              f"{d['syntax_fr']:>5.1f}% {d['func_fr']:>5.1f}% {d['mean_iterations']:>5.1f} "
              f"{sc_str:>6} {ts_str:>6}")
    print()


# ═══════════════════════════════════════════════════════════════
# LATEX EXPORT (Table 1 + Table 2)
# ═══════════════════════════════════════════════════════════════

def write_latex(s, path):
    pd = s["per_design"]
    names = sorted(pd.keys())

    lines = [
        r"% Auto-generated by benchmark_langgraph.py",
        r"% Table 1: Pass Rate",
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Syntax and functional correctness of VDs under COMBA-PROMPT flow.}",
        r"\label{tab:pass_rate}",
        r"\begin{tabular}{l c c}",
        r"\toprule",
        r"\textbf{Designs} & \textbf{SYNTAX} & \textbf{FUNC.} \\",
        r"\midrule",
    ]
    for n in names:
        d = pd[n]
        syn = f"{d['syntax_pass_rate']:.0f}\\%"
        fun = f"{d['func_pass_rate']:.0f}\\%"
        lines.append(f"  {n.replace('_', r'\_')} & {syn} & {fun} \\\\")
    lines += [
        r"\midrule",
        f"  \\textbf{{Average}} & \\textbf{{{s['avg_syntax_pass_rate']}\\%}} & \\textbf{{{s['avg_func_pass_rate']}\\%}} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
        r"% Table 2: Fix Rate",
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Fix Rate of final SGVDs under COMBA-PROMPT post-debugging.}",
        r"\label{tab:fix_rate}",
        r"\begin{tabular}{l c c}",
        r"\toprule",
        r"\textbf{Designs} & \textbf{SYNTAX} & \textbf{FUNC.} \\",
        r"\midrule",
    ]
    for n in names:
        d = pd[n]
        sfr = f"{d['syntax_fr']:.2f}\\%"
        tfr = f"{d['func_fr']:.2f}\\%"
        lines.append(f"  {n.replace('_', r'\_')} & {sfr} & {tfr} \\\\")
    lines += [
        r"\midrule",
        f"  \\textbf{{Average}} & \\textbf{{{s['avg_syntax_fr']}\\%}} & \\textbf{{{s['avg_func_fr']}\\%}} \\\\",
        f"  Total Exceptions & {s['total_sc_exceptions']} & {s['total_ts_failures']} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]

    with open(path, "w") as f:
        f.write("\n".join(lines))
    logger.info(f"  LaTeX saved: {path}")


# ═══════════════════════════════════════════════════════════════
# MARKDOWN README EXPORT
# ═══════════════════════════════════════════════════════════════

def write_markdown(s, path):
    pd = s["per_design"]
    names = sorted(pd.keys())

    lines = [
        f"# Benchmark Report — COMBA-PROMPT × LangGraph",
        f"",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Designs:** {s['n_designs']} | **Trials:** {s['n_trials']}",
        f"",
        f"## Global Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Syntax Pass Rate | **{s['avg_syntax_pass_rate']}%** (±{s['syntax_pr_std']}%) |",
        f"| Functional Pass Rate | **{s['avg_func_pass_rate']}%** (±{s['func_pr_std']}%) |",
        f"| Syntax Fix Rate | **{s['avg_syntax_fr']}%** |",
        f"| Functional Fix Rate | **{s['avg_func_fr']}%** |",
        f"| Total SC Exceptions | {s['total_sc_exceptions']} |",
        f"| Total TS Failures | {s['total_ts_failures']} |",
        f"| Mean Iterations | {s['mean_iterations']} |",
        f"",
        f"## Table 1 — Pass Rate",
        f"",
        f"| Design | Syntax | Functional |",
        f"|--------|--------|------------|",
    ]
    for n in names:
        d = pd[n]
        lines.append(f"| {n} | {d['syntax_pass_rate']:.0f}% | {d['func_pass_rate']:.0f}% |")
    lines += [
        f"| **Average** | **{s['avg_syntax_pass_rate']}%** | **{s['avg_func_pass_rate']}%** |",
        f"",
        f"## Table 2 — Fix Rate",
        f"",
        f"FR formula: FRᵢ = Σ\\[x ∉ E(v\\*ᵢ)\\] / |E(Vᵢ)|, FR = Σ FRᵢ / m",
        f"",
        f"| Design | Syntax FR | Func FR | SC Exc | TS Fail |",
        f"|--------|----------|---------|--------|---------|",
    ]
    for n in names:
        d = pd[n]
        sc = f"{d['fixed_sc_exceptions']}/{d['total_sc_exceptions']}"
        ts = f"{d['fixed_ts_failures']}/{d['total_ts_failures']}"
        lines.append(f"| {n} | {d['syntax_fr']:.2f}% | {d['func_fr']:.2f}% | {sc} | {ts} |")
    lines += [
        f"| **Average** | **{s['avg_syntax_fr']}%** | **{s['avg_func_fr']}%** | {s['total_sc_exceptions']} | {s['total_ts_failures']} |",
        f"",
        f"## Pass Analysis",
        f"",
        f"**100% pass ({len(s['pass_100pct'])}):** {', '.join(s['pass_100pct']) or 'None'}",
        f"",
        f"**0% pass ({len(s['pass_0pct'])}):** {', '.join(s['pass_0pct']) or 'None'}",
        f"",
        f"---",
        f"*Report generated by `benchmark_langgraph.py`*",
    ]

    with open(path, "w") as f:
        f.write("\n".join(lines))
    logger.info(f"  Markdown saved: {path}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="COMBA-PROMPT LangGraph Benchmark")
    p.add_argument("--rtllm-dir", default="./rtllm_suite")
    p.add_argument("--backend", choices=["ollama", "vllm"], default="ollama")
    p.add_argument("--model", default="qwen2.5-coder:7b", help="Ollama model name")
    p.add_argument("--base-url", default=None, help="Base model URL (GPU 0)")
    p.add_argument("--lora-url", default=None,
                   help="LoRA model URL (GPU 1). If omitted, uses --base-url for both.")
    p.add_argument("--base-model", default="qwen-base", help="vLLM served model name for base")
    p.add_argument("--lora-model", default="debugger", help="vLLM served model name for LoRA")
    p.add_argument("--trials", type=int, default=5)
    p.add_argument("--iter-limit", type=int, default=20)
    p.add_argument("--sc-limit", type=int, default=5)
    p.add_argument("--ts-limit", type=int, default=5)
    p.add_argument("--designs", nargs="*", help="Specific design names to run")
    p.add_argument("--output-dir", default="./benchmark_results")
    args = p.parse_args()

    if args.backend == "ollama":
        url = args.base_url or "http://localhost:11434"
        llm = OllamaLLM(model=args.model, base_url=url)
        logger.info(f"Backend: Ollama ({args.model} @ {url})")
    else:
        base_url = args.base_url or "http://localhost:8000/v1"
        lora_url = args.lora_url  # None = same server; set for dual-GPU
        llm = VLLMInterface(base_url=base_url, lora_url=lora_url,
                            base_model=args.base_model,
                            lora_model=args.lora_model)
        if lora_url:
            logger.info(f"Backend: vLLM dual-GPU (base={args.base_model}@{base_url}, "
                        f"lora={args.lora_model}@{lora_url})")
        else:
            logger.info(f"Backend: vLLM single (base={args.base_model}, "
                        f"lora={args.lora_model} @ {base_url})")

    app = build_graph(llm)
    logger.info("LangGraph compiled")

    designs = load_designs(args.rtllm_dir, args.designs)
    if not designs:
        logger.error("No designs. Check --rtllm-dir."); sys.exit(1)

    run_benchmark(app, designs, trials=args.trials,
                  iteration_limit=args.iter_limit,
                  sc_trial_limit=args.sc_limit,
                  ts_trial_limit=args.ts_limit,
                  output_dir=args.output_dir)


if __name__ == "__main__":
    main()