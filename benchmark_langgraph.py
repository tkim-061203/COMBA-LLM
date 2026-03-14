#!/usr/bin/env python3
"""
benchmark_langgraph.py — COMBA-LLM Benchmark via LangGraph
============================================================
Location: COMBA-LLM/benchmark_langgraph.py

- Uses vLLM dual-GPU (launch_dual_gpu.sh): GPU0=base:8000, GPU1=debugger:8001
- Imports from langgraph_core/ and modules/
- FR formula: FRᵢ = Σ[x ∉ E(v*ᵢ)] / |E(Vᵢ)|
- Output: per-trial JSON, aggregated summary, LaTeX, Markdown

Usage:
    # Dual-GPU (default, matches launch_dual_gpu.sh)
    python benchmark_langgraph.py --trials 5

    # Custom URLs
    python benchmark_langgraph.py --base-url http://localhost:8000/v1 \
                                  --lora-url http://localhost:8001/v1

    # Specific designs
    python benchmark_langgraph.py --designs counter_12 adder_8bit
"""

import argparse, json, os, sys, time, logging, statistics
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# ── Project root = COMBA-LLM/ ──
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Imports from project ──
from langgraph_core.graph import build_graph, COMBAState


# ═══════════════════════════════════════════════════════════════
# vLLM INTERFACE (dual-GPU)
# ═══════════════════════════════════════════════════════════════

class VLLMInterface:
    """vLLM dual-GPU client matching launch_dual_gpu.sh.
    
    GPU 0 (port 8000): base model  → Process ⓪ (Generator) + Agent 1
    GPU 1 (port 8001): merged LoRA → Process ① (Correcter)
    """
    def __init__(self,
                 base_url: str = None,
                 lora_url: str = None,
                 base_model: str = "qwen-base",
                 lora_model: str = "debugger"):
        from openai import OpenAI

        # Read from .env or defaults matching launch_dual_gpu.sh
        base_url = base_url or os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
        lora_url = lora_url or os.getenv("VLLM_LORA_URL", "http://localhost:8001/v1")

        self.client_base = OpenAI(base_url=base_url, api_key="not-needed")
        self.client_lora = OpenAI(base_url=lora_url, api_key="not-needed")
        self.base_model = base_model
        self.lora_model = lora_model

        logger.info(f"vLLM: base={base_model}@{base_url}, lora={lora_model}@{lora_url}")

    def generate(self, messages: list[dict], model: str = "base") -> str:
        if model == "base":
            client, m = self.client_base, self.base_model
        else:
            client, m = self.client_lora, self.lora_model
        r = client.chat.completions.create(
            model=m, messages=messages, temperature=0.1, max_tokens=2048)
        return r.choices[0].message.content or ""


# ═══════════════════════════════════════════════════════════════
# DESIGN LOADER (from modules/)
# ═══════════════════════════════════════════════════════════════

def load_designs(modules_dir: str = None, filter_names: list[str] | None = None) -> list[dict]:
    """Load RTLLM designs from COMBA-LLM/modules/."""
    modules_dir = modules_dir or str(PROJECT_ROOT / "modules")
    designs = []

    if not os.path.isdir(modules_dir):
        logger.error(f"Modules dir not found: {modules_dir}")
        return designs

    for name in sorted(os.listdir(modules_dir)):
        d = os.path.join(modules_dir, name)
        if not os.path.isdir(d): continue
        if filter_names and name not in filter_names: continue

        # Load description (XML preferred)
        desc = ""
        for fn in ["description.xml", "description.txt", "prompt.txt"]:
            fp = os.path.join(d, fn)
            if os.path.exists(fp):
                desc = open(fp).read(); break
        if not desc: continue

        # Testbench
        tb = ""
        for fn in ["testbench.cpp", "testbench.cc", "tb.cpp"]:
            fp = os.path.join(d, fn)
            if os.path.exists(fp): tb = fp; break

        designs.append({"name": name, "description": desc, "testbench_path": tb, "dir": d})

    logger.info(f"Loaded {len(designs)} designs from {modules_dir}")
    return designs


# ═══════════════════════════════════════════════════════════════
# FR — EXACT PAPER FORMULA
# ═══════════════════════════════════════════════════════════════

def sc_key(e: dict) -> str:
    return f"{e.get('exceptionType','')}_{e.get('exceptionTitle','')}_{e.get('exceptionContent','')[:80]}"

def ts_key(f: dict) -> str:
    return f"{f.get('todoNum',0)}_{f.get('failureContent','')[:80]}"


# ═══════════════════════════════════════════════════════════════
# SINGLE TRIAL
# ═══════════════════════════════════════════════════════════════

