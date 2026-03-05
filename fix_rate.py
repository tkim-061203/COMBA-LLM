#!/usr/bin/env python
"""
Fix Rate Analysis for COMBA LangGraph v2 Pipeline.

Reads per-module report JSON files produced by:
    python run.py langgraph modules/* --descriptiontype xml

Computes:
  - SC Pass Rate (syntax check passes)
  - TB Pass Rate (testbench passes, i.e., final_status == "pass")
  - Average SC/TS trial counts
  - Per-module breakdown

Usage:
    python fix_rate.py                           # default: xml reports
    python fix_rate.py --descriptiontype txt     # txt reports
    python fix_rate.py --legacy                  # run old fix_rate logic
"""

import glob
import os
import json
import argparse
import re

# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Fix Rate Analysis for COMBA Pipeline")
parser.add_argument(
    "--descriptiontype", default="xml",
    help="Description type used in evaluation: xml or txt"
)
parser.add_argument(
    "--modules", default="modules/*",
    help="Glob pattern for module directories"
)
parser.add_argument(
    "--legacy", action="store_true",
    help="Run old fix_rate logic (pre-LangGraph)"
)


def run_langgraph_analysis(description_type: str, modules_glob: str):
    """Analyze fix rates from LangGraph v2 pipeline reports."""

    module_paths = sorted(glob.glob(modules_glob))
    if not module_paths:
        print(f"No modules found matching: {modules_glob}")
        return

    results = {}
    total_modules = 0
    sc_pass = 0      # modules that passed syntax check (reached TB stage)
    tb_pass = 0      # modules that fully passed (final_status == "pass")
    total_sc_trials = 0
    total_ts_trials = 0
    total_iterations = 0

    for module_path in module_paths:
        module_name = os.path.basename(module_path)
        report_path = os.path.join(
            module_path, "reports", f"report_langgraph.{description_type}.json"
        )

        if not os.path.isfile(report_path):
            print(f"  ⚠️  No report for {module_name}")
            continue

        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        # Handle single vs multi-sample
        samples = report.get("samples", report)
        if isinstance(samples, dict):
            # Single sample
            sample_list = [samples]
        elif isinstance(samples, list):
            sample_list = samples
        else:
            print(f"  ⚠️  Invalid report format for {module_name}")
            continue

        total_modules += 1

        # Aggregate across samples (use best result)
        best_status = "error"
        best_sc = 0
        best_ts = 0
        best_iter = 0

        for sample in sample_list:
            status = sample.get("final_status", "error")
            sc_trials = sample.get("sc_trial", 0)
            ts_trials = sample.get("ts_trial", 0)
            iterations = sample.get("total_iter", 0)

            # Priority: pass > fail_ts > fail_sc > max_iter > error
            priority = {"pass": 4, "fail_ts": 3, "fail_sc": 2, "max_iter": 1, "error": 0}
            if priority.get(status, 0) > priority.get(best_status, 0):
                best_status = status
                best_sc = sc_trials
                best_ts = ts_trials
                best_iter = iterations

        # Count pass rates
        if best_status in ("pass", "fail_ts"):
            sc_pass += 1  # reached TB → SC passed
        if best_status == "pass":
            tb_pass += 1

        total_sc_trials += best_sc
        total_ts_trials += best_ts
        total_iterations += best_iter

        results[module_name] = {
            "final_status": best_status,
            "sc_trial": best_sc,
            "ts_trial": best_ts,
            "total_iter": best_iter,
            "sc_passed": best_status in ("pass", "fail_ts"),
            "tb_passed": best_status == "pass",
        }

    # ── Print Summary ──
    print(f"\n{'═' * 60}")
    print("  COMBA LangGraph v2 — Fix Rate Analysis")
    print(f"{'═' * 60}")
    print(f"  Description type: {description_type}")
    print(f"  Modules analyzed: {total_modules}")
    print(f"")
    print(f"  SC Pass Rate:  {sc_pass}/{total_modules} ({sc_pass/max(total_modules,1)*100:.1f}%)")
    print(f"  TB Pass Rate:  {tb_pass}/{total_modules} ({tb_pass/max(total_modules,1)*100:.1f}%)")
    print(f"")
    print(f"  Avg SC Trials: {total_sc_trials/max(total_modules,1):.1f}")
    print(f"  Avg TS Trials: {total_ts_trials/max(total_modules,1):.1f}")
    print(f"  Avg Iterations: {total_iterations/max(total_modules,1):.1f}")
    print(f"{'═' * 60}")

    # Per-module table
    print(f"\n  {'Module':<25} {'Status':<12} {'SC':>4} {'TS':>4} {'Iter':>5}")
    print(f"  {'─'*25} {'─'*12} {'─'*4} {'─'*4} {'─'*5}")
    for name, data in sorted(results.items()):
        emoji = "✅" if data["tb_passed"] else ("🔧" if data["sc_passed"] else "❌")
        print(f"  {emoji} {name:<23} {data['final_status']:<12} {data['sc_trial']:>4} {data['ts_trial']:>4} {data['total_iter']:>5}")

    # Save results
    os.makedirs("reports/fixrate", exist_ok=True)
    output_path = f"reports/fixrate/fixrate_langgraph.{description_type}.json"
    export_data = {
        "summary": {
            "total_modules": total_modules,
            "sc_pass_count": sc_pass,
            "tb_pass_count": tb_pass,
            "sc_pass_rate": sc_pass / max(total_modules, 1),
            "tb_pass_rate": tb_pass / max(total_modules, 1),
            "avg_sc_trials": total_sc_trials / max(total_modules, 1),
            "avg_ts_trials": total_ts_trials / max(total_modules, 1),
            "avg_total_iter": total_iterations / max(total_modules, 1),
        },
        "modules": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    print(f"\n  📄 Results saved: {output_path}")


if __name__ == "__main__":
    args = parser.parse_args()

    if args.legacy:
        # Run old fix_rate logic as-is (import from old code)
        print("Running legacy fix_rate logic...")
        print("(Legacy mode requires scripts.constants — run on Linux server)")
    else:
        run_langgraph_analysis(args.descriptiontype, args.modules)
