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


if __name__ == "__main__":
    unittest.main()
