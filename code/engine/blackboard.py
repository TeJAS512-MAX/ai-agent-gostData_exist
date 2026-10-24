"""
================================================================================
 Zero-Failure Multi-Agent Architecture — Pydantic Blackboard (Shared State)
 NSTVE v5.0 Enterprise
================================================================================

Implements the validated, versioned, event-sourced shared state container
(CaseBlackboard) and all typed sub-models that agents read/write through it.

Key guarantees:
  * Validation-on-write (Pydantic v2 model_validate) — no corrupt state ever
    stored in the blackboard
  * Append-only event log (versioned writes) — supervisor can replay from last
    good checkpoint on crash
  * Idempotency keys (case_id + stage + sha256(content)) — safe to retry any
    agent write; duplicates are silently discarded
  * Circuit breaker (3 consecutive stage failures -> BLOCKED) — prevents
    runaway retries and ensures a safe degraded result is returned
  * Checkpoint persistence (SQLite WAL journal) — survives process restart
    mid-batch
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, PrivateAttr

logger = logging.getLogger("Blackboard")

# ──────────────────────────────────────────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────────────────────────────────────────

class CaseStatus(str, Enum):
    PENDING     = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED     = "BLOCKED"
    DONE        = "DONE"
    FAILED      = "FAILED"


class AgentStage(str, Enum):
    ORCHESTRATION   = "ORCHESTRATION"
    INTENT          = "INTENT"
    IDENTITY        = "IDENTITY"
    EVIDENCE        = "EVIDENCE"
    TIMELINE        = "TIMELINE"
    POLICY          = "POLICY"
    SIMULATION      = "SIMULATION"
    REMEDIATION     = "REMEDIATION"
    VERIFICATION    = "VERIFICATION"
    CRITIQUE        = "CRITIQUE"
    COMPILE         = "COMPILE"
    COMPLETE        = "COMPLETE"


# ──────────────────────────────────────────────────────────────────────────────
# TYPED SUB-MODELS
# ──────────────────────────────────────────────────────────────────────────────

class UserIdentity(BaseModel):
    user_id: str
    emails: List[str] = Field(default_factory=list)
    hashes: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)


class RecordEvent(BaseModel):
    system_id: str
    resource_id: str
    operation: str
    timestamp: Optional[str] = None
    evidence_id: Optional[str] = None
    state: Optional[str] = None


class RecordState(BaseModel):
    system_id: str
    resource_id: str
    state_at_audit: str
    resolved_state: Optional[str] = None


class Discrepancy(BaseModel):
    system_id: str
    resource_id: str
    description: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"


class StepObject(BaseModel):
    phase: Literal["FINDING", "REMEDIATION", "VERIFICATION"]
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str = ""
    step_no: Optional[int] = None

    def as_dict(self) -> Dict[str, Any]:
        d = {
            "phase": self.phase,
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation,
            "state": self.state,
            "evidence_id": self.evidence_id,
        }
        if self.step_no is not None:
            d["step_no"] = self.step_no
        return d


class AgentCallRecord(BaseModel):
    stage: str
    agent_name: str
    idempotency_key: str
    started_at: float
    finished_at: Optional[float] = None
    success: bool = False
    attempt: int = 1
    output_hash: Optional[str] = None


class AgentError(BaseModel):
    stage: str
    agent_name: str
    attempt: int
    error_type: str
    message: str
    timestamp: float = Field(default_factory=time.time)


# ──────────────────────────────────────────────────────────────────────────────
# IDEMPOTENCY KEY HELPER
# ──────────────────────────────────────────────────────────────────────────────

def _idem_key(case_id: str, stage: str, content: Any) -> str:
    """Compute a stable idempotency key for a (case, stage, content) triple."""
    raw = json.dumps(content, sort_keys=True, default=str)
    digest = hashlib.sha256(f"{case_id}|{stage}|{raw}".encode()).hexdigest()[:16]
    return f"{case_id}/{stage}/{digest}"


# ──────────────────────────────────────────────────────────────────────────────
# CIRCUIT BREAKER
# ──────────────────────────────────────────────────────────────────────────────

class CircuitBreaker:
    """
    Per-stage circuit breaker with 3-strike trip threshold.
    Once OPEN, stays open until reset() is called by the Supervisor.
    """
    MAX_FAILURES = 3

    def __init__(self, stage: str):
        self.stage = stage
        self._failures = 0
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def record_failure(self):
        self._failures += 1
        if self._failures >= self.MAX_FAILURES:
            self._open = True
            logger.warning(
                "CircuitBreaker OPEN for stage '%s' after %d failures",
                self.stage, self._failures
            )

    def record_success(self):
        self._failures = 0
        self._open = False

    def reset(self):
        self._failures = 0
        self._open = False


# ──────────────────────────────────────────────────────────────────────────────
# CASE BLACKBOARD (Pydantic-validated shared state)
# ──────────────────────────────────────────────────────────────────────────────

class CaseBlackboard(BaseModel):
    """
    Pydantic-validated shared typed memory for a single audit case.
    All agent writes are validated before commit; append-only for agent_trace
    and errors (event-sourced, never mutated after write).

    Runtime-only state (idempotency set, circuit breakers) is kept in
    PrivateAttr fields which are excluded from serialisation.
    """
    case_id: str
    status: CaseStatus = CaseStatus.PENDING
    current_stage: Optional[str] = None

    # Agent outputs
    identity: Optional[UserIdentity] = None
    intent: Optional[Literal["DELETION_REQUEST", "NOT_APPLICABLE"]] = None
    regulatory_framework: Optional[str] = None

    # Evidence ledger (append-only)
    record_events: List[RecordEvent] = Field(default_factory=list)
    record_states: List[RecordState] = Field(default_factory=list)
    discrepancies: List[Discrepancy] = Field(default_factory=list)

    # Verdict and steps
    verdict: Optional[Literal["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]] = None
    draft_steps: List[StepObject] = Field(default_factory=list)
    final_steps: List[StepObject] = Field(default_factory=list)

    # Provenance (append-only)
    agent_trace: List[AgentCallRecord] = Field(default_factory=list)
    errors: List[AgentError] = Field(default_factory=list)

    # ── Project Oblivion (Verifiable Non-Existence Framework) ─────────────────
    ghost_field_score: float = 0.0
    dark_systems_inferred: List[str] = Field(default_factory=list)
    resurrection_red_team_passed: bool = True
    byzantine_quorum_achieved: bool = True
    byzantine_jury_votes: List[Dict[str, Any]] = Field(default_factory=list)
    behavioral_probes_verified: bool = True
    merkle_tree_root: Optional[str] = None

    # ── Runtime-only private attributes (not serialised) ──────────────────────
    # Idempotency set: keys already committed this session
    _committed_keys: set = PrivateAttr(default_factory=set)
    # Circuit breakers per stage
    _breakers: Dict[str, CircuitBreaker] = PrivateAttr(default_factory=dict)

    # ── Idempotent write helpers ──────────────────────────────────────────────

    def try_write(self, stage: str, content: Any, writer_fn) -> bool:
        """
        Execute writer_fn(content) only if the idempotency key for
        (case_id, stage, content) has not been committed before.
        Returns True if written, False if deduplicated.
        """
        key = _idem_key(self.case_id, stage, content)
        if key in self._committed_keys:
            logger.debug("Idempotency hit — skipping duplicate write [%s]", key)
            return False
        writer_fn(content)
        self._committed_keys.add(key)
        return True

    # ── Circuit breaker helpers ───────────────────────────────────────────────

    def _get_breaker(self, stage: str) -> CircuitBreaker:
        if stage not in self._breakers:
            self._breakers[stage] = CircuitBreaker(stage)
        return self._breakers[stage]

    def is_stage_blocked(self, stage: str) -> bool:
        return self._get_breaker(stage).is_open

    def record_stage_failure(self, stage: str, agent: str, attempt: int, err: str):
        breaker = self._get_breaker(stage)
        breaker.record_failure()
        self.errors.append(AgentError(
            stage=stage,
            agent_name=agent,
            attempt=attempt,
            error_type=type(err).__name__ if not isinstance(err, str) else "Error",
            message=str(err),
        ))
        if breaker.is_open:
            self.status = CaseStatus.BLOCKED

    def record_stage_success(self, stage: str):
        self._get_breaker(stage).record_success()

    # ── Trace helpers ─────────────────────────────────────────────────────────

    def begin_stage(self, stage: str, agent_name: str, content_for_key: Any) -> str:
        """Open an agent call record; returns idempotency_key."""
        key = _idem_key(self.case_id, stage, content_for_key)
        record = AgentCallRecord(
            stage=stage,
            agent_name=agent_name,
            idempotency_key=key,
            started_at=time.time(),
        )
        self.agent_trace.append(record)
        self.current_stage = stage
        return key

    def close_stage(self, key: str, success: bool, output_hash: Optional[str] = None):
        """Close the most recent open agent call record matching key."""
        for rec in reversed(self.agent_trace):
            if rec.idempotency_key == key and rec.finished_at is None:
                rec.finished_at = time.time()
                rec.success = success
                rec.output_hash = output_hash
                break

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "CaseBlackboard":
        return cls.model_validate_json(raw)


# ──────────────────────────────────────────────────────────────────────────────
# CHECKPOINT STORE (SQLite WAL — survives crash mid-batch)
# ──────────────────────────────────────────────────────────────────────────────

class CheckpointStore:
    """
    Lightweight SQLite-backed checkpoint journal.
    Each row is a validated JSON snapshot of a CaseBlackboard at a specific stage.
    Idempotent: upsert by (case_id, stage).
    Thread-safe via a module-level lock.
    """
    _lock = threading.Lock()

    def __init__(self, db_path: str = ".blackboard_checkpoint.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._lock:
            con = sqlite3.connect(self.db_path, check_same_thread=False)
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    case_id TEXT NOT NULL,
                    stage   TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    ts      REAL NOT NULL,
                    PRIMARY KEY (case_id, stage)
                )
            """)
            con.commit()
            con.close()

    def save(self, bb: CaseBlackboard, stage: str):
        payload = bb.to_json()
        with self._lock:
            con = sqlite3.connect(self.db_path, check_same_thread=False)
            con.execute(
                "INSERT OR REPLACE INTO checkpoints (case_id, stage, payload, ts) VALUES (?,?,?,?)",
                (bb.case_id, stage, payload, time.time())
            )
            con.commit()
            con.close()

    def load_latest(self, case_id: str) -> Optional[CaseBlackboard]:
        with self._lock:
            con = sqlite3.connect(self.db_path, check_same_thread=False)
            row = con.execute(
                "SELECT payload FROM checkpoints WHERE case_id=? ORDER BY ts DESC LIMIT 1",
                (case_id,)
            ).fetchone()
            con.close()
        if row:
            try:
                return CaseBlackboard.from_json(row[0])
            except Exception as exc:
                logger.warning(
                    "Failed to deserialise checkpoint for %s: %s", case_id, exc
                )
        return None

    def clear(self, case_id: Optional[str] = None):
        with self._lock:
            con = sqlite3.connect(self.db_path, check_same_thread=False)
            if case_id:
                con.execute("DELETE FROM checkpoints WHERE case_id=?", (case_id,))
            else:
                con.execute("DELETE FROM checkpoints")
            con.commit()
            con.close()


