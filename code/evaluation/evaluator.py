#!/usr/bin/env python3
"""
evaluation/evaluator.py
========================
Automated grading script comparing predictions against sample_output.csv.

Computes:
  - Case-Level Status Accuracy
  - Step-Level / Field-Level Accuracy
  - Sequence (Exact Array) Accuracy

Usage:
    python evaluation/evaluator.py \\
        --predictions sample_predictions.csv \\
        --ground-truth dataset/sample_output.csv
"""

import argparse
import json
import sys
import os
from typing import Any, Dict, List, Tuple

import pandas as pd

STEP_FIELDS = ["phase", "system_id", "resource_id", "operation", "state", "evidence_id"]


def load_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    return pd.read_csv(path)


def parse_steps(raw: str) -> List[Dict[str, Any]]:
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return val
    except Exception:
        pass
    return []


def step_tuple(s: Dict[str, Any]) -> Tuple:
    return tuple(str(s.get(f, "")) for f in STEP_FIELDS)


def compare_steps(
    pred_steps: List[Dict],
    gold_steps: List[Dict],
) -> Tuple[bool, int, int, Dict[str, int]]:
    """
    Returns:
      exact_match: bool (all step tuples match in sequence)
      aligned_count: number of aligned positions (min of lengths)
      matching_tuples: number of exact-matching tuples in aligned positions
      field_hits: dict {field: hits}
    """
    pred_ops = [step_tuple(s) for s in pred_steps]
    gold_ops = [step_tuple(s) for s in gold_steps]
    exact_match = pred_ops == gold_ops

    aligned = min(len(pred_steps), len(gold_steps))
    field_hits: Dict[str, int] = {f: 0 for f in STEP_FIELDS}
    matching_tuples = 0
    for i in range(aligned):
        p, g = pred_steps[i], gold_steps[i]
        full_match = True
        for fi, f in enumerate(STEP_FIELDS):
            if str(p.get(f, "")) == str(g.get(f, "")):
                field_hits[f] += 1
            else:
                full_match = False
        if full_match:
            matching_tuples += 1

    return exact_match, aligned, matching_tuples, field_hits


def evaluate(pred_df: pd.DataFrame, gold_df: pd.DataFrame, verbose: bool = True) -> Dict:
    # Align on case_id
    gold_idx = gold_df.set_index("case_id")
    pred_idx = pred_df.set_index("case_id")

    common_ids = gold_idx.index.intersection(pred_idx.index)
    n = len(common_ids)

    status_correct = 0
    exact_seq = 0
    total_gold_steps = 0
    total_pred_steps = 0
    total_aligned = 0
    total_matching_tuples = 0
    total_field_hits: Dict[str, int] = {f: 0 for f in STEP_FIELDS}

    mismatched_cases = []

    for cid in sorted(common_ids, key=lambda x: int("".join(filter(str.isdigit, x))) if any(c.isdigit() for c in x) else 0):
        gold_row = gold_idx.loc[cid]
        pred_row = pred_idx.loc[cid]

        gold_status = str(gold_row.get("deletion_status", "")).strip()
        pred_status = str(pred_row.get("deletion_status", "")).strip()

        gold_steps = parse_steps(str(gold_row.get("steps_json", "[]")))
        pred_steps = parse_steps(str(pred_row.get("steps_json", "[]")))

        status_ok = gold_status == pred_status
        if status_ok:
            status_correct += 1

        exact_match, aligned, matching_tuples, field_hits = compare_steps(pred_steps, gold_steps)
        if exact_match:
            exact_seq += 1
        else:
            mismatched_cases.append({
                "case_id": cid,
                "gold_status": gold_status,
                "pred_status": pred_status,
                "gold_steps": len(gold_steps),
                "pred_steps": len(pred_steps),
                "gold_ops": [step_tuple(s) for s in gold_steps],
                "pred_ops": [step_tuple(s) for s in pred_steps],
            })

        total_gold_steps += len(gold_steps)
        total_pred_steps += len(pred_steps)
        total_aligned += aligned
        total_matching_tuples += matching_tuples
        for f in STEP_FIELDS:
            total_field_hits[f] += field_hits[f]

    if verbose:
        _print_report(
            n, status_correct, exact_seq,
            total_gold_steps, total_pred_steps, total_aligned,
            total_matching_tuples, total_field_hits, mismatched_cases,
        )

    return {
        "n_cases": n,
        "status_accuracy": status_correct / n if n else 0.0,
        "exact_sequence_accuracy": exact_seq / n if n else 0.0,
        "step_tuple_accuracy": total_matching_tuples / total_gold_steps if total_gold_steps else 0.0,
        "field_accuracy": {
            f: total_field_hits[f] / total_aligned for f in STEP_FIELDS
        } if total_aligned else {},
    }


def _print_report(
    n, status_correct, exact_seq,
    total_gold, total_pred, total_aligned,
    matching_tuples, field_hits, mismatched,
):
    sep = "=" * 60
    print(sep)
    print("  Northstar Shop Deletion Audit - Evaluation Report")
    print(sep)
    print(f"  Total cases evaluated  : {n}")
    print()
    if n == 0:
        print("  WARNING: 0 overlapping case_ids between predictions and ground-truth.")
        print("  Note: sample_output.csv covers case_01-case_32 (from sample_deletion_requests.csv),")
        print("  whereas production output.csv covers case_33-case_550 (from deletion_requests.csv).")
        print(sep)
        return

    print(f"  Case Status Accuracy   : {status_correct}/{n} ({status_correct/n*100:.2f}%)")
    print(f"  Exact Sequence Match   : {exact_seq}/{n} ({exact_seq/n*100:.2f}%)")
    print()
    print(f"  Total Gold Steps       : {total_gold}")
    print(f"  Total Pred Steps       : {total_pred}")
    print(f"  Aligned Positions      : {total_aligned}")
    print(f"  Exact Tuple Matches    : {matching_tuples}/{total_gold} ({matching_tuples/total_gold*100:.2f}%)")
    print()
    print("  Field-Level Accuracy (aligned positions):")
    for f in STEP_FIELDS:
        hits = field_hits[f]
        pct = hits / total_aligned * 100 if total_aligned else 0.0
        print(f"    {f:<20} : {hits}/{total_aligned} ({pct:.2f}%)")
    print()

    if mismatched:
        print(f"  Cases with step mismatches ({len(mismatched)}):")
        for m in mismatched[:10]:
            print(f"    [{m['case_id']}] gold={m['gold_steps']} steps / pred={m['pred_steps']} steps")
    print(sep)


def main():
    parser = argparse.ArgumentParser(description="Northstar Shop Deletion Audit Evaluator")
    parser.add_argument(
        "--predictions", required=True,
        help="Path to predictions CSV (case_id, deletion_status, steps_json)"
    )
    parser.add_argument(
        "--ground-truth", default="dataset/sample_output.csv",
        help="Path to ground-truth CSV (case_id, deletion_status, steps_json)"
    )
    args = parser.parse_args()

    pred_df = load_csv(args.predictions)
    gold_df = load_csv(args.ground_truth)

    results = evaluate(pred_df, gold_df, verbose=True)
    if results["n_cases"] == 0:
        return 0
    return 0 if results["status_accuracy"] >= 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
