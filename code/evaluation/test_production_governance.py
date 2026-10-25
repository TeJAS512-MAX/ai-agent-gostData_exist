import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
CODE_DIR = os.path.join(REPO_ROOT, "code")
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

from code.engine.production_governance import (
    ModelSecurityGuard,
    SignedApprovalToken,
    SecurityBreachError,
    ConnectorRegistry,
    EvidenceConnector,
    ResourceRef,
    RecordState,
    RiskClassifier,
    RemediationRisk,
    HumanInTheLoopApprovalQueue,
    ProposedRemediation,
    ContinuousDecayReverificationEngine,
    RegulatorySLATracker,
)


class MockDatabaseConnector:
    @property
    def system_id(self) -> str:
        return "postgres_replica"

    def check_health(self) -> bool:
        return True

    def discover_resources(self, user_identifiers):
        return [ResourceRef("postgres_replica", "acc_101", "USER_PROFILE")]

    def get_state(self, resource, as_of):
        return RecordState.PRESENT

    def execute_dry_run(self, resource, action):
        return {"dry_run": True, "rows_affected": 1}


class TestProductionGovernance(unittest.TestCase):
    """Verifies enterprise extensions: connectors, safety queue, decay sweeps, and legal SLAs."""

    def test_01_connector_registry_and_uncovered_system_detection(self):
        registry = ConnectorRegistry()
        conn = MockDatabaseConnector()
        registry.register(conn)

        expected = {"postgres_replica", "s3_archive", "elasticsearch"}
        audit = registry.audit_coverage(expected)

        self.assertFalse(audit["coverage_complete"])
        self.assertIn("s3_archive", audit["uncovered_systems"])
        self.assertIn("elasticsearch", audit["uncovered_systems"])
        self.assertEqual(audit["total_registered"], 1)

    def test_02_risk_classifier_levels(self):
        r_low = RiskClassifier.evaluate_risk("REDACT_RECORD", "app_logs", "LOG")
        self.assertEqual(r_low, RemediationRisk.LOW)

        r_high = RiskClassifier.evaluate_risk("DELETE_RECORD", "user_service", "USER_PROFILE")
        self.assertEqual(r_high, RemediationRisk.HIGH)

        r_critical = RiskClassifier.evaluate_risk("DELETE_RECORD", "finance_ledger", "TAX_RECORD")
        self.assertEqual(r_critical, RemediationRisk.CRITICAL)

    def test_03_human_in_the_loop_approval_guard(self):
        queue = HumanInTheLoopApprovalQueue(hourly_blast_radius_limit=5)
        proposal = ProposedRemediation(
            proposal_id="prop_001",
            case_id="case_123",
            user_id="user_99",
            system_id="user_service",
            resource_id="acc_99",
            operation="DELETE_RECORD",
            target_state="ABSENT",
            evidence_id="ev_01",
            risk_level=RemediationRisk.HIGH,
            legal_basis="GDPR Art 17(1)",
        )
        queue.submit_proposal(proposal)

        # 1. Unapproved execution must raise PermissionError
        with self.assertRaises(PermissionError):
            queue.execute_with_guard(proposal, lambda: True)

        # 2. Unauthorized role cannot approve
        with self.assertRaises(PermissionError):
            queue.approve("prop_001", "INTERN", "Bob")

        # 3. DPO approves
        approved = queue.approve("prop_001", "DPO", "Sarah_Connor")
        self.assertTrue(approved)

        # 4. Approved execution succeeds and creates rollback snapshot
        executed = queue.execute_with_guard(proposal, lambda: True)
        self.assertTrue(executed)
        self.assertTrue(proposal.is_executed)
        self.assertIsNotNone(proposal.dry_run_snapshot)
        self.assertEqual(proposal.dry_run_snapshot["prior_state"], "PRESENT")

    def test_04_continuous_decay_reverification_sweeps(self):
        engine = ContinuousDecayReverificationEngine()
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        jobs = engine.schedule_decay_sweeps("case_005", "user_5", t0)

        self.assertEqual(len(jobs), 3)
        self.assertEqual([j.checkpoint_day for j in jobs], [7, 30, 90])

        # Sweep at Day 10 (Day 7 job is due, Day 30 and 90 are not)
        t_day10 = t0 + timedelta(days=10)
        # Probe reports user_5 is clean
        executed = engine.run_sweep(t_day10, audit_probe=lambda uid: True)
        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0].checkpoint_day, 7)
        self.assertFalse(executed[0].drift_detected)

        # Sweep at Day 35: Probe detects resurrection drift!
        t_day35 = t0 + timedelta(days=35)
        executed_drift = engine.run_sweep(t_day35, audit_probe=lambda uid: False)
        self.assertEqual(len(executed_drift), 1)
        self.assertEqual(executed_drift[0].checkpoint_day, 30)
        self.assertTrue(executed_drift[0].drift_detected)

    def test_05_regulatory_sla_tracker_and_sub_processor_cascade(self):
        tracker = RegulatorySLATracker()
        now = datetime.now(timezone.utc)
        req_time = now - timedelta(days=26)

        sla = tracker.compute_sla_deadline(req_time)
        self.assertFalse(sla["is_breached"])
        self.assertTrue(sla["escalation_risk"])  # 4 days remaining (< 5 days)

        # Dispatch to 3 sub-processors under GDPR Art. 28
        vendors = [
            {"id": "sp_stripe", "name": "Stripe Payments"},
            {"id": "sp_braze", "name": "Braze Marketing"},
            {"id": "sp_zendesk", "name": "Zendesk Support"},
        ]
        dispatches = tracker.dispatch_sub_processor_erasure("user_42", vendors)
        self.assertEqual(len(dispatches), 3)
        self.assertEqual(dispatches[0].vendor_name, "Stripe Payments")



    def test_06_model_security_guard_tamper_detection(self):
        import tempfile
        import joblib

        with tempfile.TemporaryDirectory() as tmpdir:
            model_file = os.path.join(tmpdir, "test_model.joblib")
            dummy_obj = {"name": "test_classifier", "weights": [0.1, 0.4, 0.9]}
            joblib.dump(dummy_obj, model_file)

            # Compute and store HMAC signature
            sig = ModelSecurityGuard.sign_model(model_file)
            self.assertTrue(os.path.exists(model_file + ".sig"))

            # 1. Unmodified model loads cleanly
            loaded = ModelSecurityGuard.verify_and_load(model_file)
            self.assertEqual(loaded["name"], "test_classifier")

            # 2. Tamper with model artifact (inject bit-flip attack)
            with open(model_file, "r+b") as f:
                f.seek(5)
                f.write(b"\xff\xff")

            # 3. Security guard must intercept and block tampered model
            with self.assertRaises(SecurityBreachError):
                ModelSecurityGuard.verify_and_load(model_file)

    def test_07_signed_approval_token_verification(self):
        queue = HumanInTheLoopApprovalQueue(hourly_blast_radius_limit=10)
        proposal = ProposedRemediation(
            proposal_id="prop_sec_007",
            case_id="case_777",
            user_id="user_777",
            system_id="auth_service",
            resource_id="user_777_tok",
            operation="DELETE_RECORD",
            target_state="ABSENT",
            evidence_id="ev_07",
            risk_level=RemediationRisk.HIGH,
            legal_basis="GDPR Art 17(1)",
        )
        queue.submit_proposal(proposal)

        # 1. Generate valid DPO token
        token = SignedApprovalToken.generate_token("prop_sec_007", "DPO", "Compliance_Officer_Alice")
        valid, role, approver = SignedApprovalToken.verify_token(token, "prop_sec_007")
        self.assertTrue(valid)
        self.assertEqual(role, "DPO")
        self.assertEqual(approver, "Compliance_Officer_Alice")

        # 2. Approve via cryptographic token
        approved = queue.approve_with_token(token, "prop_sec_007")
        self.assertTrue(approved)
        self.assertTrue(proposal.is_approved)
        self.assertEqual(proposal.approved_by, "Compliance_Officer_Alice (DPO [TOKEN-VERIFIED])")

        # 3. Forged token rejected
        forged_token = token[:-4] + "dead"
        with self.assertRaises(PermissionError):
            queue.approve_with_token(forged_token, "prop_sec_007")

    def test_08_queue_durable_persistence_across_restarts(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            persist_file = os.path.join(tmpdir, "approval_queue_state.json")
            q1 = HumanInTheLoopApprovalQueue(hourly_blast_radius_limit=15, persistence_path=persist_file)

            prop = ProposedRemediation(
                proposal_id="prop_durable_01",
                case_id="case_dur_01",
                user_id="user_dur",
                system_id="crm_service",
                resource_id="contact_888",
                operation="DELETE_RECORD",
                target_state="ABSENT",
                evidence_id="ev_crm",
                risk_level=RemediationRisk.HIGH,
                legal_basis="CCPA 1798.105",
            )
            q1.submit_proposal(prop)
            self.assertTrue(os.path.exists(persist_file))

            # Simulate complete process crash & restart
            q2 = HumanInTheLoopApprovalQueue(hourly_blast_radius_limit=15, persistence_path=persist_file)
            self.assertIn("prop_durable_01", q2.pending_queue)
            loaded_prop = q2.pending_queue["prop_durable_01"]
            self.assertEqual(loaded_prop.user_id, "user_dur")
            self.assertEqual(loaded_prop.risk_level, RemediationRisk.HIGH)

    def test_09_salted_sha256_rainbow_table_defense(self):
        from code.engine.identity_graph import salted_sha256
        import hashlib

        email = "victim.executive@example.com"
        unsalted_sha256 = hashlib.sha256(email.encode("utf-8")).hexdigest()

        pepper_a = "Enterprise_Salt_A"
        pepper_b = "Enterprise_Salt_B"

        salted_a = salted_sha256(email, pepper=pepper_a)
        salted_b = salted_sha256(email, pepper=pepper_b)

        # 1. Output must be a valid 64-character SHA256 hex string
        self.assertEqual(len(salted_a), 64)
        self.assertEqual(len(salted_b), 64)

        # 2. Salted output must NEVER match raw unsalted rainbow-table hash
        self.assertNotEqual(salted_a, unsalted_sha256)
        self.assertNotEqual(salted_b, unsalted_sha256)

        # 3. Different peppers produce distinct digests
        self.assertNotEqual(salted_a, salted_b)

if __name__ == "__main__":
    unittest.main()

