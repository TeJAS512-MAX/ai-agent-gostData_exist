import sys, os
sys.path.insert(0, os.path.abspath('.'))

import json
import pandas as pd
from code.engine.audit_engine import AuditEngine

engine = AuditEngine()
samples_df = pd.read_csv('dataset/sample_deletion_requests.csv')
sample_out_df = pd.read_csv('dataset/sample_output.csv')
merged = pd.merge(samples_df, sample_out_df, on='case_id')

status_correct = 0
total_cases = len(merged)

total_gold_steps = 0
matching_steps_count = 0
exact_case_steps_matches = 0

print("Benchmarking AuditEngine against 32 Sample Cases:\n")

for idx, r in merged.iterrows():
    cid = r['case_id']
    gold_status = r['deletion_status']
    gold_steps = json.loads(r['steps_json'])
    
    pred_status, pred_steps = engine.audit_case(r, all_cases_df=samples_df)
    
    st_match = (pred_status == gold_status)
    if st_match:
        status_correct += 1
        
    gold_str = json.dumps(gold_steps, sort_keys=True)
    pred_str = json.dumps(pred_steps, sort_keys=True)
    exact_match = (gold_str == pred_str)
    if exact_match:
        exact_case_steps_matches += 1
        
    print(f"[{cid}] Pred: {pred_status:<11} | Gold: {gold_status:<11} | Match: {st_match} | Exact Steps: {exact_match} | Pred Steps: {len(pred_steps)} | Gold Steps: {len(gold_steps)}")
    if not exact_match:
        pred_ops = [(s['phase'], s['system_id'], s['resource_id'], s['operation']) for s in pred_steps]
        gold_ops = [(s['phase'], s['system_id'], s['resource_id'], s['operation']) for s in gold_steps]
        if pred_ops != gold_ops:
            print(f"   Pred ops: {pred_ops}")
            print(f"   Gold ops: {gold_ops}")

print(f"\n==========================================")
print(f"Case Status Accuracy: {status_correct}/{total_cases} ({status_correct/total_cases*100:.1f}%)")
print(f"Exact Case Steps Match: {exact_case_steps_matches}/{total_cases} ({exact_case_steps_matches/total_cases*100:.1f}%)")
print(f"==========================================")
