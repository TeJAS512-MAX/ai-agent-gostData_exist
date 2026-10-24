"""
Stage 3: Bi-Temporal Lineage & Reachability DAG
================================================
Parses system_activity.csv (filtered to events ≤ audit_at) and builds a
per-(system_id, resource_id) temporal DAG to evaluate:

  1. Active data flows  → REPORT_ACTIVE_DATA_FLOW
  2. Restore risks      → REPORT_RESTORE_RISK

Uses a Petri-Net simulation at t_audit + Δt: if the latest event on a
pipeline is an "enabling" event (SYNC_START, EXPORT_START, INDEX_RECORD, etc.)
without a subsequent "disabling" event, the pipeline is ACTIVE.

Key event classifications:
  Flow-enabling : SYNC_RECORD, SYNC_START, EXPORT_START, EXPORT_RECORD,
                  INDEX_RECORD, IMPORT_RECORD, CONNECTOR_SYNC
  Flow-disabling: DISABLE_CONNECTOR, DISABLE_FLOW, SYNC_STOP, EXPORT_CANCEL
  Backup-create : CREATE_BACKUP, SNAPSHOT_CREATE, BACKUP_COMPLETE
  Block-restore : BLOCK_RESTORE, RESTORE_BLOCKED, BACKUP_EXPIRY
  Delete-events : DELETE_ACCOUNT, DELETE_RECORD, ANONYMIZE_RECORD,
                  REDACT_RECORD, DELETION_COMPLETE
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ── Event taxonomy ────────────────────────────────────────────────────────────

_FLOW_ENABLE = {
    "SYNC_RECORD", "SYNC_START", "CONNECTOR_SYNC",
    "EXPORT_START", "EXPORT_RECORD",
    "INDEX_RECORD",
    "IMPORT_RECORD",
}

_FLOW_DISABLE = {
    "DISABLE_CONNECTOR", "DISABLE_FLOW", "SYNC_STOP",
    "EXPORT_CANCEL", "EXPORT_COMPLETE",
}

_BACKUP_CREATE = {
    "CREATE_BACKUP", "SNAPSHOT_CREATE", "BACKUP_COMPLETE",
    "BACKUP_START",
}

_BACKUP_BLOCK = {
    "BLOCK_RESTORE", "RESTORE_BLOCKED", "BACKUP_EXPIRY",
    "BACKUP_PURGE", "BACKUP_DELETE",
}

_DELETE_EVENTS = {
    "DELETE_ACCOUNT", "DELETE_RECORD", "ANONYMIZE_RECORD",
    "REDACT_RECORD", "DELETION_COMPLETE", "PURGE_RECORD",
}


# ── DAG node ──────────────────────────────────────────────────────────────────

@dataclass
class DagNode:
    activity_id: str
    event_time: pd.Timestamp
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    result: str
    details: str


@dataclass
class FlowRisk:
    """An active data-flow or restore risk discovered for a resource."""
    kind: str        # "ACTIVE_FLOW" | "RESTORE_RISK"
    system_id: str
    resource_id: str
    activity_id: str  # evidence citation


# ── Temporal DAG ─────────────────────────────────────────────────────────────

class TemporalDAG:
    """
    Stage 3: Bi-Temporal Lineage & Reachability DAG.

    Usage:
        dag = TemporalDAG(dataset_dir="dataset")
        risks = dag.get_risks(footprint, audit_at="2026-09-27T13:00:00Z")
    """

    def __init__(self, dataset_dir: str = "dataset"):
        import os
        path = os.path.join(dataset_dir, "system_activity.csv")
        self._df = pd.read_csv(path)
        self._df["event_dt"] = pd.to_datetime(self._df["event_time"], utc=True)
        # Normalise string fields
        for col in ("event_type", "source_system", "target_system", "resource_id",
                    "reported_result", "details"):
            self._df[col] = self._df[col].fillna("").astype(str)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_risks(
        self,
        footprint,  # IdentityFootprint
        audit_at: str,
    ) -> List[FlowRisk]:
        """
        Return all active-flow and restore risks for the given identity footprint
        at or before audit_at.
        """
        audit_dt = pd.to_datetime(audit_at, utc=True)
        snapshot = self._df[self._df["event_dt"] <= audit_dt].copy()

        risks: List[FlowRisk] = []
        risks.extend(self._eval_flows(snapshot, footprint, audit_dt))
        risks.extend(self._eval_backups(snapshot, footprint, audit_dt))
        return risks

    def get_worker_batch(
        self,
        reported_at: str,
        window_minutes_before: int = 90,
        window_minutes_after: int = 15,
    ) -> pd.DataFrame:
        """Return deletion_worker activity rows in the temporal window around reported_at."""
        rep_dt = pd.to_datetime(reported_at, utc=True)
        w_start = rep_dt - pd.Timedelta(minutes=window_minutes_before)
        w_end = rep_dt + pd.Timedelta(minutes=window_minutes_after)
        return self._df[
            (self._df["event_dt"] >= w_start)
            & (self._df["event_dt"] <= w_end)
            & (self._df["source_system"] == "deletion_worker")
        ].copy()

    # ── Flow evaluation ───────────────────────────────────────────────────────

    def _eval_flows(
        self,
        snapshot: pd.DataFrame,
        footprint,
        audit_dt: pd.Timestamp,
    ) -> List[FlowRisk]:
        """
        Find active connector / sync / export flows that can recreate deleted data.
        A flow is ACTIVE if its last known state at audit_at is enabling.
        """
        flow_rows = snapshot[
            snapshot["event_type"].isin(_FLOW_ENABLE | _FLOW_DISABLE)
        ].copy()

        risks: List[FlowRisk] = []
        # Group by (target_system, resource_id)
        for (tgt, res_id), grp in flow_rows.groupby(["target_system", "resource_id"]):
            grp_sorted = grp.sort_values("event_dt")
            last = grp_sorted.iloc[-1]
            # Check if this flow is linked to the user's identity
            if not self._row_matches_identity(last, footprint):
                # Also check details field
                if not any(
                    tok in last["details"]
                    for tok in footprint.emails | footprint.phones | {footprint.user_id}
                ):
                    continue
            if last["event_type"] in _FLOW_ENABLE:
                risks.append(FlowRisk(
                    kind="ACTIVE_FLOW",
                    system_id=tgt or last["source_system"],
                    resource_id=res_id,
                    activity_id=last["activity_id"],
                ))
        return risks

    def _eval_backups(
        self,
        snapshot: pd.DataFrame,
        footprint,
        audit_dt: pd.Timestamp,
    ) -> List[FlowRisk]:
        """
        Find unblocked backups / snapshots that could restore deleted data.
        A backup is a restore risk unless a BLOCK_RESTORE event follows it.
        """
        backup_rows = snapshot[
            snapshot["event_type"].isin(_BACKUP_CREATE | _BACKUP_BLOCK)
        ].copy()

        risks: List[FlowRisk] = []
        for (tgt, res_id), grp in backup_rows.groupby(["target_system", "resource_id"]):
            grp_sorted = grp.sort_values("event_dt")
            last = grp_sorted.iloc[-1]
            # Must involve user data
            if not self._row_matches_identity(last, footprint):
                if not any(
                    tok in last["details"]
                    for tok in footprint.emails | footprint.phones | {footprint.user_id}
                ):
                    continue
            if last["event_type"] in _BACKUP_CREATE:
                risks.append(FlowRisk(
                    kind="RESTORE_RISK",
                    system_id=last["source_system"] or tgt,
                    resource_id=res_id,
                    activity_id=last["activity_id"],
                ))
        return risks

    def _row_matches_identity(self, row: pd.Series, footprint) -> bool:
        for col in ("resource_id", "details"):
            val = str(row.get(col, ""))
            if footprint.user_id in val:
                return True
            for em in footprint.emails:
                if em in val:
                    return True
        return False

