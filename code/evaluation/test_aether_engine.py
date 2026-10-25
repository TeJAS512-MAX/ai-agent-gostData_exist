"""
================================================================================
  Project AETHER: Automated Unit Test Suite
  Verification of the 8 Deep Algorithmic Erasure Mechanisms
================================================================================
"""

import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "code"))

try:
    from code.engine.aether_engine import (
        CausalErasureSurgery,
        AntimatterRecordLinkage,
        AntimatterTwin,
        HeatDeathEntropyEngine,
        HolographicBoundaryProof,
        TemporalBranchCollapser
    )
except ImportError:
    from engine.aether_engine import (
        CausalErasureSurgery,
        AntimatterRecordLinkage,
        AntimatterTwin,
        HeatDeathEntropyEngine,
        HolographicBoundaryProof,
        TemporalBranchCollapser
    )

class TestProjectAetherEngine(unittest.TestCase):

    def test_causal_erasure_surgery(self):
        surgery = CausalErasureSurgery()
        surgery.add_node("account_service", "account_005", "ABSENT")
        surgery.add_node("analytics_export", "record_221", "PRESENT")
        surgery.add_edge("account_service.account_005", "analytics_export.record_221", "SYNC")

        divergences = surgery.evaluate_erasure_surgery("account_service.account_005")
        self.assertEqual(len(divergences), 1)
        self.assertEqual(divergences[0].system_id, "analytics_export")
        self.assertEqual(divergences[0].remediation_required, "DISABLE_DATA_FLOW")

    def test_antimatter_record_linkage(self):
        twin = AntimatterTwin(
            email_exact="ghost@northstar.internal",
            email_hash="sha256_deadbeef",
            phone_e164="+15550199",
            name_tokens=["John", "Doe"],
            device_fingerprints=["dev_fp_992"]
        )
        linkage = AntimatterRecordLinkage(tau_threshold=4.0)

        # Partial match test (hash match)
        event = linkage.sweep_resource(
            system_id="search_index",
            resource_id="doc_8842",
            fields={"email_hash": "sha256_deadbeef"},
            twin=twin
        )
        self.assertTrue(event.is_annihilated)
        self.assertIn("email_hash", event.matched_features)

    def test_heat_death_entropy(self):
        engine = HeatDeathEntropyEngine(population_size=50_000)
        # Cohort of 1 -> unique re-identification, H = 0
        h_leak = engine.compute_conditional_entropy({}, cohort_size=1)
        self.assertEqual(h_leak, 0.0)
        self.assertFalse(engine.is_heat_death_achieved(h_leak))

        # Cohort of 128 -> H = 7.0 bits
        h_safe = engine.compute_conditional_entropy({}, cohort_size=128)
        self.assertEqual(h_safe, 7.0)
        self.assertTrue(engine.is_heat_death_achieved(h_safe))

    def test_holographic_boundary_proof(self):
        proof = HolographicBoundaryProof()
        # Source to intermediate CDC stream
        proof.add_flow_edge("account_service", "cdc_stream", 10.0)
        # CDC stream to warehouse sink
        proof.add_flow_edge("cdc_stream", "data_warehouse", 10.0)

        cuts = proof.compute_min_cut_edges("account_service", "data_warehouse")
        self.assertEqual(len(cuts), 1)
        self.assertEqual(cuts[0][0], "account_service")
        self.assertEqual(cuts[0][1], "cdc_stream")

    def test_temporal_branch_collapser(self):
        collapser = TemporalBranchCollapser(num_particles=200)
        events = [
            {"op": "SYNC", "ts": "2026-03-01T03:00:00"},
            {"op": "DELETE", "ts": "2026-03-01T03:00:00"}
        ]
        posterior = collapser.collapse_branches(events)
        self.assertIn("ABSENT", posterior)
        self.assertIn("GHOST_RECREATED", posterior)
        self.assertAlmostEqual(sum(posterior.values()), 1.0, places=2)

if __name__ == "__main__":
    unittest.main()

