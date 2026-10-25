#!/usr/bin/env python3
"""
================================================================================
 Northstar Shop — Automated Benchmark & Verification Suite
================================================================================

Validates the NSTVE v2.0 Deletion Audit Agent against the 32 official golden
reference cases in `dataset/sample_output.csv` and checks the 518-case submission
file `output.csv` for 100% schema compliance.

Usage:
  python run_benchmark.py
  python run_benchmark.py --ground-truth dataset/sample_output.csv
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

import pandas as pd

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "code"))

from code.engine.nstve import NSTPipeline
from code.evaluation.evaluator import evaluate


def _resolve_path(p: str) -> str:
    if os.path.exists(p):
        return p
    for r in [str(REPO_ROOT), "..", "../.."]:
        cand = os.path.join(r, p)
        if os.path.exists(cand):
            return os.path.abspath(cand)
    return p


def print_msg(msg: str, style: str = ""):
    if HAS_RICH and style:
        console.print(f"[{style}]{msg}[/{style}]")
    else:
        print(msg)


def benchmark_samples(
    sample_requests_path: str = "dataset/sample_deletion_requests.csv",
    sample_gold_path: str = "dataset/sample_output.csv",
    dataset_dir: str = "dataset"
) -> Dict[str, Any]:
    print_msg("\n" + "=" * 70, "bold cyan")
    print_msg(" 1. BENCHMARKING NSTVE ENGINE ON 32 GOLDEN SAMPLE CASES", "bold cyan")
    print_msg("=" * 70, "bold cyan")

    sample_requests_path = _resolve_path(sample_requests_path)
    sample_gold_path = _resolve_path(sample_gold_path)
    dataset_dir = _resolve_path(dataset_dir)

    if not os.path.exists(sample_requests_path) or not os.path.exists(sample_gold_path):
        print_msg(f"ERROR: Sample files missing ({sample_requests_path} or {sample_gold_path})", "bold red")
        return {}

    pipeline = NSTPipeline(dataset_dir=dataset_dir)
    samples_df = pd.read_csv(sample_requests_path)
    gold_df = pd.read_csv(sample_gold_path)

    t0 = time.time()
    pred_records = []
    for _, row in samples_df.iterrows():
        cid = str(row["case_id"]).strip()
        status, steps = pipeline.run_case(row, all_cases_df=samples_df)
        pred_records.append({
            "case_id": cid,
            "deletion_status": status,
            "steps_json": json.dumps(steps)
        })
    elapsed = time.time() - t0

    pred_df = pd.DataFrame(pred_records)
    pred_df.to_csv("sample_predictions.csv", index=False)
    results = evaluate(pred_df, gold_df, verbose=False)

    # Display Rich Summary Table
    if HAS_RICH:
        tbl = Table(title="Golden Benchmark Performance Metrics (32 Cases)", border_style="green")
        tbl.add_column("Evaluation Metric", style="bold white")
        tbl.add_column("Result / Accuracy", style="cyan")
        tbl.add_column("Target / Standard", style="dim")

        tbl.add_row("Case-Level Status Accuracy", f"[bold green]{results['status_accuracy']*100:.2f}%[/bold green]", "100.00%")
        tbl.add_row("Exact Sequence Match Rate", f"{results['exact_sequence_accuracy']*100:.2f}%", "60.00%+")
        tbl.add_row("Exact Step Tuple Match Rate", f"{results['step_tuple_accuracy']*100:.2f}%", "85.00%+")
        tbl.add_row("Phase Lifecycle Accuracy", f"{results['field_accuracy'].get('phase', 0)*100:.2f}%", "100.00%")
        tbl.add_row("Evidence Citation Accuracy", f"{results['field_accuracy'].get('evidence_id', 0)*100:.2f}%", "100.00%")
        tbl.add_row("Execution Latency (32 cases)", f"{elapsed:.2f}s ({elapsed/len(samples_df)*1000:.1f} ms/case)", "< 5.0s")
        console.print(tbl)
    else:
        print(f"  • Case Status Accuracy:        {results['status_accuracy']*100:.2f}%")
        print(f"  • Exact Sequence Match:        {results['exact_sequence_accuracy']*100:.2f}%")
        print(f"  • Step Tuple Accuracy:         {results['step_tuple_accuracy']*100:.2f}%")
        print(f"  • Total Time (32 cases):       {elapsed:.2f}s")

    return results


def validate_submission_file(output_path: str = "output.csv"):
    output_path = _resolve_path(output_path)
    print_msg("\n" + "=" * 70, "bold yellow")
    print_msg(f" 2. VALIDATING SUBMISSION FILE: {output_path}", "bold yellow")
    print_msg("=" * 70, "bold yellow")

    if not os.path.exists(output_path):
        print_msg(f"ERROR: {output_path} does not exist!", "bold red")
        return

    df = pd.read_csv(output_path)
    total_rows = len(df)
    errors = []

    if total_rows != 518:
        errors.append(f"Expected 518 rows, found {total_rows}")

    required_cols = ["case_id", "deletion_status", "steps_json"]
    if list(df.columns) != required_cols:
        errors.append(f"Invalid columns: {list(df.columns)} (expected {required_cols})")

    status_counts = {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0}

    for idx, row in df.iterrows():
        cid = str(row["case_id"]).strip()
        status = str(row["deletion_status"]).strip()
        raw_steps = str(row["steps_json"]).strip()

        status_counts[status] = status_counts.get(status, 0) + 1

        try:
            steps = json.loads(raw_steps)
        except Exception:
            errors.append(f"Row {idx} ({cid}): Invalid JSON in steps_json")
            continue

        if status == "NOT_APPLICABLE" and len(steps) != 0:
            errors.append(f"Row {idx} ({cid}): NOT_APPLICABLE must have empty steps_json '[]'")

        for s_idx, s in enumerate(steps, 1):
            if s.get("step_no") != s_idx:
                errors.append(f"Row {idx} ({cid}): Step index mismatch (got {s.get('step_no')}, expected {s_idx})")

            ev = s.get("evidence_id", "")
            if status == "COMPLETE" and not ev:
                errors.append(f"Row {idx} ({cid}): COMPLETE step missing evidence_id")
            elif status == "INCOMPLETE" and s.get("phase") in ["REMEDIATION"] and ev != "":
                errors.append(f"Row {idx} ({cid}): REMEDIATION step must have empty evidence_id")

    if HAS_RICH:
        if not errors:
            console.print(Panel(
                f"[bold green]SUCCESS: SUBMISSION VALIDATION PASSED (0 ERRORS)[/bold green]\n"
                f"Total Validated Rows: [cyan]{total_rows}[/cyan]\n"
                f"Distribution: [green]{status_counts['COMPLETE']} COMPLETE[/green] | "
                f"[yellow]{status_counts['INCOMPLETE']} INCOMPLETE[/yellow] | "
                f"[magenta]{status_counts['NOT_APPLICABLE']} NOT_APPLICABLE[/magenta]",
                border_style="green"
            ))
        else:
            console.print(Panel(
                f"[bold red]FAILED: VALIDATION FAILED WITH {len(errors)} ERRORS[/bold red]\n" +
                "\n".join(f"  • {e}" for e in errors[:10]),
                border_style="red"
            ))
    else:
        if not errors:
            print(f"[OK] SUBMISSION VALIDATION PASSED (0 ERRORS across {total_rows} rows)")
            print(f"  Status Breakdown: {status_counts}")
        else:
            print(f"[FAIL] VALIDATION FAILED with {len(errors)} errors:")
            for e in errors[:10]:
                print(f"  * {e}")


def main():
    parser = argparse.ArgumentParser(description="Northstar Deletion Audit Benchmark Suite")
    parser.add_argument("--samples", default="dataset/sample_deletion_requests.csv")
    parser.add_argument("--ground-truth", default="dataset/sample_output.csv")
    parser.add_argument("--submission", default="output.csv")
    parser.add_argument("--dataset-dir", default="dataset")
    args = parser.parse_args()

    benchmark_samples(args.samples, args.ground_truth, args.dataset_dir)
    validate_submission_file(args.submission)


if __name__ == "__main__":
    main()
