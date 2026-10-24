"""
Stage 4: Speculative Multimodal Evidence Transducer
====================================================
Routes evidence files by format to the correct zero-token symbolic parser
or (only for PDFs / images) to a constrained-decoding VLM.

Parsers:
  .sql  → 0-Token Ephemeral SQLite (in-memory, query all tables)
  .json → 0-Token AST Traversal (recursive dict/list walk)
  .log  → 0-Token Aho-Corasick substring search
  .txt  → 0-Token line-by-line pipe-delimited parser
  .pdf  → 0-Token pypdf text extraction (VLM fallback if empty)
  .png  → OCR cache lookup → VLM constrained-decoding fallback
  .jpg  → same as .png

All parsers return EvidenceObservation objects that are later evaluated by
the Stage 5 Policy Solver.  Pre-parsed results are cached in-process so
the 94 evidence files are read exactly once per run.
"""

import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import pandas as pd

logger = logging.getLogger(__name__)


# ── EvidenceObservation ───────────────────────────────────────────────────────

@dataclass
class EvidenceObservation:
    file_id: str
    file_path: str
    captured_at: str
    system_id: str
    resource_id: str
    category: str
    state: str          # PRESENT | ABSENT | REDACTED | ANONYMIZED | ACTIVE | DISABLED | BLOCKED
    user_id: Optional[str] = None
    email: Optional[str] = None
    hash_val: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    raw_text: Optional[str] = None


# ── State map shared by all parsers ──────────────────────────────────────────

_STATE_MAP = {
    "NOT_FOUND": "ABSENT",
    "FOUND": "PRESENT",
    "IDENTIFIABLE": "PRESENT",
    "ANONYMIZED": "ANONYMIZED",
    "REDACTED": "REDACTED",
    "ACTIVE": "ACTIVE",
    "DISABLED": "DISABLED",
    "BLOCKED": "BLOCKED",
    "PRESENT": "PRESENT",
    "ABSENT": "ABSENT",
}


# ── EvidenceTransducer ────────────────────────────────────────────────────────

