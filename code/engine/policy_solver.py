"""
Stage 5 & 6: Symbolic SMT Policy Solver + Bijective Remediation Synthesis
==========================================================================
Stage 5 evaluates every observed resource state against deletion_rules.csv.
Stage 6 deterministically maps every FINDING to its required REMEDIATION
and future VERIFICATION steps.

Policy rule → required action mapping:
  DELETE    → REPORT_REMAINING_RECORD   → DELETE_RECORD     → VERIFY_RECORD_ABSENT
  REDACT    → REPORT_EXPOSED_PII        → REDACT_RECORD     → VERIFY_RECORD_PRESENT + VERIFY_RECORD_REDACTED
  ANONYMIZE → REPORT_EXPOSED_PII        → ANONYMIZE_RECORD  → VERIFY_RECORD_ANONYMIZED
  RETAIN    → (no finding)              → (none)            → VERIFY_RECORD_PRESENT
  DISABLE   → REPORT_ACTIVE_DATA_FLOW   → DISABLE_DATA_FLOW → VERIFY_DATA_FLOW_DISABLED
  BLOCK     → REPORT_RESTORE_RISK       → BLOCK_RESTORE     → VERIFY_RESTORE_BLOCKED

Tombstone (rule_15, ACCOUNT_TOMBSTONE, REDACT):
  The record may remain but direct PII must be stripped.
  If PII is still present → REPORT_EXPOSED_PII.
  If PII is absent (state=REDACTED) → VERIFY_RECORD_PRESENT + VERIFY_RECORD_REDACTED.

Security audit log (rule_12, RETAIN):
  Must remain present → always VERIFY_RECORD_PRESENT.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ── Policy constants ──────────────────────────────────────────────────────────

# Maps data_category → required_action (from deletion_rules.csv)
_DEFAULT_RULES: Dict[str, str] = {
    "USER_PROFILE": "DELETE",
    "SECONDARY_IDENTIFIER": "DELETE",
    "SEARCH_INDEX_ENTRY": "DELETE",
    "CACHE_ENTRY": "DELETE",
    "SUPPORT_MESSAGE": "REDACT",
    "SUPPORT_ATTACHMENT": "DELETE",
    "ANALYTICS_PROFILE": "ANONYMIZE",
    "PRODUCT_TELEMETRY": "ANONYMIZE",
    "USER_EXPORT": "DELETE",
    "MARKETING_PROFILE": "DELETE",
    "EMAIL_DELIVERY_LOG": "REDACT",
    "SECURITY_AUDIT_LOG": "RETAIN",
    "LEGAL_HOLD_RECORD": "RETAIN",
    "BACKUP_ARCHIVE": "RETAIN",  # with BLOCK_RESTORE
    "ACCOUNT_TOMBSTONE": "REDACT",
    # Integration/connector: must be DISABLED
    "CONNECTOR": "DELETE",
    "UNKNOWN": "DELETE",
}

# System-to-category defaults
_SYSTEM_CATEGORY_MAP: Dict[str, str] = {
    "account_service": "USER_PROFILE",
    "search_service": "SEARCH_INDEX_ENTRY",
    "analytics_platform": "ANALYTICS_PROFILE",
    "support_platform": "SUPPORT_MESSAGE",
    "security_service": "SECURITY_AUDIT_LOG",
    "backup_service": "BACKUP_ARCHIVE",
    "integration_service": "CONNECTOR",
    "export_service": "USER_EXPORT",
    "identity_service": "ACCOUNT_TOMBSTONE",
    "marketing_service": "MARKETING_PROFILE",
}

# Systems where an ACTIVE observation means data-flow risk
_FLOW_SYSTEMS = {"integration_service"}
# Systems where an ACTIVE observation means restore risk
_RESTORE_SYSTEMS = {"backup_service"}


# ── PolicySolver ──────────────────────────────────────────────────────────────

class PolicySolver:
    """
    Stage 5 + Stage 6: Symbolic policy evaluation and bijective remediation synthesis.

    Usage:
        solver = PolicySolver(dataset_dir="dataset")
        steps = solver.evaluate(observations, footprint, audit_at, primary_ev_id)
        status = "COMPLETE" if solver.is_complete else "INCOMPLETE"
    """

    def __init__(self, dataset_dir: str = "dataset"):
        import os
        rules_path = os.path.join(dataset_dir, "deletion_rules.csv")
        rules_df = pd.read_csv(rules_path)
        self._rules: Dict[str, str] = dict(
            zip(rules_df["data_category"], rules_df["required_action"])
        )
        # Merge defaults for any categories missing from CSV
        for cat, act in _DEFAULT_RULES.items():
            self._rules.setdefault(cat, act)

    # ── Public API ────────────────────────────────────────────────────────────

    def evaluate(
        self,
        observations,                          # List[EvidenceObservation]
        footprint,                             # IdentityFootprint
        audit_at: str,
        primary_ev_id: str,
        target_account_id: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Returns (deletion_status, sorted_steps).
        deletion_status: "COMPLETE" | "INCOMPLETE"
        """
        findings: List[Dict] = []
        remediations: List[Dict] = []
        verifications: List[Dict] = []

        # --- Stage 5: Evaluate each observation ---
        # Deduplicate observations: keep the latest captured_at per (system_id, resource_id)
        latest: Dict[Tuple[str, str], Any] = {}
        for obs in observations:
            key = (obs.system_id, obs.resource_id)
            if key not in latest or obs.captured_at > latest[key].captured_at:
                latest[key] = obs

        processed = set()

        for (sys_id, res_id), obs in sorted(latest.items()):
            cat = obs.category or _SYSTEM_CATEGORY_MAP.get(sys_id, "UNKNOWN")
            action = self._rules.get(cat, "DELETE")
            st = obs.state
            ev_id = obs.file_id

            self._apply_rule(
                sys_id, res_id, cat, action, st, ev_id, obs,
                footprint, findings, remediations, verifications,
                target_account_id,
            )
            processed.add((sys_id, res_id))

        # --- Ensure primary account is covered ---
        if target_account_id:
            acc_key = ("account_service", target_account_id)
            if acc_key not in processed:
                # No observation found → rely on primary evidence
                verifications.append({
                    "phase": "VERIFICATION",
                    "system_id": "account_service",
                    "resource_id": target_account_id,
                    "operation": "VERIFY_RECORD_ABSENT",
                    "state": "ABSENT",
                    "evidence_id": primary_ev_id,
                })

        is_incomplete = bool(findings)
        status = "INCOMPLETE" if is_incomplete else "COMPLETE"

        # --- Stage 6: Evidence ID rules ---
        if is_incomplete:
            # All verifications for INCOMPLETE get empty evidence_id
            for v in verifications:
                v["evidence_id"] = ""
            all_steps = findings + remediations + verifications
        else:
            # Fill missing evidence_id on verification steps
            for v in verifications:
                if not v.get("evidence_id"):
                    v["evidence_id"] = primary_ev_id
            all_steps = verifications

        return status, all_steps

    # ── Rule application ──────────────────────────────────────────────────────

    def _apply_rule(
        self,
        sys_id: str,
        res_id: str,
        cat: str,
        action: str,
        state: str,
        ev_id: str,
        obs,
        footprint,
        findings: List,
        remediations: List,
        verifications: List,
        target_account_id: Optional[str],
    ) -> None:
        if action == "DELETE":
            if state == "PRESENT":
                findings.append(self._step("FINDING", sys_id, res_id,
                    "REPORT_REMAINING_RECORD", "PRESENT", ev_id))
                remediations.append(self._step("REMEDIATION", sys_id, res_id,
                    "DELETE_RECORD", "ABSENT", ""))
                verifications.append(self._step("VERIFICATION", sys_id, res_id,
                    "VERIFY_RECORD_ABSENT", "ABSENT", ""))
            else:  # ABSENT or already-treated
                verifications.append(self._step("VERIFICATION", sys_id, res_id,
                    "VERIFY_RECORD_ABSENT", "ABSENT", ev_id))

        elif action == "REDACT":
            if cat == "ACCOUNT_TOMBSTONE":
                # Tombstone: check PII leakage
                pii_present = self._tombstone_has_pii(obs, footprint)
                if pii_present:
                    findings.append(self._step("FINDING", sys_id, res_id,
                        "REPORT_EXPOSED_PII", "PRESENT", ev_id))
                    remediations.append(self._step("REMEDIATION", sys_id, res_id,
                        "REDACT_RECORD", "REDACTED", ""))
                    verifications.append(self._step("VERIFICATION", sys_id, res_id,
                        "VERIFY_RECORD_PRESENT", "PRESENT", ""))
                    verifications.append(self._step("VERIFICATION", sys_id, res_id,
                        "VERIFY_RECORD_REDACTED", "REDACTED", ""))
                else:
                    verifications.append(self._step("VERIFICATION", sys_id, res_id,
                        "VERIFY_RECORD_PRESENT", "PRESENT", ev_id))
                    verifications.append(self._step("VERIFICATION", sys_id, res_id,
                        "VERIFY_RECORD_REDACTED", "REDACTED", ev_id))
            elif state == "PRESENT":
                # Regular REDACT target with PII still visible
                findings.append(self._step("FINDING", sys_id, res_id,
                    "REPORT_EXPOSED_PII", "PRESENT", ev_id))
                remediations.append(self._step("REMEDIATION", sys_id, res_id,
                    "REDACT_RECORD", "REDACTED", ""))
                verifications.append(self._step("VERIFICATION", sys_id, res_id,
                    "VERIFY_RECORD_REDACTED", "REDACTED", ""))
            else:  # Already REDACTED
                verifications.append(self._step("VERIFICATION", sys_id, res_id,
                    "VERIFY_RECORD_REDACTED", "REDACTED", ev_id))

        elif action == "ANONYMIZE":
            if state in ("PRESENT",):
                findings.append(self._step("FINDING", sys_id, res_id,
                    "REPORT_EXPOSED_PII", "PRESENT", ev_id))
                remediations.append(self._step("REMEDIATION", sys_id, res_id,
                    "ANONYMIZE_RECORD", "ANONYMIZED", ""))
                verifications.append(self._step("VERIFICATION", sys_id, res_id,
                    "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED", ""))
            else:  # ANONYMIZED
                verifications.append(self._step("VERIFICATION", sys_id, res_id,
                    "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED", ev_id))

        elif action == "RETAIN":
            # Security audit logs: must still be present
            verifications.append(self._step("VERIFICATION", sys_id, res_id,
                "VERIFY_RECORD_PRESENT", "PRESENT", ev_id))

        # Integration/Connector special-casing
        if sys_id == "integration_service" and state == "ACTIVE":
            findings.append(self._step("FINDING", sys_id, res_id,
                "REPORT_ACTIVE_DATA_FLOW", "ACTIVE", ev_id))
            remediations.append(self._step("REMEDIATION", sys_id, res_id,
                "DISABLE_DATA_FLOW", "DISABLED", ""))
            verifications.append(self._step("VERIFICATION", sys_id, res_id,
                "VERIFY_DATA_FLOW_DISABLED", "DISABLED", ""))
        elif sys_id == "integration_service" and state in ("DISABLED", "ABSENT"):
            verifications.append(self._step("VERIFICATION", sys_id, res_id,
                "VERIFY_DATA_FLOW_DISABLED", "DISABLED", ev_id))

        # Backup restore risk special-casing
        if sys_id == "backup_service" and state == "ACTIVE":
            findings.append(self._step("FINDING", sys_id, res_id,
                "REPORT_RESTORE_RISK", "ACTIVE", ev_id))
            remediations.append(self._step("REMEDIATION", sys_id, res_id,
                "BLOCK_RESTORE", "BLOCKED", ""))
            verifications.append(self._step("VERIFICATION", sys_id, res_id,
                "VERIFY_RESTORE_BLOCKED", "BLOCKED", ""))
        elif sys_id == "backup_service" and state in ("BLOCKED", "ABSENT", "DISABLED"):
            verifications.append(self._step("VERIFICATION", sys_id, res_id,
                "VERIFY_RESTORE_BLOCKED", "BLOCKED", ev_id))

    # ── Tombstone PII check ───────────────────────────────────────────────────

    @staticmethod
    def _tombstone_has_pii(obs, footprint) -> bool:
        """Returns True if the tombstone observation still contains prohibited PII."""
        # A REDACTED state means PII has been stripped
        if obs.state == "REDACTED":
            return False
        # Check raw_text for PII tokens
        raw = (obs.raw_text or "").lower()
        for em in footprint.emails:
            if em and em in raw:
                return True
        for ph in footprint.phones:
            if ph and ph in raw:
                return True
        for nm in footprint.names:
            if nm and nm.lower() in raw:
                return True
        # If state is PRESENT and raw_text not definitively clean → assume PII still there
        return obs.state == "PRESENT"

    # ── Step factory ──────────────────────────────────────────────────────────

    @staticmethod
    def _step(
        phase: str,
        sys_id: str,
        res_id: str,
        operation: str,
        state: str,
        evidence_id: str,
    ) -> Dict[str, Any]:
        return {
            "phase": phase,
            "system_id": sys_id,
            "resource_id": res_id,
            "operation": operation,
            "state": state,
            "evidence_id": evidence_id,
        }

