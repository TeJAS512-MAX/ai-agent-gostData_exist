"""
Northstar Shop AI-Powered Deletion Audit Agent
===============================================
CLI entry point for the 7-Stage Neuro-Symbolic Temporal Verification Engine.

Usage:
    python main.py \\
        --input  dataset/deletion_requests.csv \\
        --output output.csv \\
        --dataset-dir dataset

Arguments:
    --input        Path to input deletion_requests.csv
    --output       Path to write the submission output.csv
    --dataset-dir  Root directory containing dataset files and evidence/
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from typing import Optional

import pandas as pd

# ── sys.path setup ───────────────────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from code.engine.nstve import NSTPipeline
except ImportError:
    from engine.nstve import NSTPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Northstar Shop AI-Powered Deletion Audit Agent (NSTVE)"
    )
    parser.add_argument(
        "--input", default="dataset/deletion_requests.csv",
        help="Path to input deletion requests CSV"
    )
    parser.add_argument(
        "--output", default="output.csv",
        help="Path to write submission output CSV"
    )
    parser.add_argument(
        "--dataset-dir", default="dataset",
        help="Directory containing dataset files and evidence/"
    )
    return parser.parse_args()


# ── Sort helper ───────────────────────────────────────────────────────────────

def _case_sort_key(cid: str) -> int:
    digits = re.findall(r"\d+", str(cid))
    return int(digits[0]) if digits else 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    print("=" * 60)
    print("  Northstar Shop Deletion Audit Agent — NSTVE v2.0")
    print("=" * 60)
    print(f"  Input       : {args.input}")
    print(f"  Dataset dir : {args.dataset_dir}")
    print(f"  Output      : {args.output}")
    print()

    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Initialise 7-stage pipeline (pre-builds evidence index)
    t0 = time.time()
    print("Initialising 7-Stage NSTVE…")
    pipeline = NSTPipeline(dataset_dir=args.dataset_dir)
    print(f"Pipeline ready in {time.time() - t0:.2f}s\n")

    requests_df = pd.read_csv(args.input)
    total = len(requests_df)
    print(f"Auditing {total} deletion requests…\n")

    results = []
    status_counts: dict = {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0}

    t1 = time.time()
    for idx, row in requests_df.iterrows():
        cid = str(row["case_id"]).strip()
        status, steps = pipeline.run_case(row, all_cases_df=requests_df)
        status_counts[status] = status_counts.get(status, 0) + 1

        results.append({
            "case_id": cid,
            "deletion_status": status,
            "steps_json": json.dumps(steps),
        })

        n = idx + 1
        if n % 100 == 0 or n == total:
            elapsed = time.time() - t1
            print(f"  Processed {n}/{total} cases ({n/total*100:.1f}%) — {elapsed:.1f}s elapsed")

    elapsed_total = time.time() - t1

    # Build, sort, and write output
    out_df = pd.DataFrame(results)
    out_df["_sort"] = out_df["case_id"].apply(_case_sort_key)
    out_df = out_df.sort_values("_sort").drop(columns=["_sort"])
    out_df.to_csv(args.output, index=False)

    print()
    print("=" * 60)
    print("  Audit Complete")
    print(f"  Output rows      : {len(out_df)}")
    print(f"  Total time       : {elapsed_total:.2f}s")
    print(f"  Avg per request  : {elapsed_total/total*1000:.1f}ms")
    print("  Status Breakdown :")
    for st in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"):
        n = status_counts.get(st, 0)
        print(f"    {st:<20}: {n:>4} ({n/total*100:.1f}%)")
    print(f"  Written to       : {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