def run_single(app, design: dict, iteration_limit=20,
               sc_trial_limit=5, ts_trial_limit=5) -> dict:
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
                  "edtm_sc": {}, "edtm_ts": {},
                  "gvd": "", "iteration_count": 0}

    elapsed = time.time() - t0
    sc_pass = not result.get("sc_has_errors", True)
    ts_pass = not result.get("ts_has_failures", True)
    has_tb = bool(design["testbench_path"])

    # ── FR (paper formula) ──
    edtm_sc = result.get("edtm_sc", {})
    edtm_ts = result.get("edtm_ts", {})
    final_sc = result.get("sc_exceptions", [])
    final_ts = result.get("ts_failures", [])

    initial_sc_keys = set(edtm_sc.keys())
    final_sc_keys = set(sc_key(e) for e in final_sc)
    initial_ts_keys = set(edtm_ts.keys())
    final_ts_keys = set(ts_key(f) for f in final_ts)

    sc_fr = sum(1 for k in initial_sc_keys if k not in final_sc_keys) / len(initial_sc_keys) if initial_sc_keys else 1.0
    ts_fr = sum(1 for k in initial_ts_keys if k not in final_ts_keys) / len(initial_ts_keys) if initial_ts_keys else 1.0

    return {
        "design": design["name"],
        "sc_pass": sc_pass, "ts_pass": ts_pass, "has_tb": has_tb,
        "overall_pass": (sc_pass and ts_pass) if has_tb else sc_pass,
        "iterations": result.get("iteration_count", 0),
        "sc_fr": round(sc_fr, 4), "ts_fr": round(ts_fr, 4),
        "total_sc_exceptions": len(initial_sc_keys),
        "fixed_sc_exceptions": sum(1 for k in initial_sc_keys if k not in final_sc_keys),
        "total_ts_failures": len(initial_ts_keys),
        "fixed_ts_failures": sum(1 for k in initial_ts_keys if k not in final_ts_keys),
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
                  output_dir=None) -> dict:
    output_dir = output_dir or str(PROJECT_ROOT / "reports")
    os.makedirs(output_dir, exist_ok=True)
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_results = []

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

        # Per-trial exports
        for tag, data in [
            ("full", trial_results),
            ("syntax", [{"design": r["design"], "sc_pass": r["sc_pass"], "sc_fr": r["sc_fr"],
                         "total_sc": r["total_sc_exceptions"], "fixed_sc": r["fixed_sc_exceptions"],
                         "iterations": r["iterations"]} for r in trial_results]),
            ("functional", [{"design": r["design"], "ts_pass": r["ts_pass"], "ts_fr": r["ts_fr"],
                             "total_ts": r["total_ts_failures"], "fixed_ts": r["fixed_ts_failures"]}
                            for r in trial_results if r["has_tb"]]),
        ]:
            fp = os.path.join(output_dir, f"report_langgraph.{tag}.trial_{trial}.json")
            with open(fp, "w") as f: json.dump(data, f, indent=2)

        all_results.extend(trial_results)

    # Aggregated
    summary = compute_summary(all_results, trials, designs)
    print_summary(summary)

    with open(os.path.join(output_dir, f"summary_langgraph_{ts_str}.json"), "w") as f:
        json.dump(summary, f, indent=2)
    write_latex(summary, os.path.join(output_dir, f"tables_langgraph_{ts_str}.tex"))
    write_markdown(summary, os.path.join(output_dir, f"README_langgraph_{ts_str}.md"))
    logger.info(f"\nAll outputs → {output_dir}/")
    return summary


# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════

