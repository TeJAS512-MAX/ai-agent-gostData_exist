import hashlib
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, Set, Dict

@dataclass
class SubjectProfile:
    user_id: str
    canonical_email: str
    emails: Set[str] = field(default_factory=set)
    phones: Set[str] = field(default_factory=set)
    names: Set[str] = field(default_factory=set)
    hashes: Set[str] = field(default_factory=set)

class IdentityResolver:
    def __init__(self, identities_path: str = "dataset/user_identities.csv", audit_log_path: str = "dataset/user_audit_log.csv"):
        self.identities_df = pd.read_csv(identities_path)
        self.audit_log_df = pd.read_csv(audit_log_path)
        self._cache: Dict[str, Optional[SubjectProfile]] = {}
        self._build_index()

    def _build_index(self):
        # Build quick lookup map: email -> user_id
        self.email_to_user_id: Dict[str, str] = {}
        for _, r in self.identities_df.iterrows():
            uid = str(r['user_id']).strip()
            em = str(r['email']).strip().lower()
            if em:
                self.email_to_user_id[em] = uid

        # Supplement with audit log historical email changes
        email_audits = self.audit_log_df[self.audit_log_df['field_name'] == 'email']
        for _, r in email_audits.iterrows():
            uid = str(r['user_id']).strip()
            old_em = str(r['old_value']).strip().lower() if pd.notna(r['old_value']) else ""
            new_em = str(r['new_value']).strip().lower() if pd.notna(r['new_value']) else ""
            if old_em and old_em not in self.email_to_user_id:
                self.email_to_user_id[old_em] = uid
            if new_em and new_em not in self.email_to_user_id:
                self.email_to_user_id[new_em] = uid

    def resolve(self, email: str) -> Optional[SubjectProfile]:
        clean_email = str(email).strip().lower()
        if clean_email in self._cache:
            return self._cache[clean_email]

        user_id = self.email_to_user_id.get(clean_email)
        if not user_id:
            self._cache[clean_email] = None
            return None

        # Fetch primary user row
        user_rows = self.identities_df[self.identities_df['user_id'] == user_id]
        if user_rows.empty:
            self._cache[clean_email] = None
            return None

        user_row = user_rows.iloc[0]
        canonical_email = str(user_row['email']).strip().lower()

        emails = {clean_email, canonical_email}
        phones = {str(user_row['phone']).strip()} if pd.notna(user_row['phone']) else set()
        names = {str(user_row['name']).strip()} if pd.notna(user_row['name']) else set()
        hashes = set()
        if pd.notna(user_row.get('email_hash')):
            hashes.add(str(user_row['email_hash']).strip())

        # Historical changes from user_audit_log
        user_audits = self.audit_log_df[self.audit_log_df['user_id'] == user_id]
        for _, a in user_audits.iterrows():
            field = str(a['field_name']).strip().lower()
            old_val = str(a['old_value']).strip() if pd.notna(a['old_value']) else ""
            new_val = str(a['new_value']).strip() if pd.notna(a['new_value']) else ""

            if field == 'email':
                if old_val:
                    emails.add(old_val.lower())
                if new_val:
                    emails.add(new_val.lower())
            elif field == 'phone':
                if old_val:
                    phones.add(old_val)
                if new_val:
                    phones.add(new_val)
            elif field == 'name':
                if old_val:
                    names.add(old_val)
                if new_val:
                    names.add(new_val)

        # Compute SHA256 for all resolved emails
        for em in list(emails):
            if em:
                h = hashlib.sha256(em.encode('utf-8')).hexdigest()
                hashes.add(h)

        profile = SubjectProfile(
            user_id=user_id,
            canonical_email=canonical_email,
            emails=emails - {''},
            phones=phones - {''},
            names=names - {''},
            hashes=hashes - {''}
        )
        self._cache[clean_email] = profile
        return profile
