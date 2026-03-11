#!/usr/bin/env python
"""
Fix Rate Analysis for COMBA Pipeline — Paper-Accurate FR.

Based on COMBA-PROMPT paper (MCT4SD 2025) formula:

    FRᵢ = Σ [x ∉ E(v*ᵢ)] / |E(Vᵢ)|

Where:
    E(Vᵢ)  = all exceptions encountered during trial i (from EDTM)
    E(v*ᵢ) = exceptions remaining in final SGVD of trial i
    FR     = average FRᵢ across m trials

Computes BOTH:
    - Pass Rate (PR): binary pass/fail per module (Table 1 in paper)
    - Fix Rate (FR): per-exception fix ratio (Table 2 in paper)

Usage:
    python fix_rate.py                           # default: xml reports
    python fix_rate.py --descriptiontype txt
"""

import glob
import os
import json
import re
import argparse


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Fix Rate Analysis (Paper-Accurate)")
parser.add_argument(
    "--descriptiontype", default="xml",
    help="Description type used in evaluation: xml or txt"
)
parser.add_argument(
    "--modules", default="modules/*",
    help="Glob pattern for module directories"
)


# ──────────────────────────────────────────────────────────────
# Exception Parsers
# ──────────────────────────────────────────────────────────────

def parse_sc_exceptions_from_log(sc_log: str) -> list:
    """Extract Verilator error/warning codes from SC log."""
    exceptions = []
    if not sc_log:
        return exceptions
    pattern = re.compile(
        r'%(Error|Warning)(-(?P<code>[A-Z0-9_]+))?:\s',
        re.MULTILINE,
    )
    for match in pattern.finditer(sc_log):
        code = match.group("code") or "GENERIC"
        if code not in ("Exiting",):
            exceptions.append(code)
    return exceptions


def parse_tb_failures_from_log(tb_log: str) -> list:
    """Extract testbench failure keys from TB log."""
    failures = []
    if not tb_log:
        return failures
    for line in tb_log.splitlines():
        stripped = line.strip()
        if re.search(r'TODO\s+\d+\s+Failed', stripped):
            # Normalize: replace numbers with N
            sig = "TB:" + re.sub(r'\d+', 'N', stripped).strip()
            sig = re.sub(r'\s+', ' ', sig)
            failures.append(sig)
        elif "Assertion" in stripped and "failed" in stripped.lower():
            sig = "TB:" + re.sub(r'\d+', 'N', stripped).strip()
            sig = re.sub(r'\s+', ' ', sig)
            failures.append(sig)
    return failures


# ──────────────────────────────────────────────────────────────
# FR Calculation (Paper Formula)
# ──────────────────────────────────────────────────────────────

