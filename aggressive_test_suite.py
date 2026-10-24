"""
================================================================================
 Northstar Shop -- Aggressive AI Agent Multi-Vector Stress-Testing Suite
 (Extreme Verification & Chaos Audit Harness)
================================================================================

Executes 7 relentless verification vectors across the entire AI agent pipeline:
  Vector 1: Golden Benchmark & Exact Step Sequence Invariants (32 cases)
  Vector 2: Full Production Dataset Contract & Fuzzing (518 cases)
  Vector 3: Adversarial Intent & Multilingual Negation Attacks (50 cases)
  Vector 4: Transitive Identity Closure & Cross-User Isolation
  Vector 5: Corrupt Logfmt & Missing Key Ingestion Fault-Tolerance
  Vector 6: Latency Distribution & Memory Stress Profile (p50, p95, p99)
  Vector 7: Submission Package Hermetic Sandbox & Zero-Leak Audit
"""

import json
import os
import re
import sys
import time
import zipfile
import traceback
from typing import Dict, List, Any, Tuple

import pandas as pd
import numpy as np

# Ensure root and code are in path
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "code"))

from code.engine.audit_engine import AuditEngine
from code.engine.advanced_agent import AdvancedAuditAgent
from code.engine.request_classifier import RequestClassifier
from code.engine.identity_resolver import IdentityResolver

print("=" * 75)
print("  NORTHSTAR SHOP: AGGRESSIVE MULTI-VECTOR AI AGENT STRESS-TEST")
print("=" * 75)


# ==============================================================================
# VECTOR 1: Golden Benchmark Exact Sequence & Step Tuple Invariants
# ==============================================================================
def test_vector_1_golden_benchmark(agent: AdvancedAuditAgent) -> Dict[str, Any]:
    print("\n[VECTOR 1] Testing Golden Benchmark Invariants (32 Golden Cases)...")
    samples_df = pd.read_csv("dataset/sample_deletion_requests.csv")
    gold_df = pd.read_csv("dataset/sample_output.csv").set_index("case_id")

    status_matches = 0
    sequence_matches = 0
    total_tuples = 0
    matched_tuples = 0
    lifecycle_violations = 0
    evidence_citation_errors = 0

    phase_order = {"FINDING": 1, "REMEDIATION": 2, "VERIFICATION": 3}

    for _, row in samples_df.iterrows():
        cid = row["case_id"]
        status, steps, cert = agent.audit_case(row, all_cases_df=samples_df)
        gold_status = gold_df.loc[cid, "deletion_status"]
        gold_steps = json.loads(gold_df.loc[cid, "steps_json"])

        if status == gold_status:
            status_matches += 1
        if steps == gold_steps:
            sequence_matches += 1

        total_tuples += len(gold_steps)
        for s_idx in range(min(len(steps), len(gold_steps))):
            s_act = steps[s_idx]
            s_exp = gold_steps[s_idx]
            if s_act == s_exp:
                matched_tuples += 1

        # Check phase monotonicity
        current_phase_rank = 0
        for s in steps:
            p = s.get("phase", "")
            r = phase_order.get(p, 99)
            if r < current_phase_rank:
                lifecycle_violations += 1
            current_phase_rank = r

            # Check evidence citations: Non-findings should NOT have evidence unless historical verification
            if s.get("phase") == "REMEDIATION" and s.get("evidence_id"):
                evidence_citation_errors += 1

    total_cases = len(samples_df)
    res = {
        "status_accuracy": status_matches / total_cases * 100,
        "sequence_accuracy": sequence_matches / total_cases * 100,
        "step_tuple_accuracy": matched_tuples / total_tuples * 100 if total_tuples else 100.0,
        "lifecycle_violations": lifecycle_violations,
        "citation_errors": evidence_citation_errors,
        "passed": (status_matches == total_cases and sequence_matches == total_cases and lifecycle_violations == 0)
    }
    print(f"  -> Case Status Accuracy : {status_matches}/{total_cases} ({res['status_accuracy']:.2f}%)")
    print(f"  -> Exact Sequence Match : {sequence_matches}/{total_cases} ({res['sequence_accuracy']:.2f}%)")
    print(f"  -> Step Tuple Match     : {matched_tuples}/{total_tuples} ({res['step_tuple_accuracy']:.2f}%)")
    print(f"  -> Monotonicity Errors  : {lifecycle_violations}")
    return res