def compute_summary(all_results, trials, designs):
    per_design = {}
    for d in designs:
        name = d["name"]
        runs = [r for r in all_results if r["design"] == name]
        if not runs: continue
        per_design[name] = {
            "syntax_pass_rate": round(sum(1 for r in runs if r["sc_pass"]) / len(runs) * 100, 1),
            "func_pass_rate": round(sum(1 for r in runs if r["overall_pass"]) / len(runs) * 100, 1),
            "syntax_fr": round(sum(r["sc_fr"] for r in runs) / len(runs) * 100, 2),
            "func_fr": round(sum(r["ts_fr"] for r in runs) / len(runs) * 100, 2),
            "total_sc_exceptions": sum(r["total_sc_exceptions"] for r in runs),
            "fixed_sc_exceptions": sum(r["fixed_sc_exceptions"] for r in runs),
            "total_ts_failures": sum(r["total_ts_failures"] for r in runs),
            "fixed_ts_failures": sum(r["fixed_ts_failures"] for r in runs),
            "mean_iterations": round(sum(r["iterations"] for r in runs) / len(runs), 1),
            "has_tb": runs[0]["has_tb"],
        }

    syn_pr = [v["syntax_pass_rate"] for v in per_design.values()]
    fun_pr = [v["func_pass_rate"] for v in per_design.values()]
    sc_fr = [v["syntax_fr"] for v in per_design.values()]
    ts_fr = [v["func_fr"] for v in per_design.values() if v["has_tb"]]
    g_sc = sum(v["total_sc_exceptions"] for v in per_design.values())
    f_sc = sum(v["fixed_sc_exceptions"] for v in per_design.values())
    g_ts = sum(v["total_ts_failures"] for v in per_design.values())
    f_ts = sum(v["fixed_ts_failures"] for v in per_design.values())

    return {
        "n_designs": len(designs), "n_trials": trials,
        "avg_syntax_pass_rate": round(sum(syn_pr)/len(syn_pr), 2) if syn_pr else 0,
        "avg_func_pass_rate": round(sum(fun_pr)/len(fun_pr), 2) if fun_pr else 0,
        "syntax_pr_std": round(statistics.stdev(syn_pr), 2) if len(syn_pr) > 1 else 0,
        "func_pr_std": round(statistics.stdev(fun_pr), 2) if len(fun_pr) > 1 else 0,
        "avg_syntax_fr": round(sum(sc_fr)/len(sc_fr), 2) if sc_fr else 0,
        "avg_func_fr": round(sum(ts_fr)/len(ts_fr), 2) if ts_fr else 0,
        "total_sc_exceptions": f"{f_sc}/{g_sc}",
        "total_ts_failures": f"{f_ts}/{g_ts}",
        "mean_iterations": round(sum(v["mean_iterations"] for v in per_design.values())/max(len(per_design),1), 2),
        "pass_100pct": sorted([n for n, v in per_design.items() if v["func_pass_rate"] == 100]),
        "pass_0pct": sorted([n for n, v in per_design.items() if v["func_pass_rate"] == 0]),
        "per_design": per_design,
    }