def calculate_fr_per_trial(sample: dict) -> dict:
    """
    Calculate Fix Rate for a single trial following COMBA-PROMPT formula.

    Uses EDTM dict (all exceptions seen during trial) as E(Vᵢ),
    and parses final sc_log/tb_log for E(v*ᵢ).

    Returns:
        {
            "syntax_fr": float,   # Syntax Fix Rate
            "func_fr": float,     # Function Fix Rate
            "all_syntax": list,   # E(Vᵢ) syntax keys
            "final_syntax": list, # E(v*ᵢ) syntax keys
            "all_tb": list,       # E(Vᵢ) TB keys
            "final_tb": list,     # E(v*ᵢ) TB keys
        }
    """
    final_status = sample.get("final_status", "error")
    edtm = sample.get("edtm", {})

    # Separate SC and TB exceptions from EDTM
    all_syntax = [k for k in edtm.keys() if not k.startswith("TB:")]
    all_tb = [k for k in edtm.keys() if k.startswith("TB:")]

    # Special case: no SGVD (error/crash) → FR = 0
    if final_status == "error":
        return {
            "syntax_fr": 0.0,
            "func_fr": 0.0,
            "all_syntax": all_syntax,
            "final_syntax": all_syntax,  # all remain
            "all_tb": all_tb,
            "final_tb": all_tb,
        }

    # Parse final logs for remaining exceptions
    final_sc_log = sample.get("sc_log", "")
    final_tb_log = sample.get("tb_log", "")
    final_syntax_raw = parse_sc_exceptions_from_log(final_sc_log)
    final_tb_raw = parse_tb_failures_from_log(final_tb_log)

    # Normalize final SC exceptions to match EDTM signature format
    final_syntax_sigs = set()
    for code in final_syntax_raw:
        # Try to find matching EDTM key containing this code
        for edtm_key in all_syntax:
            if code in edtm_key:
                final_syntax_sigs.add(edtm_key)
                break

    final_tb_sigs = set(final_tb_raw)

    # --- Syntax FR ---
    if len(all_syntax) == 0:
        syntax_fr = 1.0  # No exceptions encountered → perfect
    else:
        fixed_syntax = sum(1 for x in all_syntax if x not in final_syntax_sigs)
        syntax_fr = fixed_syntax / len(all_syntax)

    # --- Function FR ---
    if len(all_tb) == 0:
        if final_status == "pass":
            func_fr = 1.0  # No TB issues at all
        elif final_status in ("fail_ts",):
            func_fr = 0.0  # TB failed but no EDTM tracking → 0
        else:
            func_fr = 1.0  # SC-only trial, no TB exceptions
    else:
        fixed_tb = sum(1 for x in all_tb if x not in final_tb_sigs)
        func_fr = fixed_tb / len(all_tb)

    # Override: if final passed TB, func_fr = 1.0
    if final_status == "pass":
        func_fr = 1.0

    return {
        "syntax_fr": syntax_fr,
        "func_fr": func_fr,
        "all_syntax": all_syntax,
        "final_syntax": list(final_syntax_sigs),
        "all_tb": all_tb,
        "final_tb": list(final_tb_sigs),
    }


# ──────────────────────────────────────────────────────────────
# Main Analysis
# ──────────────────────────────────────────────────────────────

