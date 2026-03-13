"""
COMBA Pipeline Benchmark — Paper-Accurate

Based on COMBA-PROMPT paper (MCT4SD 2025):
- **29 RTLLM designs** × **5 trials** per design
- Computes **Pass Rate** (Table 1) and **Fix Rate** (Table 2)
- Fix Rate uses the per-exception formula: FRᵢ = Σ[x ∉ E(v*ᵢ)] / |E(Vᵢ)|

**Output:**
1. Per-trial reports saved as `report_langgraph.{type}.trial_{i}.json`
2. Aggregated summary with averaged Pass Rate and Fix Rate
3. LaTeX-ready table export
4. Markdown README report export
"""

import subprocess
import os
import json
import glob
import shutil
import pandas as pd
import numpy as np
from tqdm import tqdm
from datetime import datetime

# --- Configuration ---
NUM_TRIALS = 5
DESCRIPTION_TYPE = "xml"
MODULES_DIR = "modules"
SUMMARY_FILE = f"reports/summary_langgraph.{DESCRIPTION_TYPE}.json"

# All 29 RTLLM modules
ALL_MODULES = sorted([d for d in os.listdir(MODULES_DIR)
                      if os.path.isdir(os.path.join(MODULES_DIR, d))])

print(f"Configuration:")
print(f"  Trials per design: {NUM_TRIALS}")
print(f"  Description type:  {DESCRIPTION_TYPE}")
print(f"  Total modules:     {len(ALL_MODULES)}")
print(f"  Total runs:        {len(ALL_MODULES) * NUM_TRIALS}")
print(f"\nModules:")
for i, m in enumerate(ALL_MODULES, 1):
    print(f"  {i:2d}. {m}")


# ## 1. Execute Pipeline (5 trials × 29 modules)
# 
# Each trial runs the full COMBA pipeline on all 29 modules.
# Reports are saved per-trial to avoid overwrites.

trial_results = {}  # trial_idx -> {module_name -> report}