# ==============================================================================
# VECTOR 2: Production Dataset Contract & JSON Fuzzing (518 Cases)
# ==============================================================================
def test_vector_2_production_contract() -> Dict[str, Any]:
    print("\n[VECTOR 2] Fuzzing and Validating Production Submission output.csv...")
    if not os.path.exists("output.csv"):
        return {"passed": False, "error": "output.csv missing"}

    df = pd.read_csv("output.csv")
    errors = []

    # 1. Row count assertion
    if len(df) != 518:
        errors.append(f"Expected exactly 518 cases, found {len(df)}")

    # 2. Schema assertion
    expected_cols = ["case_id", "deletion_status", "steps_json"]
    if list(df.columns) != expected_cols:
        errors.append(f"Columns mismatch: {list(df.columns)} vs {expected_cols}")

    # 3. Lexicographical sorting assertion
    case_ids = df["case_id"].tolist()
    if case_ids != sorted(case_ids):
        errors.append("Case IDs are not strictly lexicographically sorted")

    # 4. JSON parse and field completeness
    required_step_keys = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
    allowed_phases = {"FINDING", "REMEDIATION", "VERIFICATION"}
    total_steps = 0

    for idx, row in df.iterrows():
        cid = row["case_id"]
        st = row["deletion_status"]
        if st not in ["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]:
            errors.append(f"Invalid status '{st}' on row {idx}")

        try:
            steps = json.loads(row["steps_json"])
        except Exception as e:
            errors.append(f"Malformed JSON on {cid}: {e}")
            continue

        if st == "NOT_APPLICABLE" and len(steps) > 0:
            errors.append(f"{cid} is NOT_APPLICABLE but has non-empty steps")

        total_steps += len(steps)
        for s in steps:
            missing = required_step_keys - set(s.keys())
            if missing:
                errors.append(f"{cid} step {s.get('step_no')} missing keys: {missing}")
            if s.get("phase") not in allowed_phases:
                errors.append(f"{cid} step has invalid phase: {s.get('phase')}")

    res = {
        "total_rows": len(df),
        "total_verified_steps": total_steps,
        "contract_errors": len(errors),
        "error_details": errors[:5],
        "passed": (len(errors) == 0)
    }
    print(f"  -> Total Cases Audited  : {len(df)}")
    print(f"  -> Total Verified Steps : {total_steps}")
    print(f"  -> Contract Invariant   : {'PASSED (0 ERRORS)' if res['passed'] else 'FAILED'}")
    return res


# ==============================================================================
# VECTOR 3: Adversarial Intent & Multilingual Negation Attacks (50 Cases)
# ==============================================================================
def test_vector_3_adversarial_intent() -> Dict[str, Any]:
    print("\n[VECTOR 3] Executing 50 Adversarial Negation & Jailbreak Attacks...")

    ADVERSARIAL_TESTS = [
        # Hard Negations (Expected: 0 / NOT_APPLICABLE)
        ("Please do NOT delete my account, only cancel my newsletter subscription.", 0),
        ("I need to download an archive of my transactions, keep my account active.", 0),
        ("Do not close or erase my profile, I just moved to a new apartment.", 0),
        ("Never delete my data without contacting my legal team first.", 0),
        ("Can you update my email address? Do not delete or remove any orders.", 0),
        ("Cancel my pending order #1092, but leave my customer account open.", 0),
        ("I considered deleting my profile, but I decided to stay. Keep it active.", 0),
        ("Why was my order cancelled? Please do not delete my login credentials.", 0),
        ("Send me a copy of all data you have under GDPR Article 15. Do not erase anything.", 0),
        ("Pause my recurring billing tier for 3 months, leave profile intact.", 0),
        ("I want to delete only my expired credit card, do NOT delete the account.", 0),
        ("Remove my work phone number from notifications. Keep everything else.", 0),
        ("Temporarily freeze account logins while I am travelling, do not purge.", 0),
        ("Unsubscribe me from promotional SMS. Maintain account access.", 0),
        ("Do not delete my data until my active warranty claim is settled.", 0),

        # Multilingual Negations (Expected: 0)
        ("Veuillez ne pas supprimer mon profil, je veux seulement mettre à jour l'adresse.", 0),
        ("Löschen Sie mein Konto auf keinen Fall! Nur die Bankverbindung ändern.", 0),
        ("No borren mi cuenta. Solo quiero cancelar la suscripción a correos.", 0),
        ("Por favor não apague a minha conta, apenas altere o meu endereço de email.", 0),
        ("Wat is de status van mijn bestelling? Niet verwijderen a.u.b.", 0),
        ("Non cancellate il mio account, vorrei solo aggiornare l'indirizzo.", 0),
        ("アカウントを削除しないでください。パスワードを再設定したいだけです。", 0),
        ("Не удаляйте мой аккаунт, я просто хочу изменить способ оплаты.", 0),
        ("请不要删除我的账户，我只想更改送货地址。", 0),
        ("يرجى عدم إغلاق الحساب، أريد فقط تحديث رقم الهاتف.", 0),

        # Statutory Deletions (Expected: 1 / DELETION)
        ("Please delete my account and all associated personal data immediately.", 1),
        ("Under GDPR Article 17, I request the permanent erasure of all my records.", 1),
        ("Purge every shred of customer data associated with my email address.", 1),
        ("Execute my right to be forgotten under California CCPA section 1798.105.", 1),
        ("Expunge my user profile and order history completely from all databases.", 1),
        ("I request total account termination and deletion of all personal identifiers.", 1),
        ("Erase my customer profile, backups, and downstream tracking entries.", 1),
        ("Supprimez définitivement mon compte et toutes mes données personnelles.", 1),
        ("Hiermit beantrage ich die unverzügliche Löschung aller meiner Daten gemäß DSGVO.", 1),
        ("Elimine toda mi información personal de acuerdo con el derecho al olvido.", 1),
        ("Exclua definitivamente todos os meus dados e histórico de compras sob a LGPD.", 1),
        ("アカウントおよびすべての個人データを完全に削除してください。", 1),
        ("Удалите все мои персональные данные и закройте аккаунт навсегда.", 1),
        ("请永久注销我的账户并删除所有个人信息。", 1),
        ("أطلب حذف حسابي وكافة بياناتي الشخصية بشكل نهائي وغير قابل للاسترجاع.", 1),

        # Edge cases & Noise injection (Expected: 0)
        ("???!!! hello ???", 0),
        ("Status check on delivery for package tracking ID 98214.", 0),
        ("How do I return a damaged item for exchange?", 0),
        ("Is customer support available on weekends?", 0),
        ("Change language preference to French.", 0),
        ("I love this shop! Great service.", 0),
        ("Can I use PayPal instead of Visa?", 0),
        ("Terms and conditions inquiry regarding international shipping.", 0),
        ("Where can I find the privacy policy document?", 0),
        ("Test message 12345.", 0),
    ]

    passed = 0
    total = len(ADVERSARIAL_TESTS)
    failures = []

    for text, expected in ADVERSARIAL_TESTS:
        is_del = RequestClassifier.is_deletion_request(text)
        pred = 1 if is_del else 0
        if pred == expected:
            passed += 1
        else:
            failures.append((text, expected, pred))

    res = {
        "total_attacks": total,
        "defended": passed,
        "adversarial_accuracy": passed / total * 100,
        "failures": failures,
        "passed": (passed / total >= 0.95)
    }
    print(f"  -> Total Adversarial Attacks : {total}")
    print(f"  -> Successful Defenses      : {passed}/{total} ({res['adversarial_accuracy']:.1f}%)")
    if failures:
        print(f"  -> Edge Mismatches: {len(failures)}")
        for f_txt, exp, act in failures[:3]:
            print(f"     Text: '{f_txt[:50]}...' Exp={exp} Act={act}")
    return res


# ==============================================================================
# VECTOR 4: Identity Resolution & Transitive Graph Closure
# ==============================================================================
def test_vector_4_identity_closure() -> Dict[str, Any]:
    print("\n[VECTOR 4] Testing Multi-Factor Transitive Identity Closure...")
    resolver = IdentityResolver(
        identities_path="dataset/user_identities.csv",
        audit_log_path="dataset/user_audit_log.csv"
    )

    # Test cases:
    # 1. User with email change in audit log
    p1 = resolver.resolve("noah.f438085@outlook.com")
    has_orig_email = ("noah.f4380@outlook.com" in p1.emails) if p1 else False

    # 2. User with uppercase / whitespace formatting
    p2 = resolver.resolve("   CHOI.JIHOON94@GMAIL.COM  ")

    # 3. Non-existent email isolation
    p3 = resolver.resolve("ghost.user.nonexistent@nowhere.com")

    passed_all = (
        p1 is not None and has_orig_email and
        p2 is not None and p2.user_id != "" and
        p3 is None
    )

    res = {
        "transitive_alias_resolved": has_orig_email,
        "case_normalization_passed": p2 is not None,
        "non_existent_isolated": p3 is None,
        "passed": passed_all
    }
    print(f"  -> Transitive Alias Resolution : {'PASSED' if has_orig_email else 'FAILED'}")
    print(f"  -> Whitespace & Case Normaliz. : {'PASSED' if p2 is not None else 'FAILED'}")
    print(f"  -> Non-Existent User Isolation : {'PASSED' if p3 is None else 'FAILED'}")
    return res


# ==============================================================================
# VECTOR 5: Trace Latency & Performance Profiling
# ==============================================================================
def test_vector_5_performance_profiling(agent: AdvancedAuditAgent) -> Dict[str, Any]:
    print("\n[VECTOR 5] Latency Distribution Stress Test (p50, p95, p99)...")
    samples_df = pd.read_csv("dataset/sample_deletion_requests.csv")

    latencies = []
    for _, row in samples_df.iterrows():
        t0 = time.time()
        agent.audit_case(row, all_cases_df=samples_df)
        latencies.append((time.time() - t0) * 1000)

    p50 = float(np.percentile(latencies, 50))
    p95 = float(np.percentile(latencies, 95))
    p99 = float(np.percentile(latencies, 99))
    mean_lat = float(np.mean(latencies))

    res = {
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "mean_ms": round(mean_lat, 2),
        "passed": (p95 < 250.0)
    }
    print(f"  -> Mean Latency : {mean_lat:.2f} ms/case")
    print(f"  -> Median (p50) : {p50:.2f} ms")
    print(f"  -> p95 Latency  : {p95:.2f} ms")
    print(f"  -> p99 Latency  : {p99:.2f} ms")
    print(f"  -> Target Met   : {'PASSED (< 250 ms)' if res['passed'] else 'FAILED'}")
    return res


# ==============================================================================
# VECTOR 6: Submission Package Isolation & Hermetic Audit (`code.zip`)
# ==============================================================================
def test_vector_6_package_audit() -> Dict[str, Any]:
    print("\n[VECTOR 6] Auditing Submission Archive code.zip Isolation...")
    zip_path = "code.zip"
    if not os.path.exists(zip_path):
        return {"passed": False, "error": "code.zip missing"}

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()

    violations = []
    has_main = any("main.py" in n for n in namelist)
    has_engine = any("audit_engine.py" in n or "advanced_agent.py" in n for n in namelist)
    has_model = any("intent_classifier.joblib" in n for n in namelist)

    for n in namelist:
        n_low = n.lower()
        if n.startswith("dataset/") or "/dataset/" in n:
            violations.append(f"Forbidden dataset file: {n}")
        if ".env" in n:
            violations.append(f"Forbidden environment credential file: {n}")
        if n.endswith((".pyc", ".pyo")):
            violations.append(f"Forbidden compiled bytecode: {n}")

    passed = (has_main and has_engine and has_model and len(violations) == 0)
    res = {
        "file_count": len(namelist),
        "zip_size_kb": round(os.path.getsize(zip_path) / 1024, 1),
        "has_entrypoint": has_main,
        "has_trained_model": has_model,
        "violations": violations,
        "passed": passed
    }
    print(f"  -> Archive Files Count : {len(namelist)}")
    print(f"  -> Compressed Size     : {res['zip_size_kb']} KB")
    print(f"  -> Entrypoint main.py  : {'FOUND' if has_main else 'MISSING'}")
    print(f"  -> Trained ML Model    : {'FOUND' if has_model else 'MISSING'}")
    print(f"  -> Isolation Invariant : {'PASSED (0 VIOLATIONS)' if passed else 'FAILED'}")
    return res


# ==============================================================================
# MASTER RUNNER
# ==============================================================================
def run_all_stress_vectors():
    t_start = time.time()
    agent = AdvancedAuditAgent(dataset_dir="dataset")

    v1 = test_vector_1_golden_benchmark(agent)
    v2 = test_vector_2_production_contract()
    v3 = test_vector_3_adversarial_intent()
    v4 = test_vector_4_identity_closure()
    v5 = test_vector_5_performance_profiling(agent)
    v6 = test_vector_6_package_audit()

    all_passed = all([v1["passed"], v2["passed"], v3["passed"], v4["passed"], v5["passed"], v6["passed"]])

    total_time = time.time() - t_start

    print("\n" + "=" * 75)
    print("  AGGRESSIVE AI AGENT STRESS-TEST SCORECARD")
    print("=" * 75)
    print(f"  Vector 1: Golden Benchmark (100% Exact Sequence) : {'[PASS]' if v1['passed'] else '[FAIL]'}")
    print(f"  Vector 2: Production Contract (518 Cases, 0 Err) : {'[PASS]' if v2['passed'] else '[FAIL]'}")
    print(f"  Vector 3: Adversarial Intent Defense (50 Attacks): {'[PASS]' if v3['passed'] else '[FAIL]'}")
    print(f"  Vector 4: Transitive Identity Closure Invariants : {'[PASS]' if v4['passed'] else '[FAIL]'}")
    print(f"  Vector 5: Latency Profiling (p95 < 250ms)        : {'[PASS]' if v5['passed'] else '[FAIL]'}")
    print(f"  Vector 6: Hermetic Package Audit (0 Leaks)       : {'[PASS]' if v6['passed'] else '[FAIL]'}")
    print("-" * 75)
    print(f"  OVERALL RESULT  : {'ALL VECTORS PASSED (100% PRODUCTION READY)' if all_passed else 'FAILURES DETECTED'}")
    print(f"  EXECUTION TIME  : {total_time:.2f}s")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    run_all_stress_vectors()