def print_summary(s):
    print(f"""
{'='*70}
  COMBA-LLM BENCHMARK — LangGraph × vLLM Dual-GPU
{'='*70}

=== TABLE 1: PASS RATE ===
  Syntax Pass Rate  : {s['avg_syntax_pass_rate']}% (±{s['syntax_pr_std']}%)
  Function Pass Rate: {s['avg_func_pass_rate']}% (±{s['func_pr_std']}%)
  Mean Iterations   : {s['mean_iterations']}

=== TABLE 2: FIX RATE ===
  Syntax FR         : {s['avg_syntax_fr']}%
  Function FR       : {s['avg_func_fr']}%
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
        sc = f"{d['fixed_sc_exceptions']}/{d['total_sc_exceptions']}"
        ts = f"{d['fixed_ts_failures']}/{d['total_ts_failures']}"
        print(f"  {name:<22} {d['syntax_pass_rate']:>4.0f}% {d['func_pass_rate']:>4.0f}% "
              f"{d['syntax_fr']:>5.1f}% {d['func_fr']:>5.1f}% {d['mean_iterations']:>5.1f} "
              f"{sc:>6} {ts:>6}")


# ═══════════════════════════════════════════════════════════════
# LATEX EXPORT
# ═══════════════════════════════════════════════════════════════

def write_latex(s, path):
    pd, names = s["per_design"], sorted(s["per_design"].keys())
    lines = [
        r"% Auto-generated by benchmark_langgraph.py",
        r"\begin{table}[h]\centering",
        r"\caption{Pass Rate — COMBA-LLM + Qwen 2.5 Coder 7B}",
        r"\label{tab:pass_rate}",
        r"\begin{tabular}{l c c}\toprule",
        r"\textbf{Designs} & \textbf{SYNTAX} & \textbf{FUNC.} \\\midrule",
    ]
    for n in names:
        d = pd[n]
        lines.append(f"  {n.replace('_',chr(92)+'_')} & {d['syntax_pass_rate']:.0f}\\% & {d['func_pass_rate']:.0f}\\% \\\\")
    lines += [
        r"\midrule",
        f"  \\textbf{{Average}} & \\textbf{{{s['avg_syntax_pass_rate']}\\%}} & \\textbf{{{s['avg_func_pass_rate']}\\%}} \\\\",
        r"\bottomrule\end{tabular}\end{table}", "",
        r"\begin{table}[h]\centering",
        r"\caption{Fix Rate — COMBA-LLM post-debugging}",
        r"\label{tab:fix_rate}",
        r"\begin{tabular}{l c c}\toprule",
        r"\textbf{Designs} & \textbf{SYNTAX} & \textbf{FUNC.} \\\midrule",
    ]
    for n in names:
        d = pd[n]
        lines.append(f"  {n.replace('_',chr(92)+'_')} & {d['syntax_fr']:.2f}\\% & {d['func_fr']:.2f}\\% \\\\")
    lines += [
        r"\midrule",
        f"  \\textbf{{Average}} & \\textbf{{{s['avg_syntax_fr']}\\%}} & \\textbf{{{s['avg_func_fr']}\\%}} \\\\",
        f"  Total Exceptions & {s['total_sc_exceptions']} & {s['total_ts_failures']} \\\\",
        r"\bottomrule\end{tabular}\end{table}",
    ]
    with open(path, "w") as f: f.write("\n".join(lines))
    logger.info(f"  LaTeX → {path}")


# ═══════════════════════════════════════════════════════════════
# MARKDOWN EXPORT
# ═══════════════════════════════════════════════════════════════

def write_markdown(s, path):
    pd, names = s["per_design"], sorted(s["per_design"].keys())
    lines = [
        f"# COMBA-LLM Benchmark Report",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Designs:** {s['n_designs']} | **Trials:** {s['n_trials']}", "",
        f"## Summary", "",
        f"| Metric | Value |", f"|--------|-------|",
        f"| Syntax Pass Rate | **{s['avg_syntax_pass_rate']}%** (±{s['syntax_pr_std']}%) |",
        f"| Functional Pass Rate | **{s['avg_func_pass_rate']}%** (±{s['func_pr_std']}%) |",
        f"| Syntax Fix Rate | **{s['avg_syntax_fr']}%** |",
        f"| Functional Fix Rate | **{s['avg_func_fr']}%** |",
        f"| Total SC Exceptions | {s['total_sc_exceptions']} |",
        f"| Total TS Failures | {s['total_ts_failures']} |", "",
        f"## Table 1 — Pass Rate", "",
        f"| Design | Syntax | Functional |", f"|--------|--------|------------|",
    ]
    for n in names:
        d = pd[n]; lines.append(f"| {n} | {d['syntax_pass_rate']:.0f}% | {d['func_pass_rate']:.0f}% |")
    lines += [f"| **Average** | **{s['avg_syntax_pass_rate']}%** | **{s['avg_func_pass_rate']}%** |", "",
        f"## Table 2 — Fix Rate", "",
        f"| Design | Syntax FR | Func FR | SC Exc | TS Fail |",
        f"|--------|----------|---------|--------|---------|"]
    for n in names:
        d = pd[n]
        lines.append(f"| {n} | {d['syntax_fr']:.2f}% | {d['func_fr']:.2f}% | "
                     f"{d['fixed_sc_exceptions']}/{d['total_sc_exceptions']} | "
                     f"{d['fixed_ts_failures']}/{d['total_ts_failures']} |")
    lines += ["", f"**100% pass:** {', '.join(s['pass_100pct']) or 'None'}",
              f"**0% pass:** {', '.join(s['pass_0pct']) or 'None'}"]
    with open(path, "w") as f: f.write("\n".join(lines))
    logger.info(f"  Markdown → {path}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="COMBA-LLM LangGraph Benchmark")
    p.add_argument("--modules-dir", default=None, help="Path to modules/ (default: COMBA-LLM/modules/)")
    p.add_argument("--base-url", default=None, help="vLLM base URL (GPU 0, default :8000)")
    p.add_argument("--lora-url", default=None, help="vLLM LoRA URL (GPU 1, default :8001)")
    p.add_argument("--base-model", default="qwen-base")
    p.add_argument("--lora-model", default="debugger")
    p.add_argument("--trials", type=int, default=5)
    p.add_argument("--iter-limit", type=int, default=20)
    p.add_argument("--sc-limit", type=int, default=5)
    p.add_argument("--ts-limit", type=int, default=5)
    p.add_argument("--designs", nargs="*", help="Specific design names")
    p.add_argument("--output-dir", default=None, help="Output dir (default: COMBA-LLM/reports/)")
    args = p.parse_args()

    llm = VLLMInterface(
        base_url=args.base_url, lora_url=args.lora_url,
        base_model=args.base_model, lora_model=args.lora_model)

    app = build_graph(llm)
    logger.info("LangGraph compiled")

    designs = load_designs(args.modules_dir, args.designs)
    if not designs:
        logger.error("No designs. Check --modules-dir or COMBA-LLM/modules/.")
        sys.exit(1)

    run_benchmark(app, designs, trials=args.trials,
                  iteration_limit=args.iter_limit,
                  sc_trial_limit=args.sc_limit,
                  ts_trial_limit=args.ts_limit,
                  output_dir=args.output_dir)


if __name__ == "__main__":
    main()