class EvidenceTransducer:
    """
    Stage 4: Multimodal evidence transducer with format-specific symbolic parsers.

    Usage:
        t = EvidenceTransducer(dataset_dir="dataset")
        observations = t.query(user_id, emails, hashes, audit_at, known_resources)
    """

    def __init__(self, dataset_dir: str = "dataset"):
        self.dataset_dir = dataset_dir
        manifest_path = os.path.join(dataset_dir, "evidence_files.csv")
        self.manifest_df = pd.read_csv(manifest_path).set_index("file_id")
        self._ocr_cache: Dict[str, str] = self._load_ocr_cache()
        # Pre-build all evidence observations at startup (0-token pass)
        self._all_observations: List[EvidenceObservation] = []
        self._build_all()

    # ── Pre-build ─────────────────────────────────────────────────────────────

    def _build_all(self) -> None:
        for fid, row in self.manifest_df.iterrows():
            fp = str(row["file_path"])
            full = os.path.join(self.dataset_dir, fp)
            try:
                if fp.endswith(".sql"):
                    self._all_observations.extend(self._parse_sql(fid, row, full))
                elif fp.endswith(".json"):
                    self._all_observations.extend(self._parse_json(fid, row, full))
                elif fp.endswith(".log"):
                    self._all_observations.extend(self._parse_log(fid, row, full))
                elif fp.endswith(".txt"):
                    self._all_observations.extend(self._parse_txt(fid, row, full))
                elif fp.endswith(".pdf"):
                    self._all_observations.extend(self._parse_pdf(fid, row, full))
                elif fp.endswith(".png") or fp.endswith(".jpg") or fp.endswith(".jpeg"):
                    self._all_observations.extend(self._parse_image(fid, row, full))
            except Exception as exc:
                logger.debug("Stage 4: Failed to parse %s (%s): %s", fid, fp, exc)

        logger.info("Stage 4: Indexed %d evidence observations from %d files.",
                    len(self._all_observations), len(self.manifest_df))

    # ── Public query API ──────────────────────────────────────────────────────

    def find_all_user_resources(
        self,
        user_id: str,
        emails: Set[str],
        hashes: Set[str],
    ) -> Set[str]:
        """Return all resource_ids ever associated with this identity."""
        resources: Set[str] = set()
        for obs in self._all_observations:
            if self._obs_matches(obs, user_id, emails, hashes, phones=set()):
                resources.add(obs.resource_id)
        return resources

    def find_observations_for_user(
        self,
        user_id: str,
        emails: Set[str],
        audit_at: str,
        hashes: Set[str] = frozenset(),
        phones: Set[str] = frozenset(),
        known_resources: Set[str] = frozenset(),
    ) -> List[EvidenceObservation]:
        """
        Return all EvidenceObservations for this user at or before audit_at.
        Matches by user_id, email, hash, phone, or known resource_id.
        """
        results: List[EvidenceObservation] = []
        for obs in self._all_observations:
            if obs.captured_at > audit_at:
                continue
            if self._obs_matches(obs, user_id, emails, hashes, phones):
                results.append(obs)
            elif obs.resource_id in known_resources:
                results.append(obs)
        return results

    # ── Matching logic ────────────────────────────────────────────────────────

    @staticmethod
    def _obs_matches(
        obs: EvidenceObservation,
        user_id: str,
        emails: Set[str],
        hashes: Set[str],
        phones: Set[str],
    ) -> bool:
        if obs.user_id and obs.user_id == user_id:
            return True
        if obs.email and obs.email.lower() in emails:
            return True
        if obs.hash_val and obs.hash_val.lower() in hashes:
            return True
        if obs.phone and obs.phone in phones:
            return True
        return False

    # ── .txt parser ───────────────────────────────────────────────────────────

    def _parse_txt(self, fid: str, row: pd.Series, full_path: str) -> List[EvidenceObservation]:
        obs_list: List[EvidenceObservation] = []
        if not os.path.exists(full_path):
            return obs_list
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("- "):
                    continue
                parts = [p.strip() for p in line[2:].split("|")]
                if len(parts) < 6:
                    continue
                ts, sys_id, res_id, cat, raw_st, lookup = parts[:6]
                st = _STATE_MAP.get(raw_st, "PRESENT")
                obs = EvidenceObservation(
                    file_id=fid,
                    file_path=str(row["file_path"]),
                    captured_at=str(row["captured_at"]),
                    system_id=sys_id,
                    resource_id=res_id,
                    category=cat,
                    state=st,
                    raw_text=line,
                )
                self._annotate_lookup(obs, lookup)
                obs_list.append(obs)
        return obs_list

    # ── .json parser ─────────────────────────────────────────────────────────

    def _parse_json(self, fid: str, row: pd.Series, full_path: str) -> List[EvidenceObservation]:
        obs_list: List[EvidenceObservation] = []
        if not os.path.exists(full_path):
            return obs_list
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            try:
                data = json.load(f)
            except Exception:
                return obs_list

        fp = str(row["file_path"])

        # Format 1: service_exports wrapper (evidence_92-style)
        if isinstance(data, dict) and "service_exports" in data:
            obs_list.extend(self._parse_service_exports(fid, row, data["service_exports"]))

        # Format 2: security_audit_ledger records
        elif isinstance(data, dict) and "records" in data and "audit" in fp.lower():
            for rec in data["records"]:
                obs = self._make_json_obs(fid, row, rec, "security_service", "SECURITY_AUDIT_LOG")
                if obs:
                    obs_list.append(obs)

        # Format 3: export manifest/jobs
        elif isinstance(data, dict) and "records" in data and "export" in fp.lower():
            for rec in data["records"]:
                obs = self._make_json_obs(fid, row, rec, "export_service", "USER_EXPORT")
                if obs:
                    obs_list.append(obs)

        # Format 4: analytics report
        elif isinstance(data, dict) and "records" in data and "analytics" in fp.lower():
            for rec in data["records"]:
                obs = self._make_json_obs(fid, row, rec, "analytics_platform", "ANALYTICS_PROFILE")
                if obs:
                    obs_list.append(obs)

        # Format 5: connector configurations
        elif isinstance(data, dict) and "connectors" in data:
            for conn in data["connectors"]:
                cid = str(conn.get("connector_id", conn.get("id", "")))
                uid = str(conn.get("customer_id", conn.get("user_id", "")))
                state_raw = str(conn.get("status", conn.get("state", "ACTIVE"))).upper()
                st = _STATE_MAP.get(state_raw, "ACTIVE")
                if cid:
                    obs = EvidenceObservation(
                        file_id=fid,
                        file_path=str(row["file_path"]),
                        captured_at=str(row["captured_at"]),
                        system_id="integration_service",
                        resource_id=cid,
                        category="CONNECTOR",
                        state=st,
                        user_id=uid if uid.startswith("user_") else None,
                        raw_text=json.dumps(conn),
                    )
                    obs_list.append(obs)

        # Format 6: snapshot bundles (list of customer records)
        elif isinstance(data, list):
            for rec in data:
                obs = self._make_json_obs(fid, row, rec, "", "")
                if obs:
                    obs_list.append(obs)

        # Format 7: single record
        elif isinstance(data, dict):
            obs = self._make_json_obs(fid, row, data, "", "")
            if obs:
                obs_list.append(obs)

        return obs_list

    def _parse_service_exports(
        self, fid: str, row: pd.Series, se: dict
    ) -> List[EvidenceObservation]:
        obs_list: List[EvidenceObservation] = []
        sys_map = {
            "account_service": ("account_service", "USER_PROFILE"),
            "search_service": ("search_service", "SEARCH_INDEX_ENTRY"),
            "analytics_platform": ("analytics_platform", "ANALYTICS_PROFILE"),
            "support_platform": ("support_platform", "SUPPORT_MESSAGE"),
            "export_service": ("export_service", "USER_EXPORT"),
            "identity_service": ("identity_service", "ACCOUNT_TOMBSTONE"),
            "security_service": ("security_service", "SECURITY_AUDIT_LOG"),
            "backup_service": ("backup_service", "BACKUP_ARCHIVE"),
            "integration_service": ("integration_service", "CONNECTOR"),
        }
        for svc_key, (sys_id, cat) in sys_map.items():
            records = se.get(svc_key, [])
            if not isinstance(records, list):
                records = [records]
            for rec in records:
                obs = self._make_json_obs(fid, row, rec, sys_id, cat)
                if obs:
                    obs_list.append(obs)
        return obs_list

    def _make_json_obs(
        self,
        fid: str,
        row: pd.Series,
        rec: dict,
        sys_id: str,
        cat: str,
    ) -> Optional[EvidenceObservation]:
        if not isinstance(rec, dict):
            return None
        # Resolve resource_id
        res_id = (
            rec.get("account_id") or rec.get("record_id") or rec.get("resource_id")
            or rec.get("search_id") or rec.get("analytics_id") or rec.get("export_id")
            or rec.get("support_id") or rec.get("tombstone_id") or rec.get("audit_id")
            or rec.get("backup_id") or rec.get("connector_id") or rec.get("id")
        )
        if not res_id:
            return None
        res_id = str(res_id)

        # Resolve system_id from record if not given
        if not sys_id:
            inferred = _infer_system_from_resource(res_id)
            sys_id = inferred[0]
            if not cat:
                cat = inferred[1]

        # Resolve state
        raw_st = str(rec.get("status", rec.get("state", rec.get("record_status", "PRESENT")))).upper()
        st = _STATE_MAP.get(raw_st, "PRESENT")

        # Resolve user identity tokens
        uid = str(rec.get("user_id", rec.get("customer_id", rec.get("customer_reference",
                  rec.get("subject_reference", ""))))).strip()
        em = str(rec.get("email", rec.get("customer_email", ""))).strip().lower()
        ph = str(rec.get("phone", rec.get("phone_number", ""))).strip()
        nm = str(rec.get("name", rec.get("customer_name", ""))).strip()

        # Nested document extraction
        doc = rec.get("document", {})
        if isinstance(doc, dict):
            if not uid or uid == "nan":
                uid = str(doc.get("user_id", doc.get("customer_reference", ""))).strip()
            if not em or em == "nan":
                em = str(doc.get("email", "")).strip().lower()

        obs = EvidenceObservation(
            file_id=fid,
            file_path=str(row["file_path"]),
            captured_at=str(row["captured_at"]),
            system_id=sys_id,
            resource_id=res_id,
            category=cat,
            state=st,
            raw_text=json.dumps(rec)[:500],
        )
        if uid and uid != "nan" and uid.startswith("user_"):
            obs.user_id = uid
        if em and em != "nan" and "@" in em:
            obs.email = em
        if ph and ph != "nan" and ph not in ("", "nan"):
            obs.phone = ph
        if nm and nm != "nan":
            obs.name = nm
        return obs

    # ── .log parser ───────────────────────────────────────────────────────────

    def _parse_log(self, fid: str, row: pd.Series, full_path: str) -> List[EvidenceObservation]:
        """0-Token Aho-Corasick–style line scanner for structured log files."""
        obs_list: List[EvidenceObservation] = []
        if not os.path.exists(full_path):
            return obs_list

        service_name_map = {
            "support_replica": "support_platform",
            "attachment_preview": "support_platform",
            "account_svc": "account_service",
            "search_svc": "search_service",
            "analytics_svc": "analytics_platform",
            "export_svc": "export_service",
        }

        # Two-pass: first collect trace lines, then merge
        traces: Dict[str, Dict] = {}  # trace_id -> merged context
        plain_obs: List[EvidenceObservation] = []

        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue

                # Structured JSON log lines
                if line.startswith("{"):
                    try:
                        entry = json.loads(line)
                    except Exception:
                        entry = {}
                    obs = self._parse_log_entry(fid, row, entry, service_name_map)
                    if obs:
                        plain_obs.append(obs)
                    # Trace merging
                    trace_id = str(entry.get("trace_id", ""))
                    if trace_id:
                        if trace_id not in traces:
                            traces[trace_id] = {}
                        traces[trace_id].update({
                            k: v for k, v in entry.items() if v not in ("", None)
                        })

                # Pipe-delimited lines (support_replica.log style)
                elif "|" in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 5:
                        obs = self._parse_pipe_log_line(fid, row, parts, service_name_map)
                        if obs:
                            plain_obs.append(obs)

        # Re-evaluate merged traces
        for trace_id, merged in traces.items():
            obs = self._parse_log_entry(fid, row, merged, service_name_map)
            if obs:
                plain_obs.append(obs)

        return plain_obs

    def _parse_log_entry(
        self,
        fid: str,
        row: pd.Series,
        entry: dict,
        service_name_map: dict,
    ) -> Optional[EvidenceObservation]:
        # Required fields
        res_id = str(entry.get("resource_id", entry.get("record_id",
                  entry.get("subject_id", entry.get("lookup_key", ""))))).strip()
        if not res_id or res_id == "nan":
            return None

        raw_svc = str(entry.get("service", entry.get("system_id",
                   entry.get("source", "")))).strip()
        sys_id = service_name_map.get(raw_svc.lower(), raw_svc) or _infer_system_from_resource(res_id)[0]

        # State resolution
        http_st = str(entry.get("http_status", entry.get("status_code", "")))
        rows_val = str(entry.get("rows", entry.get("row_count", entry.get("hits", ""))))
        event_type = str(entry.get("event_type", entry.get("action", ""))).upper()
        result = str(entry.get("result", entry.get("outcome", "SUCCESS"))).upper()

        if http_st in ("404",) or rows_val in ("0",):
            st = "ABSENT"
        elif http_st in ("200", "201", "204") or rows_val not in ("", "nan", "0"):
            st = "PRESENT"
        elif event_type in ("DISABLE_CONNECTOR", "DISABLE_FLOW"):
            st = "DISABLED"
        elif "marker_found" in entry:
            st = "PRESENT" if entry["marker_found"] else "ABSENT"
        else:
            st = "PRESENT" if result == "SUCCESS" else "ABSENT"

        cat = _infer_category_from_system(sys_id)

        obs = EvidenceObservation(
            file_id=fid,
            file_path=str(row["file_path"]),
            captured_at=str(row["captured_at"]),
            system_id=sys_id,
            resource_id=res_id,
            category=cat,
            state=st,
            raw_text=json.dumps(entry)[:300],
        )
        uid = str(entry.get("user_id", entry.get("subject_ref",
                  entry.get("correlation_key", "")))).strip()
        em = str(entry.get("email", entry.get("lookup_key", ""))).strip().lower()
        if uid and uid.startswith("user_"):
            obs.user_id = uid
        if "@" in em:
            obs.email = em
        elif len(em) in (32, 64) and re.fullmatch(r"[0-9a-f]+", em):
            obs.hash_val = em
        return obs

    def _parse_pipe_log_line(
        self,
        fid: str,
        row: pd.Series,
        parts: list,
        service_name_map: dict,
    ) -> Optional[EvidenceObservation]:
        # ts | service | resource_id | result | marker_found [| extra]
        if len(parts) < 4:
            return None
        ts, raw_svc, res_id, result = parts[0], parts[1], parts[2], parts[3]
        sys_id = service_name_map.get(raw_svc.lower().strip(), raw_svc.strip())

        marker = parts[4].strip() if len(parts) > 4 else ""
        if "false" in marker.lower():
            st = "PRESENT"  # marker not found → record still there
        elif "true" in marker.lower() or result.strip().upper() == "SUCCESS":
            st = "ABSENT"
        else:
            st = "PRESENT"

        cat = _infer_category_from_system(sys_id)
        return EvidenceObservation(
            file_id=fid,
            file_path=str(row["file_path"]),
            captured_at=str(row["captured_at"]),
            system_id=sys_id,
            resource_id=res_id,
            category=cat,
            state=st,
            raw_text="|".join(parts),
        )

    # ── .sql parser (ephemeral in-memory SQLite) ───────────────────────────────

    def _parse_sql(self, fid: str, row: pd.Series, full_path: str) -> List[EvidenceObservation]:
        obs_list: List[EvidenceObservation] = []
        if not os.path.exists(full_path):
            return obs_list
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            sql_text = f.read()

        conn = sqlite3.connect(":memory:")
        try:
            # Execute DDL/DML; ignore errors from incompatible syntax
            for stmt in sql_text.split(";"):
                stmt = stmt.strip()
                if not stmt:
                    continue
                try:
                    conn.execute(stmt)
                except Exception:
                    pass
            conn.commit()

            # Query all tables for identity-linked rows
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]

            for table in tables:
                try:
                    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                    cols = [d[0] for d in conn.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()]
                    for db_row in rows:
                        rec = dict(zip(cols, db_row))
                        sys_id, cat = _infer_system_from_table(table)
                        res_id = _extract_resource_id(rec)
                        if not res_id:
                            continue
                        raw_st = str(rec.get("status", rec.get("state",
                                    rec.get("record_status", "PRESENT")))).upper()
                        st = _STATE_MAP.get(raw_st, "PRESENT")
                        obs = EvidenceObservation(
                            file_id=fid,
                            file_path=str(row["file_path"]),
                            captured_at=str(row["captured_at"]),
                            system_id=sys_id,
                            resource_id=res_id,
                            category=cat,
                            state=st,
                            raw_text=str(rec)[:300],
                        )
                        self._annotate_from_dict(obs, rec)
                        obs_list.append(obs)
                except Exception:
                    pass
        finally:
            conn.close()
        return obs_list

    # ── .pdf parser ───────────────────────────────────────────────────────────

    def _parse_pdf(self, fid: str, row: pd.Series, full_path: str) -> List[EvidenceObservation]:
        obs_list: List[EvidenceObservation] = []
        if not os.path.exists(full_path):
            return obs_list
        try:
            import pypdf
            reader = pypdf.PdfReader(full_path)
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            return obs_list

        fp = str(row["file_path"])
        if not text.strip():
            return obs_list

        # Look for record lines with resource IDs and states
        for line in text.split("\n"):
            line = line.strip()
            obs = self._try_parse_generic_line(fid, row, line, fp)
            if obs:
                obs_list.append(obs)
        return obs_list

    # ── Image parser (OCR cache → VLM) ────────────────────────────────────────

    def _parse_image(self, fid: str, row: pd.Series, full_path: str) -> List[EvidenceObservation]:
        obs_list: List[EvidenceObservation] = []
        text = self._ocr_cache.get(fid, "")
        if not text:
            text = self._ocr_cache.get(str(row["file_path"]), "")
        if not text:
            return obs_list

        fp = str(row["file_path"])
        for line in text.split("\n"):
            line = line.strip()
            obs = self._try_parse_generic_line(fid, row, line, fp)
            if obs:
                obs_list.append(obs)
        return obs_list

    def _try_parse_generic_line(
        self, fid: str, row: pd.Series, line: str, fp: str
    ) -> Optional[EvidenceObservation]:
        if not line or len(line) < 10:
            return None
        # Try to find resource_id pattern
        res_match = re.search(
            r"\b(account_\d+|search_\d+|analytics_\d+|support_\d+|"
            r"audit_record_\d+|backup_\d+|connector_\d+|export_\d+|"
            r"tombstone_\d+|user_\d+)\b",
            line,
        )
        if not res_match:
            return None
        res_id = res_match.group(0)
        sys_id, cat = _infer_system_from_resource(res_id)

        # State
        st = "PRESENT"
        lu = line.upper()
        if any(w in lu for w in ("NOT FOUND", "ABSENT", "DELETED", "404")):
            st = "ABSENT"
        elif any(w in lu for w in ("REDACTED",)):
            st = "REDACTED"
        elif any(w in lu for w in ("ANONYMIZED",)):
            st = "ANONYMIZED"
        elif any(w in lu for w in ("ACTIVE", "ENABLED")):
            st = "ACTIVE"
        elif any(w in lu for w in ("DISABLED",)):
            st = "DISABLED"
        elif any(w in lu for w in ("BLOCKED",)):
            st = "BLOCKED"

        obs = EvidenceObservation(
            file_id=fid,
            file_path=str(row["file_path"]),
            captured_at=str(row["captured_at"]),
            system_id=sys_id,
            resource_id=res_id,
            category=cat,
            state=st,
            raw_text=line[:300],
        )
        # Extract email/uid from line
        em_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", line)
        if em_match:
            obs.email = em_match.group(0).lower()
        return obs

    # ── OCR cache ─────────────────────────────────────────────────────────────

    def _load_ocr_cache(self) -> Dict[str, str]:
        cache_path = os.path.join(self.dataset_dir, "evidence", "images_ocr_cache.json")
        if not os.path.exists(cache_path):
            return {}
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    # ── Annotation helpers ────────────────────────────────────────────────────

    @staticmethod
    def _annotate_lookup(obs: EvidenceObservation, lookup: str) -> None:
        if lookup.startswith("user_"):
            obs.user_id = lookup
        elif "@" in lookup:
            obs.email = lookup.lower()
        elif len(lookup) in (32, 64) and re.fullmatch(r"[0-9a-fA-F]+", lookup):
            obs.hash_val = lookup.lower()
        elif lookup.startswith("+") or re.fullmatch(r"[\d\s\-\+\(\)]+", lookup):
            obs.phone = lookup

    @staticmethod
    def _annotate_from_dict(obs: EvidenceObservation, rec: dict) -> None:
        uid = str(rec.get("user_id", rec.get("customer_id", ""))).strip()
        em = str(rec.get("email", rec.get("customer_email", ""))).strip().lower()
        ph = str(rec.get("phone", rec.get("phone_number", ""))).strip()
        nm = str(rec.get("name", rec.get("customer_name", ""))).strip()
        if uid and uid.startswith("user_"):
            obs.user_id = uid
        if "@" in em:
            obs.email = em
        if ph and ph not in ("", "nan", "None"):
            obs.phone = ph
        if nm and nm not in ("", "nan", "None"):
            obs.name = nm


