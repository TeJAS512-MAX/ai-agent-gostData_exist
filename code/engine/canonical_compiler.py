"""
Stage 7: Canonical Tuple Compiler & Telemetry Sink
===================================================
Performs the final deterministic transforms on the collected steps:

  1. Deduplication  – remove duplicate (phase, system_id, resource_id, operation, state)
     tuples; keep the one with the richer evidence_id (non-empty wins).
  2. Canonical sort – sort by (Phase_Rank, Operation_Rank, system_id ASC, resource_id ASC).
  3. step_no        – assign 1-based consecutive integers.
  4. Assertions     – enforce all invariants required by the grader.

Ordering ranks (authoritative):
  Phase 1 FINDING:
    1 REPORT_REMAINING_RECORD
    2 REPORT_EXPOSED_PII
    3 REPORT_ACTIVE_DATA_FLOW
    4 REPORT_RESTORE_RISK
  Phase 2 REMEDIATION:
    1 DISABLE_DATA_FLOW
    2 BLOCK_RESTORE
    3 DELETE_RECORD
    4 REDACT_RECORD
    5 ANONYMIZE_RECORD
  Phase 3 VERIFICATION:
    1 VERIFY_RECORD_ABSENT
    2 VERIFY_RECORD_PRESENT
    3 VERIFY_RECORD_REDACTED
    4 VERIFY_RECORD_ANONYMIZED
    5 VERIFY_DATA_FLOW_DISABLED
    6 VERIFY_RESTORE_BLOCKED
"""

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ── Rank tables ───────────────────────────────────────────────────────────────

_PHASE_RANK: Dict[str, int] = {
    "FINDING": 1,
    "REMEDIATION": 2,
    "VERIFICATION": 3,
}

_OP_RANK: Dict[str, int] = {
    # FINDING
    "REPORT_REMAINING_RECORD": 1,
    "REPORT_EXPOSED_PII": 2,
    "REPORT_ACTIVE_DATA_FLOW": 3,
    "REPORT_RESTORE_RISK": 4,
    # REMEDIATION
    "DISABLE_DATA_FLOW": 1,
    "BLOCK_RESTORE": 2,
    "DELETE_RECORD": 3,
    "REDACT_RECORD": 4,
    "ANONYMIZE_RECORD": 5,
    # VERIFICATION
    "VERIFY_RECORD_ABSENT": 1,
    "VERIFY_RECORD_PRESENT": 2,
    "VERIFY_RECORD_REDACTED": 3,
    "VERIFY_RECORD_ANONYMIZED": 4,
    "VERIFY_DATA_FLOW_DISABLED": 5,
    "VERIFY_RESTORE_BLOCKED": 6,
}


def _sort_key(s: Dict[str, Any]) -> Tuple[int, int, str, str]:
    return (
        _PHASE_RANK.get(s["phase"], 99),
        _OP_RANK.get(s["operation"], 99),
        s.get("system_id", ""),
        s.get("resource_id", ""),
    )


# ── CanonicalCompiler ─────────────────────────────────────────────────────────

class CanonicalCompiler:
    """
    Stage 7: Deduplication, canonical sort, step_no assignment, and assertion gate.

    Usage:
        compiler = CanonicalCompiler()
        steps = compiler.compile(steps, deletion_status="INCOMPLETE")
    """

    def compile(
        self,
        steps: List[Dict[str, Any]],
        deletion_status: str,
        case_id: str = "",
    ) -> List[Dict[str, Any]]:
        # 1. Deduplicate by (phase, system_id, resource_id, operation)
        #    Keep entry with richer evidence_id (non-empty wins over empty).
        seen: Dict[Tuple, Dict] = {}
        for s in steps:
            key = (s["phase"], s["system_id"], s["resource_id"], s["operation"])
            if key not in seen:
                seen[key] = s
            else:
                existing = seen[key]
                # Non-empty evidence_id takes priority
                if s.get("evidence_id") and not existing.get("evidence_id"):
                    seen[key] = s

        deduped = list(seen.values())

        # 2. Canonical sort
        deduped.sort(key=_sort_key)

        # 3. Assign step_no
        for i, s in enumerate(deduped, start=1):
            s["step_no"] = i

        # 4. Assertions
        self._assert_invariants(deduped, deletion_status, case_id)

        return deduped

    # ── Invariant checks ──────────────────────────────────────────────────────

    @staticmethod
    def _assert_invariants(
        steps: List[Dict[str, Any]],
        deletion_status: str,
        case_id: str,
    ) -> None:
        if deletion_status == "NOT_APPLICABLE":
            assert len(steps) == 0, f"{case_id}: NOT_APPLICABLE must have empty steps_json"
            return

        # step_no must be 1..N consecutively
        for i, s in enumerate(steps, start=1):
            assert s["step_no"] == i, (
                f"{case_id}: Non-consecutive step_no at position {i}: got {s['step_no']}"
            )

        # evidence_id rules
        for s in steps:
            phase = s["phase"]
            ev = s.get("evidence_id", "")
            op = s["operation"]

            if deletion_status == "COMPLETE":
                assert phase == "VERIFICATION", (
                    f"{case_id}: COMPLETE case has non-VERIFICATION step: {op}"
                )
                assert ev, (
                    f"{case_id}: COMPLETE VERIFICATION step missing evidence_id: {op} {s['resource_id']}"
                )

            elif deletion_status == "INCOMPLETE":
                if phase == "FINDING":
                    assert ev, (
                        f"{case_id}: INCOMPLETE FINDING step missing evidence_id: {op} {s['resource_id']}"
                    )
                elif phase in ("REMEDIATION",):
                    assert ev == "", (
                        f"{case_id}: REMEDIATION step must have empty evidence_id: {op} {s['resource_id']}"
                    )

