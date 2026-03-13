#!/usr/bin/env python
"""
Exception Trial Analysis for COMBA LangGraph v2 Pipeline.

Reads per-module report JSON files produced by:
    python run.py langgraph modules/* --descriptiontype xml

Analyzes:
  - Syntax exception types (from sc_log) and frequency
  - TB failure types (from tb_log) and frequency
  - Per-module breakdown as DataFrames

Usage:
    python exceptionTrial.py                           # default: xml reports
    python exceptionTrial.py --descriptiontype txt
"""

import glob
import os
import json
import re
import argparse

import pandas as pd
import numpy as np


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Exception Trial Analysis for COMBA Pipeline")
parser.add_argument(
    "--descriptiontype", default="xml",
    help="Description type used in evaluation: xml or txt"
)
parser.add_argument(
    "--modules", default="modules/*",
    help="Glob pattern for module directories"
)


def parse_sc_exceptions(sc_log: str) -> list:
    """Extract Verilator exception codes from SC log."""
    exceptions = []
    if not sc_log:
        return exceptions

    # Match: %Error-CODE: file.v:line:col: message
    # or:    %Error: file.v:line:col: message  (no code)
    pattern = re.compile(
        r'%Error(-(?P<code>[A-Z0-9_]+))?:\s',
        re.MULTILINE,
    )
    for match in pattern.finditer(sc_log):
        code = match.group("code") or "GENERIC"
        if code not in ("Exiting",):  # skip "Exiting due to" lines
            exceptions.append(code)

    return exceptions


def parse_tb_failures(tb_log: str) -> list:
    """Extract testbench failure descriptions from TB log."""
    failures = []
    if not tb_log:
        return failures

    for line in tb_log.splitlines():
        stripped = line.strip()
        # Match: TODO N Failed or assertion failures
        if re.search(r'TODO\s+\d+\s+Failed', stripped):
            failures.append(stripped)
        elif "Assertion" in stripped and "failed" in stripped.lower():
            failures.append(stripped)

    return failures


def run_analysis(description_type: str, modules_glob: str):
    """Analyze exception types from LangGraph v2 reports."""

    module_paths = sorted(glob.glob(modules_glob))
    if not module_paths:
        print(f"No modules found matching: {modules_glob}")
        return

    module_names = [os.path.basename(p) for p in module_paths]

    # DataFrames: rows = modules, columns = exception types
    sc_exception_counts = pd.DataFrame(index=module_names)
    tb_failure_counts = pd.DataFrame(index=module_names)

    # Summary data
    module_summary = {}

    for module_path in module_paths:
        module_name = os.path.basename(module_path)
        report_path = os.path.join(
            module_path, "reports", f"report_langgraph.{description_type}.json"
        )

        if not os.path.isfile(report_path):
            continue

        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        # Handle single vs multi-sample
        samples = report.get("samples", report)
        if isinstance(samples, dict):
            sample_list = [samples]
        elif isinstance(samples, list):
            sample_list = samples
        else:
            continue

        # Aggregate all exceptions across samples
        all_sc_exceptions = []
        all_tb_failures = []

        for sample in sample_list:
            sc_log = sample.get("sc_log", "")
            tb_log = sample.get("tb_log", "")

            all_sc_exceptions.extend(parse_sc_exceptions(sc_log))
            all_tb_failures.extend(parse_tb_failures(tb_log))

        # Count SC exception types
        for exc_code in set(all_sc_exceptions):
            if exc_code not in sc_exception_counts.columns:
                sc_exception_counts[exc_code] = 0
            count = all_sc_exceptions.count(exc_code)
            sc_exception_counts.loc[module_name, exc_code] = count

        # Count TB failure types (simplified key)
        for failure in set(all_tb_failures):
            # Create a short key from the failure message
            key = failure[:60].strip()
            if key not in tb_failure_counts.columns:
                tb_failure_counts[key] = 0
            tb_failure_counts.loc[module_name, key] = all_tb_failures.count(failure)

        passed_samples = [x for x in sample_list if x.get("final_status") == "pass"]
        best_sample = passed_samples[0] if passed_samples else sample_list[0]

        module_summary[module_name] = {
            "final_status": best_sample.get("final_status", "unknown"),
            "sc_exception_types": list(set(all_sc_exceptions)),
            "sc_exception_total": len(all_sc_exceptions),
            "tb_failure_total": len(all_tb_failures),
        }

    # Fill NaN with 0
    sc_exception_counts = sc_exception_counts.fillna(0).astype(int)
    tb_failure_counts = tb_failure_counts.fillna(0).astype(int)

    # ── Print Results ──
    print(f"\n{'═' * 60}")
    print("  COMBA LangGraph v2 — Exception Trial Analysis")
    print(f"{'═' * 60}")

    print(f"\n  📋 Syntax Exception Types ({len(sc_exception_counts.columns)} unique):")
    if not sc_exception_counts.empty:
        # Sort columns by frequency
        col_sums = sc_exception_counts.sum().sort_values(ascending=False)
        print(f"  {'Exception Code':<25} {'Total':>6} {'Modules':>8}")
        print(f"  {'─'*25} {'─'*6} {'─'*8}")
        for code in col_sums.index:
            total = int(col_sums[code])
            affected = int((sc_exception_counts[code] > 0).sum())
            print(f"  {code:<25} {total:>6} {affected:>8}")

    print(f"\n  📋 TB Failures ({len(tb_failure_counts.columns)} unique):")
    if not tb_failure_counts.empty:
        col_sums = tb_failure_counts.sum().sort_values(ascending=False)
        for key in col_sums.index[:10]:  # top 10
            total = int(col_sums[key])
            print(f"  [{total}x] {key}")

    # Per-module summary
    print(f"\n  {'Module':<25} {'Status':<12} {'SC Exc':>7} {'TB Fail':>8}")
    print(f"  {'─'*25} {'─'*12} {'─'*7} {'─'*8}")
    for name in sorted(module_summary.keys()):
        data = module_summary[name]
        status = data["final_status"]
        emoji = "✅" if status == "pass" else "❌"
        print(f"  {emoji} {name:<23} {status:<12} {data['sc_exception_total']:>7} {data['tb_failure_total']:>8}")

    # ── Export ──
    os.makedirs("reports/exceptionTrialBench", exist_ok=True)
    output_path = f"reports/exceptionTrialBench/exceptionTrialBench_langgraph.{description_type}.json"

    export_data = {
        "sc_exception_counts": sc_exception_counts.to_dict(),
        "tb_failure_counts": tb_failure_counts.to_dict(),
        "module_summary": module_summary,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    print(f"\n  📄 Results saved: {output_path}")

    # Also save CSV for easy viewing
    csv_path = f"reports/exceptionTrialBench/sc_exceptions_langgraph.{description_type}.csv"
    sc_exception_counts.to_csv(csv_path)
    print(f"  📄 SC exceptions CSV: {csv_path}")


if __name__ == "__main__":
    args = parser.parse_args()
    run_analysis(args.descriptiontype, args.modules)