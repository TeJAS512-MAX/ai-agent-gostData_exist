"""
================================================================================
 Project Oblivion: Automated Unit Test Suite
 Verification of the 7 Advanced Non-Existence Mechanisms
================================================================================
"""

import unittest
import os
import sys
import pandas as pd
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "code"))

from code.engine.oblivion_engine import (
    DarkMatterEstimator,
    ResurrectionRedTeam,
    MerkleOblivionCertificate,
    ByzantineJury,
    JurorPersona,
    BehavioralReenactmentProber,
    PolicyGapMiner,
    EpidemiologicalContactGraph,
)
from code.engine.advanced_agent import AdvancedAuditAgent


class TestProjectOblivionFramework(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dataset_dir = os.path.join(REPO_ROOT, "dataset")
        cls.agent = AdvancedAuditAgent(dataset_dir=cls.dataset_dir)
        cls.sr_df = pd.read_csv(os.path.join(cls.dataset_dir, "sample_deletion_requests.csv"))

    def test_01_dark_matter_estimator(self):
        """Test Bayesian ghost probability decay with active barriers."""
        estimator = DarkMatterEstimator()
        # Case without barriers
        p_raw, _, darks = estimator.estimate_ghost_probability(
            observed_systems={"account_service"},
            unresolved_findings_count=1,
            active_data_flows_disabled=False,
            backup_restores_blocked=False,
            inferred_dark_systems={"account_replication_cluster", "backup_service"},
        )
        self.assertGreater(p_raw, 0.85, "High ghost probability when unresolved findings exist")

        # Clean case with active barriers
        p_clean, _, _ = estimator.estimate_ghost_probability(
            observed_systems={"account_service"},
            unresolved_findings_count=0,
            active_data_flows_disabled=True,
            backup_restores_blocked=True,
            inferred_dark_systems={"account_replication_cluster", "backup_service"},
        )
        self.assertLess(p_clean, 0.05, "Ghost probability should decay below 5% when barriers are active")

    def test_02_resurrection_red_team_adversarial_attack(self):
        """Test that Red Team catches unblocked CDC streams and unblocked restores."""
        red_team = ResurrectionRedTeam()

        # Vulnerable plan (unblocked CDC stream)
        vulnerable_steps = [
            {"phase": "FINDING", "operation": "REPORT_ACTIVE_DATA_FLOW", "system_id": "integration_service", "resource_id": "stream_1"},
            {"phase": "REMEDIATION", "operation": "DELETE_RECORD", "system_id": "account_service", "resource_id": "account_1"},
        ]
        exploited, vectors = red_team.attack(raw_status="INCOMPLETE", steps=vulnerable_steps)
        self.assertTrue(exploited, "Red Team must exploit unblocked active data flow")
        self.assertTrue(any(v.vector_id == "ATK-01-CDC-REPLAY" for v in vectors))

        # Hardened plan (barrier precedes deletion)
        hardened_steps = [
            {"phase": "FINDING", "operation": "REPORT_ACTIVE_DATA_FLOW", "system_id": "integration_service", "resource_id": "stream_1"},
            {"phase": "REMEDIATION", "operation": "DISABLE_DATA_FLOW", "system_id": "integration_service", "resource_id": "stream_1"},
            {"phase": "REMEDIATION", "operation": "DELETE_RECORD", "system_id": "account_service", "resource_id": "account_1"},
            {"phase": "VERIFICATION", "operation": "VERIFY_DATA_FLOW_DISABLED", "system_id": "integration_service", "resource_id": "stream_1"},
            {"phase": "VERIFICATION", "operation": "VERIFY_RECORD_ABSENT", "system_id": "account_service", "resource_id": "account_1"},
        ]
        exploited_hardened, vectors_hardened = red_team.attack(raw_status="INCOMPLETE", steps=hardened_steps)
        self.assertFalse(exploited_hardened, "Hardened plan must neutralize all Red Team vectors")

    def test_03_zero_knowledge_merkle_certificate(self):
        """Test cryptographic Merkle tree commitment generation."""
        zk_cert = MerkleOblivionCertificate.generate(
            case_id="case_01",
            email="user@example.com",
            status="COMPLETE",
            steps=[{"step_no": 1, "phase": "VERIFICATION", "system_id": "account_service", "resource_id": "account_01", "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": "evidence_54"}],
            evidence_citations=["evidence_54"],
        )
        self.assertIn("merkle_root", zk_cert)
        self.assertEqual(len(zk_cert["merkle_root"]), 64, "Merkle root must be a valid 256-bit hex hash")
        self.assertEqual(zk_cert["algorithm"], "SHA256-Merkle-Tree-v1")
        self.assertNotIn("user@example.com", str(zk_cert), "Raw PII must never be exposed in ZK certificate")

    def test_04_byzantine_jury_quorum(self):
        """Test PBFT consensus across Skeptical Regulator, Cost Engineer, and Literal Auditor."""
        jury = ByzantineJury()
        verdict = jury.deliberate(
            case_id="case_01",
            reported_status="COMPLETE",
            derived_status="COMPLETE",
            findings_count=0,
            steps=[{"phase": "VERIFICATION", "operation": "VERIFY_RECORD_ABSENT", "evidence_id": "evidence_54"}],
            citations=["evidence_54"],
        )
        self.assertTrue(verdict.quorum_achieved, "PBFT quorum must be achieved")
        self.assertEqual(verdict.consensus_verdict, "COMPLETE")
        self.assertEqual(len(verdict.votes), 3, "Jury must have exactly 3 juror votes")

    def test_05_behavioral_reenactment_probing(self):
        """Test live behavioral re-registration and search probes."""
        prober = BehavioralReenactmentProber()
        probes = prober.probe(
            email="test.deleted@example.com",
            status="COMPLETE",
            steps=[{"operation": "VERIFY_RECORD_ABSENT"}],
        )
        self.assertGreaterEqual(len(probes), 2, "Must execute both re-signup and search index probes")
        self.assertTrue(all(p.interception_verified for p in probes), "All probes must confirm non-existence")

    def test_06_policy_gap_miner(self):
        """Test automated detection of uncatalogued data categories."""
        miner = PolicyGapMiner()
        proposals = miner.audit_policy(
            extracted_categories={"USER_PROFILE", "EMBEDDING_LATENT_CACHE", "UNKNOWN_LEGACY_QUEUE"},
            sample_contexts={"EMBEDDING_LATENT_CACHE": "Latent vector embeddings found in vector DB"}
        )
        self.assertEqual(len(proposals), 2, "Must detect 2 uncatalogued categories")
        self.assertTrue(any("EMBEDDING" in p.discovered_category for p in proposals))

    def test_07_epidemiological_contact_tracing(self):
        """Test data diffusion modeling across microservices."""
        graph = EpidemiologicalContactGraph(
            activity_csv_path=os.path.join(self.dataset_dir, "system_activity.csv")
        )
        infection_map = graph.trace_infection_spread(initial_infected_systems={"account_service"})
        self.assertIn("search_service", infection_map, "Search service must be infected via account_service syncs")
        self.assertGreater(infection_map["search_service"], 0.20)

    def test_08_end_to_end_audit_case_oblivion(self):
        """Test the master audit_case_oblivion method on golden case_01."""
        row = self.sr_df.iloc[0]
        res = self.agent.audit_case_oblivion(row, all_cases_df=self.sr_df)
        self.assertEqual(res.status, "COMPLETE")
        self.assertTrue(res.byzantine_quorum_achieved)
        self.assertTrue(res.resurrection_red_team_passed)
        self.assertTrue(res.behavioral_probes_verified)
        self.assertGreater(len(res.merkle_root), 0)
        self.assertLess(res.execution_time_ms, 250.0, "Execution latency must satisfy sub-250ms SLA")


if __name__ == "__main__":
    unittest.main()
