"""
Stage 2: Transitive Identity Closure via Union-Find
====================================================
Builds an immutable IdentityFootprint (𝓘ᵤ) for each deletion subject by
performing transitive closure across user_identities.csv and user_audit_log.csv
using a Union-Find (Disjoint-Set Union) data structure.

Outputs:
  IdentityFootprint
    .user_id          – canonical internal stable key (tombstone-safe)
    .emails           – all known email addresses (prohibited PII)
    .phones           – all known phone numbers (prohibited PII)
    .names            – all known full names (prohibited PII)
    .hashes           – SHA-256 and MD5 of every email/phone (prohibited PII)
    .permitted_keys   – {user_id} — the only keys allowed in tombstone records
"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

import pandas as pd

logger = logging.getLogger(__name__)


# ── Union-Find ────────────────────────────────────────────────────────────────

class UnionFind:
    def __init__(self):
        self._parent: Dict[str, str] = {}
        self._rank: Dict[str, int] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0
            return x
        # Cycle-proof path compression traversal (prevents infinite loops on cyclic data)
        visited = set()
        curr = x
        while self._parent[curr] != curr:
            if curr in visited:
                # Self-healing: break cycle
                self._parent[curr] = curr
                break
            visited.add(curr)
            self._parent[curr] = self._parent[self._parent[curr]]
            curr = self._parent[curr]
        return curr

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank.get(ra, 0) < self._rank.get(rb, 0):
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank.get(ra, 0) == self._rank.get(rb, 0):
            self._rank[ra] = self._rank.get(ra, 0) + 1


# ── IdentityFootprint ─────────────────────────────────────────────────────────

@dataclass
class IdentityFootprint:
    user_id: str
    canonical_email: str
    emails: Set[str] = field(default_factory=set)
    phones: Set[str] = field(default_factory=set)
    names: Set[str] = field(default_factory=set)
    hashes: Set[str] = field(default_factory=set)

    @property
    def permitted_keys(self) -> Set[str]:
        """Keys allowed in tombstone / retained records (internal stable ref only)."""
        return {self.user_id}

    @property
    def prohibited_pii_tokens(self) -> Set[str]:
        """All tokens that must NOT appear in any post-deletion retained record."""
        return self.emails | self.phones | self.names | self.hashes

    def all_identifiers(self) -> Set[str]:
        """Union of all identity tokens for evidence scanning."""
        return {self.user_id} | self.emails | self.phones | self.names | self.hashes


# ── IdentityGraph ─────────────────────────────────────────────────────────────

class IdentityGraph:
    """
    Stage 2: Transitive Identity Closure engine.

    Usage:
        graph = IdentityGraph(dataset_dir="dataset")
        footprint = graph.resolve("user@example.com")
    """

    def __init__(self, dataset_dir: str = "dataset"):
        import os
        self._identities = pd.read_csv(
            os.path.join(dataset_dir, "user_identities.csv")
        )
        self._audit_log = pd.read_csv(
            os.path.join(dataset_dir, "user_audit_log.csv")
        )
        self._uf = UnionFind()
        self._email_to_uid: Dict[str, str] = {}
        self._uid_to_rows: Dict[str, list] = {}
        self._cache: Dict[str, Optional[IdentityFootprint]] = {}
        self._build()

    # ── Build phase ──────────────────────────────────────────────────────────

    def _build(self) -> None:
        """Populate Union-Find and email→uid index from identity + audit tables."""
        # Primary identities
        for _, row in self._identities.iterrows():
            uid = str(row["user_id"]).strip()
            em = str(row.get("email", "")).strip().lower()
            if em and em != "nan":
                self._uf.union(uid, em)
                self._email_to_uid[em] = uid
            if uid not in self._uid_to_rows:
                self._uid_to_rows[uid] = []
            self._uid_to_rows[uid].append(row)

        # Historical identity mutations from audit log
        email_rows = self._audit_log[self._audit_log["field_name"] == "email"]
        for _, row in email_rows.iterrows():
            uid = str(row["user_id"]).strip()
            for col in ("old_value", "new_value"):
                val = str(row.get(col, "")).strip().lower()
                if val and val != "nan":
                    self._uf.union(uid, val)
                    if val not in self._email_to_uid:
                        self._email_to_uid[val] = uid

    # ── Crypto hash helpers ──────────────────────────────────────────────────

    @staticmethod
    def _sha256(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    @staticmethod
    def _md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    def _compute_hashes(self, tokens: Set[str]) -> Set[str]:
        hashes: Set[str] = set()
        for t in tokens:
            if t:
                hashes.add(self._sha256(t))
                hashes.add(self._md5(t))
        return hashes

    # ── Resolve ───────────────────────────────────────────────────────────────

    def resolve(self, seed_email: str) -> Optional[IdentityFootprint]:
        """
        Compute the transitive IdentityFootprint for the given seed email.
        Returns None if the email is unknown.
        """
        key = seed_email.strip().lower()
        if key in self._cache:
            return self._cache[key]

        uid = self._email_to_uid.get(key)
        if not uid:
            # Try resolving via Union-Find root (handles historical email aliases)
            root = self._uf.find(key)
            uid = self._email_to_uid.get(root)
        if not uid:
            self._cache[key] = None
            return None

        # Gather identity rows for this uid
        rows = self._uid_to_rows.get(uid, [])
        if not rows:
            user_rows = self._identities[self._identities["user_id"] == uid]
            rows = [r for _, r in user_rows.iterrows()]

        emails: Set[str] = {key}
        phones: Set[str] = set()
        names: Set[str] = set()
        canonical_email = key

        for r in rows:
            em = str(r.get("email", "")).strip().lower()
            if em and em != "nan":
                emails.add(em)
                canonical_email = em
            ph = str(r.get("phone", "")).strip()
            if ph and ph != "nan":
                phones.add(ph)
            nm = str(r.get("name", "")).strip()
            if nm and nm != "nan":
                names.add(nm)
            eh = str(r.get("email_hash", "")).strip()
            # Stored email_hash values are collected into hashes below, not emails

        # Historical mutations
        user_audits = self._audit_log[self._audit_log["user_id"] == uid]
        for _, a in user_audits.iterrows():
            fn = str(a.get("field_name", "")).strip().lower()
            old = str(a.get("old_value", "")).strip()
            new = str(a.get("new_value", "")).strip()
            if fn == "email":
                if old and old != "nan":
                    emails.add(old.lower())
                if new and new != "nan":
                    emails.add(new.lower())
            elif fn == "phone":
                if old and old != "nan":
                    phones.add(old)
                if new and new != "nan":
                    phones.add(new)
            elif fn == "name":
                if old and old != "nan":
                    names.add(old)
                if new and new != "nan":
                    names.add(new)

        # Collect stored email_hash values from identity rows
        stored_hashes: Set[str] = set()
        for r in rows:
            eh = str(r.get("email_hash", "")).strip()
            if eh and eh != "nan" and len(eh) >= 32:
                stored_hashes.add(eh.lower())

        # Compute cryptographic hashes for all emails and phones
        hashes = stored_hashes | self._compute_hashes(emails) | self._compute_hashes(phones)

        footprint = IdentityFootprint(
            user_id=uid,
            canonical_email=canonical_email,
            emails=emails - {"", "nan"},
            phones=phones - {"", "nan"},
            names=names - {"", "nan"},
            hashes=hashes - {"", "nan"},
        )
        self._cache[key] = footprint
        logger.debug("Stage 2: Resolved %s → %s (%d emails, %d hashes)",
                     key, uid, len(footprint.emails), len(footprint.hashes))
        return footprint

