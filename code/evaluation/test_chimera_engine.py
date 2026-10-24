"""
================================================================================
  Project CHIMERA: Automated Unit Test Suite
  Verification of Formal Taint Fixpoint, Model Checker & Step Type System
================================================================================
"""

import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "code"))

try:
    from code.engine.chimera_engine import (
        LineageNode,
        LineageEdge,
        RuleSpec,
        TaintFixpointAnalyzer,
        CompletenessModelChecker,
        RemediationIROptimizer,
        StepGrammarTypeChecker,
        ImmuneMemoryAutomaton,
        ImmuneAntibody,
        Countermodel
    )
except ImportError:
    from engine.chimera_engine import (
        LineageNode,
        LineageEdge,
        RuleSpec,
        TaintFixpointAnalyzer,
        CompletenessModelChecker,
        RemediationIROptimizer,
        StepGrammarTypeChecker,
        ImmuneMemoryAutomaton,
        ImmuneAntibody,
        Countermodel
    )

class TestProjectChimeraEngine(unittest.TestCase):

    def setUp(self):
        self.rules = {
            "account": RuleSpec(retain=True, permitted_identifiers={"user_001"}, prohibited_fields={"email", "name"}),
            "analytics": RuleSpec(retain=False, permitted_identifiers=set(), prohibited_fields={"email", "name", "phone"}),
            "support": RuleSpec(retain=False, permitted_identifiers=set(), prohibited_fields={"email", "name", "phone"}),
        }

    def test_taint_fixpoint_propagation(self):
        analyzer = TaintFixpointAnalyzer(self.rules)
        source = LineageNode("account_service", "acc_1", "account")
        target = LineageNode("analytics_export", "rec_2", "analytics")
        edge = LineageEdge(source, target, "SYNC", "ev_01")

        nodes = [source, target]
        edges = [edge]
        taint_table = analyzer.compute_fixpoint(nodes, edges, source, {"user_001", "email@test.com"})

        self.assertIn("email@test.com", taint_table[target])
        self.assertIn("user_001", taint_table[target])

    def test_completeness_model_checker_incomplete(self):
        analyzer = TaintFixpointAnalyzer(self.rules)
        source = LineageNode("account_service", "acc_1", "account", is_sink=False)
        target = LineageNode("analytics_export", "rec_2", "analytics", is_sink=True)
        edge = LineageEdge(source, target, "SYNC", "ev_01")

        nodes = [source, target]
        edges = [edge]
        taint_table = analyzer.compute_fixpoint(nodes, edges, source, {"email@test.com"})

        checker = CompletenessModelChecker(self.rules)
        verdict, cert, countermodels = checker.evaluate_completeness(taint_table, {"email@test.com"}, edges)

        self.assertEqual(verdict, "INCOMPLETE")
        self.assertIsNone(cert)
        self.assertEqual(len(countermodels), 1)
        self.assertEqual(countermodels[0].node.system_id, "analytics_export")

    def test_completeness_model_checker_complete(self):
        analyzer = TaintFixpointAnalyzer(self.rules)
        source = LineageNode("account_service", "acc_1", "account")
        target = LineageNode("analytics_export", "rec_2", "analytics")
        edge = LineageEdge(source, target, "DELETE", "ev_02")

        nodes = [source, target]
        edges = [edge]
        taint_table = analyzer.compute_fixpoint(nodes, edges, source, {"email@test.com"})
        taint_table[source] = {"user_001"}  # Permitted identifier

        checker = CompletenessModelChecker(self.rules)
        verdict, cert, countermodels = checker.evaluate_completeness(taint_table, {"user_001"}, edges)

        self.assertEqual(verdict, "COMPLETE")
        self.assertIsNotNone(cert)
        self.assertEqual(len(countermodels), 0)

    def test_remediation_ir_optimizer_cse(self):
        optimizer = RemediationIROptimizer()
        n1 = LineageNode("analytics_export", "rec_1", "analytics")
        n2 = LineageNode("analytics_export", "rec_2", "analytics")

        c1 = Countermodel(node=n1, residual_taint={"email"}, witness_path=["acc_1 --[SYNC]--> rec_1"], evidence_id="ev_1")
        c2 = Countermodel(node=n2, residual_taint={"email"}, witness_path=["acc_1 --[SYNC]--> rec_2"], evidence_id="ev_2")

        actions = optimizer.optimize([c1, c2])
        self.assertTrue(len(actions) >= 2)
        self.assertEqual(actions[0].action_type, "DISABLE_DATA_FLOW")
        self.assertEqual(actions[0].dependency_rank, 1)

    def test_step_grammar_typechecker(self):
        step_valid = {
            "step_no": 1,
            "phase": "FINDING",
            "system_id": "account_service",
            "resource_id": "acc_01",
            "operation": "REPORT_REMAINING_RECORD",
            "state": "PRESENT",
            "evidence_id": "ev_sql_01"
        }
        errs = StepGrammarTypeChecker.validate_step(step_valid, is_complete_case=False)
        self.assertEqual(len(errs), 0)

        step_invalid_state = dict(step_valid, state="ABSENT")
        errs_invalid = StepGrammarTypeChecker.validate_step(step_invalid_state, is_complete_case=False)
        self.assertGreater(len(errs_invalid), 0)

    def test_immune_memory_automaton(self):
        automaton = ImmuneMemoryAutomaton()
        ab = ImmuneAntibody(
            antibody_id="ab_001",
            pattern="account_service:acc_005",
            system_id="account_service",
            finding_operation="REPORT_REMAINING_RECORD",
            origin_case_id="case_001"
        )
        automaton.add_antibody(ab)

        matches = automaton.scan_evidence("Scanning logs for account_service:acc_005 un-redacted remnant")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].antibody_id, "ab_001")

if __name__ == "__main__":
    unittest.main()