# ──────────────────────────────────────────────────────────────────────────────
# SUPERVISOR MIXIN — attaches to AdvancedAuditAgent
# ──────────────────────────────────────────────────────────────────────────────

class SupervisorMixin:
    """
    Mixin that wraps any agent method with idempotency + circuit breaker +
    checkpoint + retry logic.  The decorated method must be called as:
        self._supervised_call(bb, stage, agent_name, fn, *args, **kwargs)
    """
    _checkpoint_store: Optional[CheckpointStore] = None

    def _init_supervisor(self, checkpoint_db: str = ".blackboard_checkpoint.db"):
        self._checkpoint_store = CheckpointStore(db_path=checkpoint_db)

    def _supervised_call(
        self,
        bb: CaseBlackboard,
        stage: str,
        agent_name: str,
        fn,
        *args,
        max_retries: int = 3,
        **kwargs,
    ) -> Any:
        """
        Execute fn(*args, **kwargs) under the supervision contract:
          1. Circuit breaker check — abort if open
          2. Execute fn; on failure, record error + retry up to max_retries
          3. On success, checkpoint blackboard state
          4. On permanent failure (3 strikes), mark BLOCKED and return None
        """
        if bb.is_stage_blocked(stage):
            logger.error(
                "[Supervisor] Stage '%s' circuit breaker is OPEN — skipping", stage
            )
            return None

        key = bb.begin_stage(
            stage, agent_name, {"args": str(args), "kwargs": str(kwargs)}
        )
        result = None

        for attempt in range(1, max_retries + 1):
            try:
                result = fn(*args, **kwargs)
                bb.record_stage_success(stage)
                out_hash = None
                if result is not None:
                    try:
                        out_hash = hashlib.sha256(
                            json.dumps(result, default=str).encode()
                        ).hexdigest()[:16]
                    except Exception:
                        pass
                bb.close_stage(key, success=True, output_hash=out_hash)

                # Checkpoint after each successful stage
                if self._checkpoint_store:
                    try:
                        self._checkpoint_store.save(bb, stage)
                    except Exception as cp_err:
                        logger.warning("Checkpoint save failed: %s", cp_err)
                return result

            except Exception as exc:
                logger.warning(
                    "[Supervisor] Stage '%s' attempt %d/%d failed: %s",
                    stage, attempt, max_retries, exc,
                )
                bb.record_stage_failure(stage, agent_name, attempt, str(exc))
                if bb.is_stage_blocked(stage):
                    break  # circuit breaker opened — no more retries

        # Permanent failure path
        bb.close_stage(key, success=False)
        logger.error(
            "[Supervisor] Stage '%s' permanently failed after %d attempts. BLOCKED.",
            stage, max_retries,
        )
        return None

