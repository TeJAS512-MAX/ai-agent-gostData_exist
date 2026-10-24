import sys
import os
import re
import argparse
import json
import pandas as pd
from typing import Optional

# Ensure both repository root and code directory are on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from code.engine.audit_engine import AuditEngine
except ImportError:
    from engine.audit_engine import AuditEngine

def parse_args():
    parser = argparse.ArgumentParser(description="Northstar Shop Deletion Audit Agent")
    parser.add_argument(
        "--input",
        type=str,
        default="dataset/deletion_requests.csv",
        help="Path to deletion requests CSV input file"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output.csv",
        help="Path to save output CSV submission file"
    )
    parser.add_argument(
        "--dataset-dir",
        type=str,
        default="dataset",
        help="Directory containing the full dataset and evidence"
    )
    return parser.parse_args()

def main():
    args = parse_args()
    
    input_path = args.input
    output_path = args.output
    dataset_dir = args.dataset_dir

    print(f"==================================================")
    print(f" Northstar Shop AI-Powered Deletion Audit Agent")
    print(f"==================================================")
    print(f"Loading input:       {input_path}")
    print(f"Dataset directory:   {dataset_dir}")
    print(f"Target output:       {output_path}")

    if not os.path.exists(input_path):
        print(f"Error: Input file '{input_path}' not found!")
        sys.exit(1)

    print("\nInitializing AuditEngine & indexing evidence...")
    engine = AuditEngine(dataset_dir=dataset_dir)
    print("Evidence index ready.")

    requests_df = pd.read_csv(input_path)
    total_cases = len(requests_df)
    print(f"Auditing {total_cases} deletion requests...\n")

    results = []
    status_counts = {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0}

    for idx, row in requests_df.iterrows():
        cid = str(row['case_id']).strip()
        status, steps = engine.audit_case(row, all_cases_df=requests_df)
        status_counts[status] = status_counts.get(status, 0) + 1

        steps_json_str = json.dumps(steps)
        results.append({
            "case_id": cid,
            "deletion_status": status,
            "steps_json": steps_json_str
        })

        if (idx + 1) % 50 == 0 or (idx + 1) == total_cases:
            print(f"Processed {idx + 1}/{total_cases} cases ({(idx + 1)/total_cases*100:.1f}%)")

    # Format output DataFrame and sort by case_id
    out_df = pd.DataFrame(results)
    
    # Sort by numeric case index if case_XXX format
    def case_sort_key(cid: str):
        digits = re.findall(r'\d+', str(cid))
        return int(digits[0]) if digits else str(cid)

    out_df['sort_k'] = out_df['case_id'].apply(case_sort_key)
    out_df = out_df.sort_values('sort_k').drop(columns=['sort_k'])

    out_df.to_csv(output_path, index=False)
    print(f"\n==================================================")
    print(f" Audit Complete! Results written to: {output_path}")
    print(f" Total rows: {len(out_df)}")
    print(f" Status Breakdown:")
    for st, count in sorted(status_counts.items()):
        print(f"   {st:<16}: {count} ({count/total_cases*100:.1f}%)")
    print(f"==================================================")

if __name__ == "__main__":
    main()
