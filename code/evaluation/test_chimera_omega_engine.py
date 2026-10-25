"""
================================================================================
  Project CHIMERA-Ω: Automated Unit Test Suite
  Verification of Concurrency, Automata Learning, POMDP, MPC, TDA & Categories
================================================================================
"""

import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "code"))

try:
    from code.engine.chimera_omega_engine import (
        PetriNetConcurrencyModel,
        SandboxOracle,
        AngluinLStarLearner,
        POMDPBeliefState,
        POMDPEvidencePolicy,
        SecureMultipartyAuditProtocol,
        TopologicalCoverageAnalyzer,
        VerifiedMorphism,
        FunctorialLineageAuditor
    )
except ImportError:
    from engine.chimera_omega_engine import (
        PetriNetConcurrencyModel,
        SandboxOracle,
        AngluinLStarLearner,
        POMDPBeliefState,
        POMDPEvidencePolicy,
        SecureMultipartyAuditProtocol,
        TopologicalCoverageAnalyzer,
        VerifiedMorphism,
        FunctorialLineageAuditor
    )

class TestProjectChimeraOmegaEngine(unittest.TestCase):

    def test_module1_petri_net_race_detection(self):
        net = PetriNetConcurrencyModel()
        # Transitions
        net.add_transition("start_delete", {"tainted": 1}, {"deleting": 1})
        net.add_transition("finish_delete", {"deleting": 1}, {"deleted": 1})
        net.add_transition("concurrent_sync", {"deleting": 1}, {"deleting": 1, "tainted": 1})

        initial = {"tainted": 1, "deleted": 0, "deleting": 0}
        races = net.find_reachable_races(initial)
        self.assertTrue(len(races) > 0)
        # Verify race marking has both deleted and tainted
        marking = races[0][2]
        self.assertTrue(net.is_unsafe(marking))

    def test_module2_angluin_lstar_dfa_learning(self):
        oracle = SandboxOracle()
        learner = AngluinLStarLearner(alphabet=["DELETE", "SYNC", "SIGNUP", "RESTORE"])
        dfa = learner.learn_minimal_dfa(oracle)

        # Discovered transition: SYNC on S2_SOFT_DELETED transitions back to S1_TAINTED
        self.assertEqual(dfa["S2_SOFT_DELETED"]["SYNC"], "S1_TAINTED")
        self.assertEqual(dfa["S1_TAINTED"]["DELETE"], "S2_SOFT_DELETED")

    def test_module3_pomdp_evoi_policy(self):
        policy = POMDPEvidencePolicy(cost_table={"sql_scan": 0.5, "deep_ocr": 5.0})
        # Uncertain belief: 50/50
        belief = POMDPBeliefState(p_complete=0.5, p_incomplete=0.5)

        # Available actions with expected clarity
        actions = [("sql_scan", 0.7), ("deep_ocr", 0.8)]
        best = policy.select_best_action(belief, actions)
        # Cheap sql_scan should have higher EVOI than expensive deep_ocr
        self.assertEqual(best, "sql_scan")

    def test_module4_mpc_psi_audit(self):
        mpc = SecureMultipartyAuditProtocol()
        system_records = ["user_100@northstar.internal", "user_200@northstar.internal"]
        target_pii = ["user_200@northstar.internal"]

        res = mpc.audit_via_private_set_intersection(system_records, target_pii)
        self.assertTrue(res["contains_match"])
        self.assertEqual(res["match_count"], 1)
        self.assertTrue(res["zero_pii_exposed"])

    def test_module5_topological_coverage_holes(self):
        tda = TopologicalCoverageAnalyzer()
        # Source 1 covers ORDERS and PAYMENTS
        tda.add_evidence_source(["ORDERS", "PAYMENTS"])
        # Source 2 covers PAYMENTS and SHIPPING
        tda.add_evidence_source(["PAYMENTS", "SHIPPING"])
        # ORDERS and SHIPPING never co-evidenced -> H1 hole
        holes = tda.detect_h1_coverage_holes([("ORDERS", "PAYMENTS", "SHIPPING")])
        self.assertEqual(len(holes), 1)
        self.assertEqual(holes[0].dimension, 1)

    def test_module6_functorial_category_composition(self):
        auditor = FunctorialLineageAuditor()
        # f: TAINTED -> CLEAN (Account Service deletion)
        f = VerifiedMorphism("TAINTED", "CLEAN", "account_service", "proof_f")
        # g: CLEAN -> CLEAN (Analytics Sync pass-through)
        g = VerifiedMorphism("CLEAN", "CLEAN", "analytics_sync", "proof_g")

        composite = auditor.verify_composite_pipeline(f, g)
        self.assertEqual(composite.source_state, "TAINTED")
        self.assertEqual(composite.target_state, "CLEAN")
        self.assertIn("account_service∘analytics_sync", composite.system_id)

if __name__ == "__main__":
    unittest.main()
