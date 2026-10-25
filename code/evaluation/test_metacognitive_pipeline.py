#!/usr/bin/env python3
"""
Unit tests for next-generation Meta-Cognitive Architecture (AOT).
"""

import sys
import unittest
from pathlib import Path

# Setup paths
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "code"))

try:
    from code.engine.metacognitive_pipeline import (
        MetaCognitiveGovernor,
        CognitiveMode,
        CounterfactualCausalSimulator,
        MCTSRemediationScheduler,
    )
except ImportError:
    from engine.metacognitive_pipeline import (
        MetaCognitiveGovernor,
        CognitiveMode,
        CounterfactualCausalSimulator,
        MCTSRemediationScheduler,
    )


class MockIdentity:
    def __init__(self, user_id="user_99", emails=None):
        self.user_id = user_id
        self.emails = emails or ["test@example.com"]


class TestMetaCognitivePipeline(unittest.TestCase):

    def setUp(self):
        self.governor = MetaCognitiveGovernor()
        self.simulator = CounterfactualCausalSimulator()
        self.scheduler = MCTSRemediationScheduler()

    def test_epistemic_governor_high_certainty_reflex(self):
        """High-probability intent and complete graph triggers SYSTEM_1_REFLEX."""
        identity = MockIdentity()
        state = self.governor.evaluate_epistemic_state(
            request_text="Please delete my account and personal data.",
            intent_prob=0.999,
            identity_profile=identity,
            unresolved_events_count=0,
            statutory_hold_active=False
        )
        self.assertEqual(state.selected_mode, CognitiveMode.SYSTEM_1_REFLEX)
        self.assertGreaterEqual(state.overall_confidence, 0.92)
        self.assertLess(state.shannon_entropy, 0.05)

    def test_epistemic_governor_statutory_hold_deliberation(self):
        """Active statutory hold triggers SYSTEM_2_DELIBERATION."""
        identity = MockIdentity()
        state = self.governor.evaluate_epistemic_state(
            request_text="Delete my data under GDPR.",
            intent_prob=0.98,
            identity_profile=identity,
            unresolved_events_count=0,
            statutory_hold_active=True
        )
        self.assertEqual(state.selected_mode, CognitiveMode.SYSTEM_2_DELIBERATION)
        self.assertIn("MCTS", state.rationale)

    def test_epistemic_governor_high_ambiguity_probe(self):
        """Ambiguous intent and missing identity triggers SYSTEM_3_ACTIVE_PROBE."""
        state = self.governor.evaluate_epistemic_state(
            request_text="Can you review my profile status?",
            intent_prob=0.52,  # Maximum Shannon entropy near p=0.5
            identity_profile=None,
            unresolved_events_count=3,
            statutory_hold_active=False
        )
        self.assertEqual(state.selected_mode, CognitiveMode.SYSTEM_3_ACTIVE_PROBE)
        self.assertGreater(state.shannon_entropy, 0.95)

    def test_causal_simulator_detects_tombstone_leak(self):
        """Counterfactual simulator flags direct PII lingering in tombstones."""
        steps = [
            {"phase": "REMEDIATION", "operation": "REDACT_RECORD", "resource_id": "account_tombstone", "system_id": "auth"}
        ]
        leaking_fields = {"user_id", "email", "phone"}
        result = self.simulator.simulate_remediation_plan(
            steps=steps,
            tombstone_fields=leaking_fields
        )
        self.assertFalse(result.is_provably_safe)
        self.assertIn("email", result.unredacted_tombstone_pii)
        self.assertIn("phone", result.unredacted_tombstone_pii)

    def test_causal_simulator_safe_plan(self):
        """Compliant plan with no leaks passes formal verification."""
        steps = [
            {"phase": "REMEDIATION", "operation": "DISABLE_DATA_FLOW", "resource_id": "sync_job_01", "system_id": "etl"},
            {"phase": "REMEDIATION", "operation": "DELETE_RECORD", "resource_id": "profile_01", "system_id": "account"}
        ]
        result = self.simulator.simulate_remediation_plan(
            steps=steps,
            tombstone_fields={"user_id"},  # only internal user_id, no direct PII
            active_flows={"sync_job_01"}
        )
        self.assertTrue(result.is_provably_safe)
        self.assertEqual(result.resurrection_risk_score, 0.0)

    def test_scheduler_canonical_ordering_and_monotonicity(self):
        """MCTS scheduler strictly enforces phase, operator priority, and 1-indexing."""
        raw = [
            {"phase": "VERIFICATION", "operation": "VERIFY_RECORD_ABSENT", "system_id": "sys_b", "resource_id": "res_1"},
            {"phase": "FINDING", "operation": "REPORT_REMAINING_RECORD", "system_id": "sys_a", "resource_id": "res_2"},
            {"phase": "REMEDIATION", "operation": "DELETE_RECORD", "system_id": "sys_a", "resource_id": "res_1"},
        ]
        ordered = self.scheduler.canonical_schedule(raw)
        self.assertEqual(len(ordered), 3)
        self.assertEqual(ordered[0]["step_no"], 1)
        self.assertEqual(ordered[0]["phase"], "FINDING")
        self.assertEqual(ordered[1]["step_no"], 2)
        self.assertEqual(ordered[1]["phase"], "REMEDIATION")
        self.assertEqual(ordered[2]["step_no"], 3)
        self.assertEqual(ordered[2]["phase"], "VERIFICATION")


if __name__ == "__main__":
    unittest.main()

