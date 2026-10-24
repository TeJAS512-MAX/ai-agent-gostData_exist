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
    python evaluation/evaluator.py
    python evaluation/evaluator.py sample_predictions.csv
    python evaluation/evaluator.py --predictions sample_predictions.csv --ground-truth dataset/sample_output.csv
"""

import argparse
import json
import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

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
    field_hits = {f: 0 for f in STEP_FIELDS}

    aligned = min(len(pred_steps), len(gold_steps))
    matching_tuples = 0

    for i in range(aligned):
        p, g = pred_steps[i], gold_steps[i]
        all_match = True
        for f in STEP_FIELDS:
            pv = str(p.get(f, "")).strip()
            gv = str(g.get(f, "")).strip()
            if pv == gv:
                field_hits[f] += 1
            else:
                all_match = False
        if all_match:
            matching_tuples += 1

    exact_seq = (
        len(pred_steps) == len(gold_steps)
        and matching_tuples == len(gold_steps)
    )
    return exact_seq, aligned, matching_tuples, field_hits


def evaluate(
    pred_df: pd.DataFrame,
    gold_df: pd.DataFrame,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Evaluates predictions against gold answers.
    Expects columns: case_id, deletion_status, steps_json
    """
    gold_map = {str(r["case_id"]).strip(): r for _, r in gold_df.iterrows()}
    pred_map = {str(r["case_id"]).strip(): r for _, r in pred_df.iterrows()}

    common_cases = [cid for cid in gold_map if cid in pred_map]
    n = len(common_cases)

    status_correct = 0
    exact_seq = 0
    total_aligned = 0
    matching_tuples = 0
    field_hits = {f: 0 for f in STEP_FIELDS}
    total_gold_steps = 0
    total_pred_steps = 0

    mismatched = []

    for cid in common_cases:
        gold_row = gold_map[cid]
        pred_row = pred_map[cid]

        # Status check
        gold_status = str(gold_row.get("deletion_status", "")).strip().upper()
        pred_status = str(pred_row.get("deletion_status", "")).strip().upper()
        if gold_status == pred_status:
            status_correct += 1

        # Step check
        g_steps = parse_steps(str(gold_row.get("steps_json", "[]")))
        p_steps = parse_steps(str(pred_row.get("steps_json", "[]")))
        total_gold_steps += len(g_steps)
        total_pred_steps += len(p_steps)

        is_exact, aligned, matches, hits = compare_steps(p_steps, g_steps)
        if is_exact:
            exact_seq += 1
        else:
            mismatched.append({
                "case_id": cid,
                "gold_status": gold_status,
                "pred_status": pred_status,
                "gold_steps": len(g_steps),
                "pred_steps": len(p_steps),
                "matches": matches,
            })

        total_aligned += aligned
        matching_tuples += matches
        for f in STEP_FIELDS:
            field_hits[f] += hits[f]

    status_acc = status_correct / n if n else 0.0
    seq_acc = exact_seq / n if n else 0.0
    step_acc = matching_tuples / total_gold_steps if total_gold_steps else 0.0
    field_acc = {
        f: field_hits[f] / total_aligned if total_aligned else 0.0
        for f in STEP_FIELDS
    }

    results = {
        "n_cases": n,
        "status_correct": status_correct,
        "status_accuracy": status_acc,
        "exact_sequence_matches": exact_seq,
        "exact_sequence_accuracy": seq_acc,
        "total_gold_steps": total_gold_steps,
        "total_pred_steps": total_pred_steps,
        "total_aligned_positions": total_aligned,
        "exact_matching_tuples": matching_tuples,
        "step_tuple_accuracy": step_acc,
        "field_hits": field_hits,
        "field_accuracy": field_acc,
        "mismatched_cases": mismatched,
    }

    if verbose:
        print_report(results)

    return results


def print_report(results: Dict[str, Any]):
    sep = "=" * 65
    n = results["n_cases"]
    status_correct = results["status_correct"]
    exact_seq = results["exact_sequence_matches"]
    total_gold = results["total_gold_steps"]
    total_pred = results["total_pred_steps"]
    total_aligned = results["total_aligned_positions"]
    matching_tuples = results["exact_matching_tuples"]
    field_hits = results["field_hits"]
    mismatched = results["mismatched_cases"]

    print()
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


def _resolve_candidate(path_str: Optional[str], default_names: List[str]) -> Optional[str]:
    if path_str:
        if os.path.isfile(path_str):
            return path_str
        for prefix in [".", "..", "../.."]:
            cand = os.path.join(prefix, path_str)
            if os.path.isfile(cand):
                return os.path.abspath(cand)
        return path_str

    for name in default_names:
        for prefix in [".", "..", "../.."]:
            cand = os.path.join(prefix, name)
            if os.path.isfile(cand):
                return os.path.abspath(cand)
    return None


def main():
    parser = argparse.ArgumentParser(description="Northstar Shop Deletion Audit Evaluator")
    parser.add_argument(
        "target", nargs="?", default=None,
        help="Path to predictions CSV (optional positional argument)"
    )
    parser.add_argument(
        "--predictions", "-p", default=None,
        help="Path to predictions CSV (case_id, deletion_status, steps_json)"
    )
    parser.add_argument(
        "--ground-truth", "-g", default=None,
        help="Path to ground-truth CSV (case_id, deletion_status, steps_json)"
    )
    args = parser.parse_args()

    pred_target = args.predictions or args.target
    pred_path = _resolve_candidate(pred_target, ["sample_predictions.csv", "output.csv"])

    gold_path = _resolve_candidate(args.ground_truth, ["dataset/sample_output.csv"])
    if not gold_path or not os.path.isfile(gold_path):
        print(f"ERROR: Ground-truth file not found: {args.ground_truth or 'dataset/sample_output.csv'}")
        return 1

    # If sample_predictions.csv doesn't exist yet, generate it via benchmark
    if not pred_path or not os.path.isfile(pred_path) or pred_target is None:
        if not os.path.isfile("sample_predictions.csv"):
            try:
                # Add repo root to sys.path
                root_dir = str(Path(__file__).resolve().parent.parent.parent)
                sys.path.insert(0, root_dir)
                from run_benchmark import benchmark_samples
                print("Running calibration on 32 golden samples to generate predictions...")
                benchmark_samples()
                pred_path = _resolve_candidate("sample_predictions.csv", ["sample_predictions.csv"])
            except Exception as e:
                pass

    if not pred_path or not os.path.isfile(pred_path):
        print(f"ERROR: Predictions file not found: {pred_target or 'sample_predictions.csv'}")
        return 1

    print(f"Evaluating: {os.path.basename(pred_path)} against {os.path.basename(gold_path)}...")
    pred_df = load_csv(pred_path)
    gold_df = load_csv(gold_path)

    results = evaluate(pred_df, gold_df, verbose=True)
    if results["n_cases"] == 0:
        return 0
    return 0 if results["status_accuracy"] >= 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
