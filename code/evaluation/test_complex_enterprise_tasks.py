"""
================================================================================
 Unit Tests: Complex Enterprise Task Orchestrator (Aggressive Mode)
================================================================================
Verifies that the AI deletion audit agent autonomously solves:
  1. 3-Hop circular replication sync & restore resurrection loops
  2. Multi-jurisdiction GDPR vs statutory tax retention conflicts
  3. Multimodal deep identity obfuscation across PDF & SQLite
  4. Split-brain eventual consistency queue lag
  5. Adversarial prompt injections and DSAR disentanglement
"""

import unittest
import os
import sys

# Ensure repository root and code directory are in sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
CODE_DIR = os.path.join(ROOT, "code")
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

try:
    from code.engine.complex_task_orchestrator import ComplexEnterpriseTaskOrchestrator
except ImportError:
    from engine.complex_task_orchestrator import ComplexEnterpriseTaskOrchestrator


class TestComplexEnterpriseTasks(unittest.TestCase):
    """Test suite for high-complexity enterprise privacy scenarios."""

    @classmethod
    def setUpClass(cls):
        cls.orchestrator = ComplexEnterpriseTaskOrchestrator()

    def test_resurrection_loop_resolution(self):
        """Scenario 1: Break 3-hop CDC replication & backup restore cycle."""
        res = self.orchestrator.solve_resurrection_loop_3_hop()
        self.assertEqual(res.deletion_status, "INCOMPLETE")
        self.assertTrue(res.causal_invariance_proven)
        self.assertEqual(res.resurrection_risk_post_remediation, 0.0)
        self.assertGreater(len(res.ordered_steps), 0)

        # Verify precedence: DISABLE_DATA_FLOW and BLOCK_RESTORE must precede DELETE_RECORD
        op_seq = [s["operation"] for s in res.ordered_steps]
        if "DISABLE_DATA_FLOW" in op_seq and "DELETE_RECORD" in op_seq:
            self.assertLess(op_seq.index("DISABLE_DATA_FLOW"), op_seq.index("DELETE_RECORD"))
        if "BLOCK_RESTORE" in op_seq and "DELETE_RECORD" in op_seq:
            self.assertLess(op_seq.index("BLOCK_RESTORE"), op_seq.index("DELETE_RECORD"))

    def test_regulatory_conflict_resolution(self):
        """Scenario 2: Preserve statutory tax records while redacting PII."""
        res = self.orchestrator.solve_cross_jurisdiction_regulatory_conflict()
        self.assertEqual(res.deletion_status, "INCOMPLETE")
        self.assertTrue(res.causal_invariance_proven)

        # Confirm presence of statutory check
        has_present = any(
            s.get("operation") == "VERIFY_RECORD_PRESENT" and s.get("system_id") == "tax_compliance_store"
            for s in res.ordered_steps
        )
        self.assertTrue(has_present, "Must verify presence of tax records")

        # Confirm redaction of account tombstone
        has_redact = any(
            s.get("operation") == "REDACT_RECORD" and s.get("system_id") == "account_service"
            for s in res.ordered_steps
        )
        self.assertTrue(has_redact, "Must redact account tombstone")

    def test_multimodal_identity_obfuscation(self):
        """Scenario 3: Multi-target alias resolution across PDF and SQLite."""
        res = self.orchestrator.solve_multimodal_identity_obfuscation()
        self.assertEqual(res.deletion_status, "INCOMPLETE")
        self.assertTrue(res.causal_invariance_proven)
        self.assertEqual(len(res.ordered_steps), 9)

    def test_split_brain_consistency_lag(self):
        """Scenario 4: Halt asynchronous cross-region queue replay."""
        res = self.orchestrator.solve_split_brain_consistency_lag()
        self.assertEqual(res.deletion_status, "INCOMPLETE")
        self.assertTrue(res.causal_invariance_proven)

        # Verify queue was disabled
        has_disable = any(
            s.get("operation") == "DISABLE_DATA_FLOW" and s.get("system_id") == "cross_region_sqs_queue"
            for s in res.ordered_steps
        )
        self.assertTrue(has_disable, "Must disable asynchronous cross-region queue")

    def test_adversarial_prompt_injection(self):
        """Scenario 5: Detect adversarial prompt injection and reject account destruction."""
        res = self.orchestrator.solve_adversarial_prompt_injection()
        self.assertEqual(res.deletion_status, "NOT_APPLICABLE")
        self.assertEqual(len(res.ordered_steps), 0)
        self.assertEqual(res.resurrection_risk_post_remediation, 0.0)


if __name__ == "__main__":
    unittest.main()