for trial in range(1, NUM_TRIALS + 1):
    print(f"\n{'='*60}")
    print(f"  TRIAL {trial}/{NUM_TRIALS}")
    print(f"{'='*60}")

    # Remove old summary to get fresh data
    if os.path.exists(SUMMARY_FILE):
        os.remove(SUMMARY_FILE)

    # Execute pipeline on all modules
    cmd = [
        "python", "run.py", "langgraph",
        f"{MODULES_DIR}/*",
        "--descriptiontype", DESCRIPTION_TYPE
    ]

    result = subprocess.run(cmd, capture_output=False, text=True)

    if result.returncode != 0:
        print(f"  ⚠️ Trial {trial} had errors (returncode={result.returncode})")

    # Copy per-module reports to trial-specific files
    trial_data = {}
    for module_name in ALL_MODULES:
        report_path = os.path.join(
            MODULES_DIR, module_name, "reports",
            f"report_langgraph.{DESCRIPTION_TYPE}.json"
        )

        if os.path.isfile(report_path):
            # Read report
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)

            # Save trial-specific copy
            trial_report_path = os.path.join(
                MODULES_DIR, module_name, "reports",
                f"report_langgraph.{DESCRIPTION_TYPE}.trial_{trial}.json"
            )
            with open(trial_report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            # Extract sample data
            samples = report.get("samples", report)
            if isinstance(samples, dict):
                trial_data[module_name] = samples
            elif isinstance(samples, list):
                trial_data[module_name] = samples[0]
        else:
            print(f"  ⚠️ No report for {module_name}")
            trial_data[module_name] = {"final_status": "error", "edtm": {}}

    trial_results[trial] = trial_data
    passed = sum(1 for d in trial_data.values() if d.get("final_status") == "pass")
    print(f"  ✅ Trial {trial}: {passed}/{len(ALL_MODULES)} passed")

print(f"\n{'='*60}")
print(f"  All {NUM_TRIALS} trials completed.")
print(f"{'='*60}")


# ## 2. Compute Pass Rate (Table 1) and Fix Rate (Table 2)
# 
# **Pass Rate** = across m trials, how often does the module pass syntax / testbench?
# **Fix Rate** = across all exceptions encountered in a trial, what fraction were fixed?

import re

def parse_sc_exceptions(sc_log):
    """Extract exception codes from SC log."""
    if not sc_log:
        return []
    exceptions = []
    for match in re.finditer(r'%(Error|Warning)(-(?P<code>[A-Z0-9_]+))?:\s', sc_log):
        code = match.group('code') or 'GENERIC'
        if code != 'Exiting':
            exceptions.append(code)
    return exceptions


def calc_fr_trial(sample):
    """Paper-accurate FRᵢ for one trial."""
    status = sample.get('final_status', 'error')
    edtm = sample.get('edtm', {})

    # Separate SC vs TB exceptions from EDTM keys
    all_sc = [k for k in edtm.keys() if not k.startswith('TB:')]
    all_tb = [k for k in edtm.keys() if k.startswith('TB:')]

    if status == 'error':
        return 0.0, 0.0  # syntax_fr, func_fr

    # Final SC exceptions (still in final log)
    final_sc_raw = parse_sc_exceptions(sample.get('sc_log', ''))
    final_sc_sigs = set()
    for code in final_sc_raw:
        for edtm_key in all_sc:
            if code in edtm_key:
                final_sc_sigs.add(edtm_key)
                break

    # Syntax FR
    if len(all_sc) == 0:
        syntax_fr = 1.0
    else:
        fixed = sum(1 for x in all_sc if x not in final_sc_sigs)
        syntax_fr = fixed / len(all_sc)

    # Func FR
    if status == 'pass':
        func_fr = 1.0
    elif len(all_tb) == 0:
        func_fr = 0.0 if status == 'fail_ts' else 1.0
    else:
        # If TB still failing, all TB exceptions remain
        func_fr = 0.0 if status in ('fail_ts',) else 1.0

    return syntax_fr, func_fr


# Build results table
rows = []
for module_name in ALL_MODULES:
    sc_pass_count = 0
    tb_pass_count = 0
    syntax_frs = []
    func_frs = []

    for trial in range(1, NUM_TRIALS + 1):
        sample = trial_results[trial].get(module_name, {})
        status = sample.get('final_status', 'error')

        # Pass Rate (binary)
        if status in ('pass', 'fail_ts'):
            sc_pass_count += 1
        if status == 'pass':
            tb_pass_count += 1

        # Fix Rate
        sfr, ffr = calc_fr_trial(sample)
        syntax_frs.append(sfr)
        func_frs.append(ffr)

    rows.append({
        'Module': module_name,
        'SC Pass Rate': f"{sc_pass_count/NUM_TRIALS*100:.0f}%",
        'TB Pass Rate': f"{tb_pass_count/NUM_TRIALS*100:.0f}%",
        'Syntax FR': f"{np.mean(syntax_frs)*100:.2f}%",
        'Func FR': f"{np.mean(func_frs)*100:.2f}%",
        '_sc_pr': sc_pass_count/NUM_TRIALS,
        '_tb_pr': tb_pass_count/NUM_TRIALS,
        '_sfr': np.mean(syntax_frs),
        '_ffr': np.mean(func_frs),
    })

df = pd.DataFrame(rows)

# Global averages
avg_sc_pr = df['_sc_pr'].mean() * 100
avg_tb_pr = df['_tb_pr'].mean() * 100
avg_sfr = df['_sfr'].mean() * 100
avg_ffr = df['_ffr'].mean() * 100

print(f"=== GLOBAL RESULTS ({NUM_TRIALS} trials × {len(ALL_MODULES)} modules) ===")
print(f"SC Pass Rate:   {avg_sc_pr:.1f}%")
print(f"TB Pass Rate:   {avg_tb_pr:.1f}%")
print(f"Syntax Fix Rate: {avg_sfr:.2f}%")
print(f"Func Fix Rate:   {avg_ffr:.2f}%")
print()

print(df[['Module', 'SC Pass Rate', 'TB Pass Rate', 'Syntax FR', 'Func FR']]
        .sort_values('Module').to_string(index=False))


# ## 3. Export Results

# Save aggregated JSON
os.makedirs('reports/fixrate', exist_ok=True)

export_data = {
    'config': {
        'num_trials': NUM_TRIALS,
        'description_type': DESCRIPTION_TYPE,
        'num_modules': len(ALL_MODULES),
        'timestamp': datetime.now().isoformat(),
    },
    'global': {
        'sc_pass_rate': avg_sc_pr / 100,
        'tb_pass_rate': avg_tb_pr / 100,
        'syntax_fix_rate': avg_sfr / 100,
        'func_fix_rate': avg_ffr / 100,
    },
    'modules': {r['Module']: {
        'sc_pass_rate': r['_sc_pr'],
        'tb_pass_rate': r['_tb_pr'],
        'syntax_fr': r['_sfr'],
        'func_fr': r['_ffr'],
    } for r in rows}
}

json_path = f'reports/fixrate/benchmark_{DESCRIPTION_TYPE}_{NUM_TRIALS}trials.json'
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(export_data, f, indent=2, ensure_ascii=False)
print(f'📄 JSON saved: {json_path}')

# Save CSV
csv_path = f'reports/fixrate/benchmark_{DESCRIPTION_TYPE}_{NUM_TRIALS}trials.csv'
df[['Module', 'SC Pass Rate', 'TB Pass Rate', 'Syntax FR', 'Func FR']].to_csv(
    csv_path, index=False
)
print(f'📄 CSV saved: {csv_path}')

# LaTeX table
latex_rows = []
for r in rows:
    latex_rows.append(
        f"  {r['Module']} & {r['SC Pass Rate']} & {r['TB Pass Rate']} & "
        f"{r['Syntax FR']} & {r['Func FR']} \\\\"
    )
latex_avg = (
    f"  \\textbf{{Average}} & \\textbf{{{avg_sc_pr:.0f}\\%}} & "
    f"\\textbf{{{avg_tb_pr:.0f}\\%}} & \\textbf{{{avg_sfr:.2f}\\%}} & "
    f"\\textbf{{{avg_ffr:.2f}\\%}} \\\\"
)

latex = '\n'.join([
    r'\begin{table}[h]',
    r'\centering',
    f'\\caption{{Pass Rate and Fix Rate ({DESCRIPTION_TYPE}, {NUM_TRIALS} trials)}}',
    r'\begin{tabular}{l|cc|cc}',
    r'  \hline',
    r'  Design & SC PR & TB PR & Syntax FR & Func FR \\',
    r'  \hline',
    *latex_rows,
    r'  \hline',
    latex_avg,
    r'  \hline',
    r'\end{tabular}',
    r'\end{table}',
])

tex_path = f'reports/fixrate/benchmark_{DESCRIPTION_TYPE}_{NUM_TRIALS}trials.tex'
with open(tex_path, 'w', encoding='utf-8') as f:
    f.write(latex)
print(f'📄 LaTeX saved: {tex_path}')
print()
print(latex)

# Save Markdown README
readme_content = f"""# COMBA Pipeline Benchmark Results ({DESCRIPTION_TYPE})

## Configuration
- **Trials per design:** {NUM_TRIALS}
- **Description type:** {DESCRIPTION_TYPE}
- **Total modules:** {len(ALL_MODULES)}
- **Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Global Results
- **SC Pass Rate:** {avg_sc_pr:.1f}%
- **TB Pass Rate:** {avg_tb_pr:.1f}%
- **Syntax Fix Rate:** {avg_sfr:.2f}%
- **Func Fix Rate:** {avg_ffr:.2f}%

## Per-Module Results
{df[['Module', 'SC Pass Rate', 'TB Pass Rate', 'Syntax FR', 'Func FR']].to_markdown(index=False)}
"""

readme_path = f'reports/fixrate/README_{DESCRIPTION_TYPE}_{NUM_TRIALS}trials.md'
with open(readme_path, 'w', encoding='utf-8') as f:
    f.write(readme_content)
print(f'📄 README saved: {readme_path}')