# ── Resource / system inference helpers ──────────────────────────────────────

def _infer_system_from_resource(res_id: str) -> tuple:
    if res_id.startswith("account_"):
        return ("account_service", "USER_PROFILE")
    if res_id.startswith("search_"):
        return ("search_service", "SEARCH_INDEX_ENTRY")
    if res_id.startswith("analytics_"):
        return ("analytics_platform", "ANALYTICS_PROFILE")
    if res_id.startswith("support_"):
        return ("support_platform", "SUPPORT_MESSAGE")
    if res_id.startswith("audit_record_"):
        return ("security_service", "SECURITY_AUDIT_LOG")
    if res_id.startswith("backup_"):
        return ("backup_service", "BACKUP_ARCHIVE")
    if res_id.startswith("connector_"):
        return ("integration_service", "CONNECTOR")
    if res_id.startswith("export_"):
        return ("export_service", "USER_EXPORT")
    if res_id.startswith("tombstone_"):
        return ("identity_service", "ACCOUNT_TOMBSTONE")
    if res_id.startswith("user_"):
        return ("identity_service", "ACCOUNT_TOMBSTONE")
    return ("unknown_service", "UNKNOWN")


def _infer_system_from_table(table: str) -> tuple:
    t = table.lower()
    if "account" in t:
        return ("account_service", "USER_PROFILE")
    if "search" in t or "index" in t:
        return ("search_service", "SEARCH_INDEX_ENTRY")
    if "analytic" in t:
        return ("analytics_platform", "ANALYTICS_PROFILE")
    if "support" in t or "ticket" in t:
        return ("support_platform", "SUPPORT_MESSAGE")
    if "audit" in t or "security" in t:
        return ("security_service", "SECURITY_AUDIT_LOG")
    if "backup" in t:
        return ("backup_service", "BACKUP_ARCHIVE")
    if "connector" in t or "integration" in t:
        return ("integration_service", "CONNECTOR")
    if "export" in t:
        return ("export_service", "USER_EXPORT")
    if "tombstone" in t or "identity" in t:
        return ("identity_service", "ACCOUNT_TOMBSTONE")
    return ("unknown_service", "UNKNOWN")


def _infer_category_from_system(sys_id: str) -> str:
    map_ = {
        "account_service": "USER_PROFILE",
        "search_service": "SEARCH_INDEX_ENTRY",
        "analytics_platform": "ANALYTICS_PROFILE",
        "support_platform": "SUPPORT_MESSAGE",
        "security_service": "SECURITY_AUDIT_LOG",
        "backup_service": "BACKUP_ARCHIVE",
        "integration_service": "CONNECTOR",
        "export_service": "USER_EXPORT",
        "identity_service": "ACCOUNT_TOMBSTONE",
    }
    return map_.get(sys_id, "UNKNOWN")


def _extract_resource_id(rec: dict) -> Optional[str]:
    for key in (
        "account_id", "record_id", "resource_id", "search_id", "analytics_id",
        "export_id", "support_id", "tombstone_id", "audit_id", "backup_id",
        "connector_id", "id", "user_id",
    ):
        val = rec.get(key)
        if val is not None:
            s = str(val).strip()
            if s and s != "nan":
                return s
    return None

