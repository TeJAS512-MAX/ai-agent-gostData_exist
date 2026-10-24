"""
================================================================================
 Northstar Shop -- Multi-Jurisdiction Compliance Matrix & Invariant Verifier
 (Enterprise Autonomous Architecture Module)
================================================================================

Encapsulates global statutory data retention mandates, formal contract invariants,
and causal cycle prevention across:
  1. GDPR (EU 2016/679) Art. 17 (Right to Erasure) & Art. 17(3) Legal Retention
  2. German Commercial Code (HGB § 257 & AO § 147 - 10-Year Statutory Retention)
  3. California Consumer Privacy Act (CCPA / CPRA Cal. Civ. Code § 1798.105(d))
  4. Health Insurance Portability and Accountability Act (HIPAA 45 CFR § 164.316)
  5. Sarbanes-Oxley Act (SOX § 802 / 18 U.S.C. § 1520 - 7-Year Audit Records)
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("ComplianceMatrix")


# ── Statutory Retentions ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class StatutoryRule:
    jurisdiction: str
    statute: str
    category: str
    required_treatment: str
    retention_period_years: int
    rationale: str


GLOBAL_STATUTORY_REGIME: Dict[str, StatutoryRule] = {
    "SECURITY_AUDIT_LOG": StatutoryRule(
        jurisdiction="GLOBAL",
        statute="GDPR Art 32 / SOC 2 Type II / ISO 27001",
        category="SECURITY_AUDIT_LOG",
        required_treatment="RETAIN",
        retention_period_years=7,
        rationale="Immutable security event logging required to prove auditability and integrity."
    ),
    "LEGAL_HOLD_RECORD": StatutoryRule(
        jurisdiction="GLOBAL",
        statute="FRCP Rule 37(e) / Sarbanes-Oxley § 802",
        category="LEGAL_HOLD_RECORD",
        required_treatment="RETAIN",
        retention_period_years=7,
        rationale="Active legal hold supersedes right-to-erasure until litigation resolution."
    ),
    "ACCOUNT_TOMBSTONE": StatutoryRule(
        jurisdiction="EU / US",
        statute="GDPR Recital 65 / CCPA § 1798.105(d)(1)",
        category="ACCOUNT_TOMBSTONE",
        required_treatment="REDACT",
        retention_period_years=10,
        rationale="Preserves internal reference integrity for retained ledger entries with PII stripped."
    ),
    "BACKUP_ARCHIVE": StatutoryRule(
        jurisdiction="EU / US",
        statute="EDPB Guidelines 05/2021 on Right to Erasure in Backups",
        category="BACKUP_ARCHIVE",
        required_treatment="BLOCK_RESTORE",
        retention_period_years=1,
        rationale="Backups cannot be selectively overwritten; restore paths must be blocked until expiry."
    ),
    "TAX_TRANSACTION_LEDGER": StatutoryRule(
        jurisdiction="GERMANY",
        statute="German HGB § 257 & AO § 147",
        category="COMMERCIAL_INVOICE",
        required_treatment="RETAIN",
        retention_period_years=10,
        rationale="Statutory 10-year commercial and tax retention exemption under GDPR Art. 17(3)(b)."
    ),
}


# ── Formal Contract Invariant Verifier ────────────────────────────────────────

class ContractInvariantVerifier:
    """
    Formal mathematical verifier enforcing strict competition & enterprise invariants.
    """

    ALLOWED_OPERATIONS: Dict[str, Dict[str, str]] = {
        "FINDING": {
            "REPORT_REMAINING_RECORD": "PRESENT",
            "REPORT_EXPOSED_PII": "PRESENT",
            "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
            "REPORT_RESTORE_RISK": "ACTIVE",
        },
        "REMEDIATION": {
            "DISABLE_DATA_FLOW": "DISABLED",
            "BLOCK_RESTORE": "BLOCKED",
            "DELETE_RECORD": "ABSENT",
            "REDACT_RECORD": "REDACTED",
            "ANONYMIZE_RECORD": "ANONYMIZED",
        },
        "VERIFICATION": {
            "VERIFY_RECORD_ABSENT": "ABSENT",
            "VERIFY_RECORD_PRESENT": "PRESENT",
            "VERIFY_RECORD_REDACTED": "REDACTED",
            "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
            "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
            "VERIFY_RESTORE_BLOCKED": "BLOCKED",
        },
    }

    PHASE_RANK = {"FINDING": 1, "REMEDIATION": 2, "VERIFICATION": 3}

    @classmethod
    def verify_steps(cls, steps: List[Dict[str, Any]], deletion_status: str, case_id: str = "") -> Tuple[bool, List[str]]:
        """
        Formally verifies that steps_json complies with every specification axiom.
        Returns (is_valid, list_of_violations).
        """
        violations = []

        # Axiom 1: NOT_APPLICABLE must have empty steps
        if deletion_status == "NOT_APPLICABLE":
            if len(steps) != 0:
                violations.append(f"{case_id}: NOT_APPLICABLE must have empty steps array, found {len(steps)} steps.")
            return len(violations) == 0, violations

        # Axiom 2: Monotonic Step Index Continuity (1..N)
        for expected_no, step in enumerate(steps, start=1):
            if step.get("step_no") != expected_no:
                violations.append(f"{case_id}: Step number discontinuity: expected {expected_no}, got {step.get('step_no')}")

        # Axiom 3: Phase Ordering Monotonicity (FINDING -> REMEDIATION -> VERIFICATION)
        current_phase_rank = 0
        for step in steps:
            phase = step.get("phase", "")
            prank = cls.PHASE_RANK.get(phase, 99)
            if prank < current_phase_rank:
                violations.append(f"{case_id}: Phase regression from rank {current_phase_rank} to {prank} ({phase})")
            current_phase_rank = prank

        # Axiom 4: Operator & State Legality
        for step in steps:
            phase = step.get("phase", "")
            op = step.get("operation", "")
            st = step.get("state", "")
            ev = step.get("evidence_id", "")

            if phase not in cls.ALLOWED_OPERATIONS:
                violations.append(f"{case_id}: Unknown phase '{phase}'")
                continue

            allowed_states = cls.ALLOWED_OPERATIONS[phase]
            if op not in allowed_states:
                violations.append(f"{case_id}: Illegal operation '{op}' for phase '{phase}'")
            elif allowed_states[op] != st:
                violations.append(f"{case_id}: State mismatch for '{op}': expected '{allowed_states[op]}', got '{st}'")

            # Axiom 5: Evidence Citation Rules
            if deletion_status == "COMPLETE":
                if phase != "VERIFICATION":
                    violations.append(f"{case_id}: COMPLETE status contains non-VERIFICATION step: {phase}:{op}")
                if not ev:
                    violations.append(f"{case_id}: COMPLETE verification step missing evidence citation: {op}")
            elif deletion_status == "INCOMPLETE":
                if phase == "FINDING" and not ev:
                    violations.append(f"{case_id}: INCOMPLETE finding step missing evidence citation: {op}")
                elif phase in ("REMEDIATION", "VERIFICATION") and ev != "":
                    violations.append(f"{case_id}: Proposed {phase} step must have empty evidence_id, got '{ev}'")

        return len(violations) == 0, violations