def run_analysis(description_type: str, modules_glob: str):
    """Analyze Pass Rate + Fix Rate from pipeline reports."""

    module_paths = sorted(glob.glob(modules_glob))
    if not module_paths:
        print(f"No modules found matching: {modules_glob}")
        return

    results = {}
    total_modules = 0

    # Aggregators for global metrics
    all_syntax_frs = []
    all_func_frs = []
    total_sc_pass = 0
    total_tb_pass = 0
    total_syntax_exceptions = 0
    total_syntax_fixed = 0
    total_tb_exceptions = 0
    total_tb_fixed = 0

    for module_path in module_paths:
        module_name = os.path.basename(module_path)
        report_path = os.path.join(
            module_path, "reports", f"report_langgraph.{description_type}.json"
        )

        if not os.path.isfile(report_path):
            continue

        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        # Normalize samples
        samples = report.get("samples", report)
        if isinstance(samples, dict):
            sample_list = [samples]
        elif isinstance(samples, list):
            sample_list = samples
        else:
            continue

        total_modules += 1
        m = len(sample_list)

        # Per-trial FR
        trial_syntax_frs = []
        trial_func_frs = []
        sc_passed_count = 0
        tb_passed_count = 0

        for sample in sample_list:
            status = sample.get("final_status", "error")

            # Pass Rate (binary)
            if status in ("pass", "fail_ts"):
                sc_passed_count += 1
            if status == "pass":
                tb_passed_count += 1

            # Fix Rate (paper formula)
            fr_result = calculate_fr_per_trial(sample)
            trial_syntax_frs.append(fr_result["syntax_fr"])
            trial_func_frs.append(fr_result["func_fr"])

            # Aggregators for total counts
            total_syntax_exceptions += len(fr_result["all_syntax"])
            total_syntax_fixed += len(fr_result["all_syntax"]) - len(fr_result["final_syntax"])
            total_tb_exceptions += len(fr_result["all_tb"])
            total_tb_fixed += len(fr_result["all_tb"]) - len(fr_result["final_tb"])

        # Average FR across trials
        avg_syntax_fr = sum(trial_syntax_frs) / m if m > 0 else 0
        avg_func_fr = sum(trial_func_frs) / m if m > 0 else 0

        all_syntax_frs.append(avg_syntax_fr)
        all_func_frs.append(avg_func_fr)

        # Pass rates
        sc_pr = sc_passed_count / m if m > 0 else 0
        tb_pr = tb_passed_count / m if m > 0 else 0
        if sc_pr > 0:
            total_sc_pass += 1
        if tb_pr > 0:
            total_tb_pass += 1

        results[module_name] = {
            "trials": m,
            "sc_pass_rate": sc_pr,
            "tb_pass_rate": tb_pr,
            "syntax_fr": avg_syntax_fr,
            "func_fr": avg_func_fr,
        }

    # ── Print Summary ──
    print(f"\n{'═' * 70}")
    print("  COMBA Pipeline — Paper-Accurate Fix Rate Analysis")
    print(f"{'═' * 70}")
    print(f"  Description type: {description_type}")
    print(f"  Modules analyzed: {total_modules}")
    print()

    # Pass Rate (Table 1 style)
    print(f"  ── Pass Rate (Table 1) ────────────────────────────────")
    print(f"  SC Pass:   {total_sc_pass}/{total_modules} ({total_sc_pass/max(total_modules,1)*100:.0f}%)")
    print(f"  TB Pass:   {total_tb_pass}/{total_modules} ({total_tb_pass/max(total_modules,1)*100:.0f}%)")
    print()

    # Fix Rate (Table 2 style)
    avg_global_syntax_fr = sum(all_syntax_frs) / max(len(all_syntax_frs), 1)
    avg_global_func_fr = sum(all_func_frs) / max(len(all_func_frs), 1)
    print(f"  ── Fix Rate (Table 2) ─────────────────────────────────")
    print(f"  Syntax FR: {avg_global_syntax_fr*100:.2f}%")
    print(f"  Func FR:   {avg_global_func_fr*100:.2f}%")
    print(f"  Total Syntax Exceptions: {total_syntax_fixed}/{total_syntax_exceptions}")
    print(f"  Total TB Failures:       {total_tb_fixed}/{total_tb_exceptions}")
    print(f"{'═' * 70}")

    # Per-module table
    print(f"\n  {'Module':<25} {'SC PR':>6} {'TB PR':>6} {'Syn FR':>7} {'Fn FR':>7}")
    print(f"  {'─'*25} {'─'*6} {'─'*6} {'─'*7} {'─'*7}")
    for name, data in sorted(results.items()):
        sc_str = f"{data['sc_pass_rate']*100:.0f}%"
        tb_str = f"{data['tb_pass_rate']*100:.0f}%"
        sfr_str = f"{data['syntax_fr']*100:.1f}%"
        ffr_str = f"{data['func_fr']*100:.1f}%"
        emoji = "✅" if data["tb_pass_rate"] > 0 else "❌"
        print(f"  {emoji} {name:<23} {sc_str:>6} {tb_str:>6} {sfr_str:>7} {ffr_str:>7}")

    # Save results
    os.makedirs("reports/fixrate", exist_ok=True)
    output_path = f"reports/fixrate/fixrate_langgraph.{description_type}.json"
    export_data = {
        "summary": {
            "total_modules": total_modules,
            "sc_pass_count": total_sc_pass,
            "tb_pass_count": total_tb_pass,
            "sc_pass_rate": total_sc_pass / max(total_modules, 1),
            "tb_pass_rate": total_tb_pass / max(total_modules, 1),
            "syntax_fix_rate": avg_global_syntax_fr,
            "func_fix_rate": avg_global_func_fr,
            "total_syntax_exceptions": total_syntax_exceptions,
            "total_syntax_fixed": total_syntax_fixed,
            "total_tb_exceptions": total_tb_exceptions,
            "total_tb_fixed": total_tb_fixed,
        },
        "modules": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    print(f"\n  📄 Results saved: {output_path}")


if __name__ == "__main__":
    args = parser.parse_args()
    run_analysis(args.descriptiontype, args.modules)
