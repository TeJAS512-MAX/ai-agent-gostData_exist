"""
================================================================================
  Project CHIMERA-X: Automated Unit Test Suite
  Verification of the 7 Advanced Formal Methods Modules
================================================================================
"""

import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "code"))

try:
    from code.engine.chimerax_engine import (
        SMTPolicySatisfiabilitySolver,
        TemporalLTLModelChecker,
        TraceState,
        KnowledgeGraphLinkPredictor,
        StackelbergGameSolver,
        SelfStabilizingProtocol,
        DifferentialPrivacyAccountant,
        CEGISRemediationSynthesizer
    )
except ImportError:
    from engine.chimerax_engine import (
        SMTPolicySatisfiabilitySolver,
        TemporalLTLModelChecker,
        TraceState,
        KnowledgeGraphLinkPredictor,
        StackelbergGameSolver,
        SelfStabilizingProtocol,
        DifferentialPrivacyAccountant,
        CEGISRemediationSynthesizer
    )

class TestProjectChimeraXEngine(unittest.TestCase):

    def test_module1_smt_policy_solver(self):
        solver = SMTPolicySatisfiabilitySolver()
        solver.add_constraint("c1", "acc_01", "DELETE", satisfied=True, explanation="Account row absent")
        solver.add_constraint("c2", "analytics_02", "DELETE", satisfied=False, explanation="Analytics row still present")

        status, unsat_core = solver.solve()
        self.assertEqual(status, "UNSAT")
        self.assertEqual(len(unsat_core), 1)
        self.assertEqual(unsat_core[0].resource_id, "analytics_02")

    def test_module2_ltl_model_checker(self):
        checker = TemporalLTLModelChecker()
        trace = [
            TraceState("2026-03-01T01:00:00", "account_service", is_deleted=True, exists_after=False, sync_active=False),
            TraceState("2026-03-01T04:00:00", "analytics_export", is_deleted=False, exists_after=True, sync_active=True),
        ]
        holds, counterexample = checker.check_safety(trace)
        self.assertFalse(holds)
        self.assertIn("Lasso counterexample", counterexample)

    def test_module3_knowledge_graph_link_predictor(self):
        predictor = KnowledgeGraphLinkPredictor()
        predictor.set_system_embedding("account_service", [0.1, 0.2, 0.3, 0.4])
        # Position analytics_export near account_service + SYNCS_TO
        predictor.set_system_embedding("analytics_export", [0.6, 0.0, 0.4, 1.2])

        score = predictor.score_triple("account_service", "SYNCS_TO", "analytics_export")
        self.assertGreater(score, 0.70)

    def test_module4_stackelberg_game_solver(self):
        solver = StackelbergGameSolver()
        resources = ["acc_01", "analytics_02", "logs_03"]
        probs = {"acc_01": 0.9, "analytics_02": 0.8, "logs_03": 0.3}
        costs = {"acc_01": 2.0, "analytics_02": 1.0, "logs_03": 1.0}

        allocation = solver.allocate_budget(resources, probs, costs, budget=2.0)
        # analytics_02 has ratio 0.8/1.0 = 0.8, logs_03 has 0.3/1.0 = 0.3, acc_01 has 0.9/2.0 = 0.45
        self.assertTrue(allocation["analytics_02"])

    def test_module5_self_stabilizing_protocol(self):
        protocol = SelfStabilizingProtocol()
        adj = {"acc_01": [], "analytics_02": ["acc_01"]}
        initial = {"acc_01": "LEGIT", "analytics_02": "CORRUPT"}

        converged, rounds, _ = protocol.simulate_stabilization(adj, initial)
        self.assertTrue(converged)
        self.assertEqual(rounds, 1)

    def test_module6_differential_privacy_accountant(self):
        dp = DifferentialPrivacyAccountant()
        # High distinguishability cohort frequencies (e.g. 100 vs 1)
        eps_high = dp.estimate_epsilon([100, 1])
        self.assertFalse(dp.is_anonymized(eps_high, threshold=1.5))

        # Low distinguishability cohort frequencies (e.g. 50 vs 48)
        eps_low = dp.estimate_epsilon([50, 48])
        self.assertTrue(dp.is_anonymized(eps_low, threshold=1.5))

    def test_module7_cegis_remediation_synthesizer(self):
        cegis = CEGISRemediationSynthesizer()
        violations = ["analytics_rec_01"]
        flow_deps = {"analytics_rec_01": "sync_job_7"}

        plan = cegis.synthesize_plan(violations, flow_deps)
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0].operation, "DISABLE_DATA_FLOW")
        self.assertEqual(plan[0].target, "sync_job_7")
        self.assertEqual(plan[1].operation, "DELETE_RECORD")
        self.assertEqual(plan[1].target, "analytics_rec_01")

if __name__ == "__main__":
    unittest.main()
