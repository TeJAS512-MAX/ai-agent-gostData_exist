import os
import json
import sqlite3
import re
import pandas as pd
import pypdf
from dataclasses import dataclass
from typing import List, Dict, Set, Optional, Any

@dataclass
class EvidenceObservation:
    file_id: str
    file_path: str
    captured_at: str
    system_id: str
    resource_id: str
    category: str
    state: str  # PRESENT, ABSENT, REDACTED, ANONYMIZED, ACTIVE, DISABLED, BLOCKED
    user_id: Optional[str] = None
    email: Optional[str] = None
    hash_val: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    raw_text: Optional[str] = None

class EvidenceScanner:
    def __init__(self, dataset_dir: str = "dataset"):
        self.dataset_dir = dataset_dir
        self.manifest_path = os.path.join(dataset_dir, "evidence_files.csv")
        self.ocr_cache_path = os.path.join(dataset_dir, "evidence", "images_ocr_cache.json")
        self.manifest_df = pd.read_csv(self.manifest_path).set_index("file_id")
        self.observations: List[EvidenceObservation] = []
        self._index_all_evidence()

    def _index_all_evidence(self):
        self._index_txt_files()
        self._index_json_files()
        self._index_log_files()
        self._index_sql_files()
        self._index_pdf_files()
        self._index_image_files()

    def _index_txt_files(self):
        txt_files = self.manifest_df[self.manifest_df['file_path'].str.endswith('.txt')]
        for fid, r in txt_files.iterrows():
            full_p = os.path.join(self.dataset_dir, r['file_path'])
            if not os.path.exists(full_p):
                continue
            with open(full_p, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('- '):
                        parts = [p.strip() for p in line[2:].split('|')]
                        if len(parts) >= 6:
                            ts, sys_id, res_id, cat, raw_st, lookup = parts[:6]
                            state_map = {
                                'NOT_FOUND': 'ABSENT',
                                'FOUND': 'PRESENT',
                                'IDENTIFIABLE': 'PRESENT',
                                'ANONYMIZED': 'ANONYMIZED',
                                'REDACTED': 'REDACTED',
                                'ACTIVE': 'ACTIVE',
                                'DISABLED': 'DISABLED',
                                'BLOCKED': 'BLOCKED'
                            }
                            st = state_map.get(raw_st, 'PRESENT')
                            obs = EvidenceObservation(
                                file_id=fid,
                                file_path=r['file_path'],
                                captured_at=r['captured_at'],
                                system_id=sys_id,
                                resource_id=res_id,
                                category=cat,
                                state=st,
                                raw_text=line
                            )
                            if lookup.startswith('user_'):
                                obs.user_id = lookup
                            elif '@' in lookup:
                                obs.email = lookup.lower()
                            elif len(lookup) == 64 and all(c in '0123456789abcdefABCDEF' for c in lookup):
                                obs.hash_val = lookup.lower()
                            self.observations.append(obs)

    def _index_json_files(self):
        json_files = self.manifest_df[self.manifest_df['file_path'].str.endswith('.json')]
        for fid, r in json_files.iterrows():
            full_p = os.path.join(self.dataset_dir, r['file_path'])
            if not os.path.exists(full_p):
                continue
            with open(full_p, 'r', encoding='utf-8', errors='ignore') as f:
                try:
                    data = json.load(f)
                except Exception:
                    continue

            # Format 1: service_exports (e.g. evidence_92)
            if isinstance(data, dict) and 'service_exports' in data:
                se = data['service_exports']
                # account_service
                for item in se.get('account_service', {}).get('profile_lookups', []):
                    st = "ABSENT" if item.get('status_code') == 404 or item.get('profile') is None else "PRESENT"
                    prof = item.get('profile') or {}
                    em = prof.get('email')
                    uid = prof.get('customer_reference') or prof.get('user_id')
                    hv = prof.get('email_hash')
                    self.observations.append(EvidenceObservation(
                        file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                        system_id='account_service', resource_id=item.get('resource_id', ''),
                        category='USER_PROFILE', state=st,
                        user_id=uid, email=str(em).lower() if em else None,
                        hash_val=str(hv).lower() if hv else None
                    ))
                # analytics_platform
                for item in se.get('analytics_platform', {}).get('profiles', []):
                    has_pii = any(item.get(k) for k in ['email', 'phone', 'email_hash', 'customer_reference'])
                    st = "PRESENT" if has_pii else "ANONYMIZED"
                    obs = EvidenceObservation(
                        file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                        system_id='analytics_platform', resource_id=item.get('resource_id', ''),
                        category='ANALYTICS_PROFILE', state=st,
                        user_id=item.get('customer_reference'),
                        email=str(item.get('email')).lower() if item.get('email') else None,
                        hash_val=str(item.get('email_hash')).lower() if item.get('email_hash') else None,
                        phone=item.get('phone')
                    )
                    self.observations.append(obs)
                # backup_service
                for item in se.get('backup_service', {}).get('restore_entries', []):
                    st = "ACTIVE" if item.get('restore_allowed') else "BLOCKED"
                    obs = EvidenceObservation(
                        file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                        system_id='backup_service', resource_id=item.get('resource_id', ''),
                        category='BACKUP_ARCHIVE', state=st,
                        user_id=item.get('customer_reference'),
                        email=str(item.get('customer_email')).lower() if item.get('customer_email') else None
                    )
                    self.observations.append(obs)
                # export_service
                for item in se.get('export_service', {}).get('exports', []):
                    obs = EvidenceObservation(
                        file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                        system_id='export_service', resource_id=item.get('resource_id', ''),
                        category='USER_EXPORT', state='PRESENT',
                        user_id=item.get('customer_reference'),
                        email=str(item.get('owner_email')).lower() if item.get('owner_email') else None,
                        phone=item.get('owner_phone')
                    )
                    self.observations.append(obs)
                # integration_service
                for item in se.get('integration_service', {}).get('connectors', []):
                    st = "ACTIVE" if item.get('enabled') else "DISABLED"
                    obs = EvidenceObservation(
                        file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                        system_id='integration_service', resource_id=item.get('resource_id', ''),
                        category='DATA_FLOW', state=st,
                        user_id=item.get('customer_reference'),
                        email=str(item.get('customer_email')).lower() if item.get('customer_email') else None
                    )
                    self.observations.append(obs)
                # search_service
                for item in se.get('search_service', {}).get('index_queries', []):
                    hits = item.get('hits', {}).get('total', 0)
                    st = "PRESENT" if hits > 0 else "ABSENT"
                    q = item.get('query', '')
                    em = q.lower() if '@' in q else None
                    uid = q if q.startswith('user_') else None
                    docs = item.get('hits', {}).get('documents', [])
                    for doc in docs:
                        if doc.get('email'):
                            em = str(doc.get('email')).lower()
                        if doc.get('customer_reference'):
                            uid = doc.get('customer_reference')
                    obs = EvidenceObservation(
                        file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                        system_id='search_service', resource_id=item.get('resource_id', ''),
                        category='SEARCH_INDEX_ENTRY', state=st,
                        user_id=uid, email=em
                    )
                    self.observations.append(obs)
                # security_service
                for item in se.get('security_service', {}).get('audit_records', []):
                    obs = EvidenceObservation(
                        file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                        system_id='security_service', resource_id=item.get('resource_id', ''),
                        category='SECURITY_AUDIT_LOG', state='PRESENT',
                        user_id=item.get('subject_reference') or item.get('user_id')
                    )
                    self.observations.append(obs)
                # support_platform
                for item in se.get('support_platform', {}).get('tickets', []):
                    has_pii = any(item.get(k) for k in ['requester_email', 'requester_name', 'requester_phone'])
                    st = "PRESENT" if has_pii else "REDACTED"
                    obs = EvidenceObservation(
                        file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                        system_id='support_platform', resource_id=item.get('resource_id', ''),
                        category='SUPPORT_MESSAGE', state=st,
                        user_id=item.get('customer_reference') or item.get('subject_reference'),
                        email=str(item.get('requester_email')).lower() if item.get('requester_email') else None,
                        name=item.get('requester_name'),
                        phone=item.get('requester_phone')
                    )
                    self.observations.append(obs)

            # Format 2: snapshot_bundle (e.g. evidence_51, evidence_02)
            elif isinstance(data, dict) and 'snapshots' in data:
                for snap in data['snapshots']:
                    store = snap.get('data_store', '')
                    recs = snap.get('records', [])
                    for rec in recs:
                        res_id = rec.get('resource_id', '')
                        uid = rec.get('user_id') or rec.get('customer_reference') or rec.get('subject_reference') or rec.get('subject_selector')
                        em = rec.get('email') or rec.get('owner_email') or rec.get('requester_email') or rec.get('customer_email')
                        hv = rec.get('email_hash')
                        
                        doc = rec.get('document') or {}
                        if doc:
                            uid = uid or doc.get('customer_reference')
                            em = em or doc.get('email')
                            hv = hv or doc.get('email_hash')

                        clean_em = str(em).lower() if em else None
                        clean_hv = str(hv).lower() if hv else None

                        if store == 'account_service':
                            status = rec.get('account_status') or rec.get('status')
                            st = 'ABSENT' if status in ['DELETED', 'ABSENT'] else 'PRESENT'
                            self.observations.append(EvidenceObservation(
                                file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                                system_id='account_service', resource_id=res_id,
                                category='USER_PROFILE', state=st,
                                user_id=uid, email=clean_em, hash_val=clean_hv,
                                name=rec.get('full_name') or rec.get('name')
                            ))
                        elif store == 'identity_service':
                            has_pii = any(rec.get(k) for k in ['name', 'email', 'phone', 'email_hash'])
                            st = "PRESENT" if has_pii else "REDACTED"
                            self.observations.append(EvidenceObservation(
                                file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                                system_id='identity_service', resource_id=res_id,
                                category='ACCOUNT_TOMBSTONE', state=st,
                                user_id=uid, email=clean_em, hash_val=clean_hv,
                                name=rec.get('name'), phone=rec.get('phone')
                            ))
                        elif store == 'security_service':
                            self.observations.append(EvidenceObservation(
                                file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                                system_id='security_service', resource_id=res_id,
                                category='SECURITY_AUDIT_LOG', state='PRESENT',
                                user_id=uid, email=clean_em, hash_val=clean_hv
                            ))
                        elif store == 'analytics_platform':
                            has_pii = any(rec.get(k) for k in ['name', 'email', 'phone', 'email_hash', 'user_id', 'customer_reference'])
                            st = "PRESENT" if has_pii else "ANONYMIZED"
                            self.observations.append(EvidenceObservation(
                                file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                                system_id='analytics_platform', resource_id=res_id,
                                category='ANALYTICS_PROFILE', state=st,
                                user_id=uid, email=clean_em, hash_val=clean_hv
                            ))
                        elif store == 'search_service':
                            self.observations.append(EvidenceObservation(
                                file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                                system_id='search_service', resource_id=res_id,
                                category='SEARCH_INDEX_ENTRY', state='PRESENT',
                                user_id=uid, email=clean_em, hash_val=clean_hv
                            ))
                        elif store == 'support_platform':
                            msg_txt = str(rec.get('message_text', ''))
                            has_pii = any(rec.get(k) for k in ['requester_email', 'requester_name', 'requester_phone'])
                            if not has_pii and ('@' in msg_txt and '[REDACTED]' not in msg_txt):
                                has_pii = True
                            st = "PRESENT" if has_pii else "REDACTED"
                            self.observations.append(EvidenceObservation(
                                file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                                system_id='support_platform', resource_id=res_id,
                                category='SUPPORT_MESSAGE', state=st,
                                user_id=uid, email=clean_em, hash_val=clean_hv
                            ))
                        elif store == 'backup_service':
                            rest_allowed = rec.get('restore_allowed')
                            st = 'ACTIVE' if rest_allowed in [True, 'True', 1, '1'] else 'BLOCKED'
                            self.observations.append(EvidenceObservation(
                                file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                                system_id='backup_service', resource_id=res_id,
                                category='BACKUP_ARCHIVE', state=st,
                                user_id=uid, email=clean_em, hash_val=clean_hv
                            ))
                        elif store == 'integration_service':
                            enabled = rec.get('enabled')
                            st = 'ACTIVE' if enabled in [True, 'True', 1, '1'] else 'DISABLED'
                            self.observations.append(EvidenceObservation(
                                file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                                system_id='integration_service', resource_id=res_id,
                                category='DATA_FLOW', state=st,
                                user_id=uid, email=clean_em, hash_val=clean_hv
                            ))

            # Format 3: customer_export_jobs_*.json
            elif 'export' in r['file_path'].lower():
                items = data.get('jobs') or data.get('exports') or data.get('records') or []
                for item in items:
                    self.observations.append(EvidenceObservation(
                        file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                        system_id='export_service', resource_id=item.get('resource_id', ''),
                        category='USER_EXPORT', state='PRESENT',
                        user_id=item.get('customer_reference') or item.get('user_id'),
                        email=str(item.get('owner_email') or item.get('email')).lower() if (item.get('owner_email') or item.get('email')) else None
                    ))

            # Format 4: customer_analytics_report_*.json (e.g. evidence_56)
            elif 'analytics' in r['file_path'].lower():
                recs = data.get('records', [])
                for rec in recs:
                    has_pii = any(rec.get(k) for k in ['name', 'email', 'phone', 'email_hash', 'user_id', 'customer_reference'])
                    st = "PRESENT" if has_pii else "ANONYMIZED"
                    self.observations.append(EvidenceObservation(
                        file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                        system_id='analytics_platform', resource_id=rec.get('resource_id', ''),
                        category='ANALYTICS_PROFILE', state=st,
                        user_id=rec.get('user_id') or rec.get('customer_reference'),
                        email=str(rec.get('email')).lower() if rec.get('email') else None,
                        hash_val=str(rec.get('email_hash')).lower() if rec.get('email_hash') else None
                    ))

    def _index_log_files(self):
        log_files = self.manifest_df[self.manifest_df['file_path'].str.endswith('.log')]
        for fid, r in log_files.iterrows():
            full_p = os.path.join(self.dataset_dir, r['file_path'])
            if not os.path.exists(full_p):
                continue
            with open(full_p, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            traces: Dict[str, Dict[str, Any]] = {}
            untraced_lines = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if line.startswith('{') and line.endswith('}'):
                    try:
                        kv = json.loads(line)
                    except Exception:
                        kv = dict(re.findall(r'(\w+)=["\']?([^"\'\s]+)["\']?', line))
                else:
                    kv = dict(re.findall(r'(\w+)=["\']?([^"\'\s]+)["\']?', line))

                tr = kv.get('trace_id')
                if tr:
                    if tr not in traces:
                        traces[tr] = {}
                    traces[tr].update(kv)
                else:
                    untraced_lines.append(kv)

            for tr, tr_dict in traces.items():
                self._create_log_observation(fid, r, tr_dict)

            for kv in untraced_lines:
                self._create_log_observation(fid, r, kv)

    def _create_log_observation(self, fid: str, r: pd.Series, kv: Dict[str, Any]):
        res_id = kv.get('resource_id')
        svc = kv.get('service') or kv.get('system')
        evt = str(kv.get('event', '')).lower()

        if not res_id:
            m = re.search(r'(account_\d+|search_\d+|support_\d+|analytics_\d+|backup_\d+|data_flow_\d+|audit_record_\d+|tombstone_\d+|export_\d+)', str(kv))
            if m:
                res_id = m.group(1)

        if not res_id:
            return

        # Canonicalize service names
        if svc in ['support_replica', 'attachment_preview']:
            svc = 'support_platform'
        elif svc == 'search_index_service':
            svc = 'search_service'

        if not svc or svc in ['readback_collector', 'log_router']:
            if res_id.startswith('account_'):
                svc = 'account_service'
            elif res_id.startswith('search_'):
                svc = 'search_service'
            elif res_id.startswith('support_'):
                svc = 'support_platform'
            elif res_id.startswith('analytics_'):
                svc = 'analytics_platform'
            elif res_id.startswith('backup_'):
                svc = 'backup_service'
            elif res_id.startswith('data_flow_'):
                svc = 'integration_service'
            elif res_id.startswith('audit_record_'):
                svc = 'security_service'
            elif res_id.startswith('tombstone_'):
                svc = 'identity_service'
            elif res_id.startswith('export_'):
                svc = 'export_service'

        cat_map = {
            'account_service': 'USER_PROFILE',
            'search_service': 'SEARCH_INDEX_ENTRY',
            'support_platform': 'SUPPORT_MESSAGE',
            'analytics_platform': 'ANALYTICS_PROFILE',
            'backup_service': 'BACKUP_ARCHIVE',
            'integration_service': 'DATA_FLOW',
            'security_service': 'SECURITY_AUDIT_LOG',
            'identity_service': 'ACCOUNT_TOMBSTONE',
            'export_service': 'USER_EXPORT'
        }
        cat = cat_map.get(svc, 'USER_PROFILE')

        st = "PRESENT"
        if svc == 'account_service':
            if str(kv.get('http_status')) == '404' or str(kv.get('rows')) == '0' or 'not_found' in evt:
                st = 'ABSENT'
            else:
                st = 'PRESENT'
        elif svc == 'search_service':
            hits = kv.get('total_hits') or kv.get('hits') or ('1' if kv.get('result') == 'hit' else ('0' if kv.get('result') == 'miss' else None))
            if hits in ['0', 0, 'null', 'None'] or kv.get('result') == 'miss':
                st = 'ABSENT'
            else:
                st = 'PRESENT'
        elif svc == 'analytics_platform':
            # Contact lookups (secondary identifiers / marketing profiles) that returned rows
            if 'contact_lookup' in evt and (str(kv.get('rows')) not in ['0', 'None', 'null'] or kv.get('email_opt_in') in ['true', True, 1]):
                st = 'PRESENT'
                cat = 'SECONDARY_IDENTIFIER'
            else:
                has_pii = any(kv.get(k) and kv.get(k) not in ['null', 'None'] for k in ['email', 'phone', 'email_hash', 'customer_reference'])
                st = 'PRESENT' if has_pii else 'ANONYMIZED'
        elif svc == 'support_platform':
            if str(kv.get('marker_found')) == 'false' or evt == 'message_pii_scan' or (kv.get('rows') and str(kv.get('rows')) not in ['0', 'null', 'None']):
                st = 'PRESENT'
            else:
                has_pii = any(kv.get(k) and kv.get(k) not in ['null', 'None'] for k in ['requester_email', 'requester_name', 'requester_phone'])
                st = 'PRESENT' if has_pii else 'REDACTED'
        elif svc == 'backup_service':
            rest_allowed = kv.get('restore_allowed') or kv.get('eligible')
            del_block = kv.get('deletion_block')
            if rest_allowed in ['true', True, '1', 1] or del_block in ['false', False, '0', 0]:
                st = 'ACTIVE'
            else:
                st = 'BLOCKED'
        elif svc == 'integration_service':
            enabled = kv.get('enabled')
            st = 'ACTIVE' if enabled in ['true', True, '1', 1] else 'DISABLED'
        elif svc == 'security_service':
            st = 'PRESENT'

        local_uid = kv.get('subject_reference') or kv.get('customer_reference') or kv.get('user_id')
        local_em = kv.get('lookup_key') or kv.get('subject_key') or kv.get('email') or kv.get('requester_email') or kv.get('customer_email') or kv.get('matched_value')
        local_hv = kv.get('email_hash')

        corr = kv.get('correlation_key')
        if corr and corr not in ['null', 'None']:
            if corr.startswith('user_'):
                local_uid = corr
            elif '@' in corr:
                local_em = corr
            elif len(corr) == 64 and all(c in '0123456789abcdefABCDEF' for c in corr):
                local_hv = corr

        if local_em and not ('@' in local_em):
            if local_em.startswith('user_'):
                local_uid = local_em
                local_em = None
            elif len(local_em) == 64 and all(c in '0123456789abcdefABCDEF' for c in local_em):
                local_hv = local_em
                local_em = None

        clean_em = str(local_em).lower() if local_em and local_em not in ['null', 'None'] else None
        clean_uid = str(local_uid) if local_uid and local_uid not in ['null', 'None'] else None
        clean_hv = str(local_hv).lower() if local_hv and local_hv not in ['null', 'None'] else None

        self.observations.append(EvidenceObservation(
            file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
            system_id=svc, resource_id=res_id, category=cat, state=st,
            user_id=clean_uid,
            email=clean_em,
            hash_val=clean_hv
        ))

    def _index_sql_files(self):
        sql_files = self.manifest_df[self.manifest_df['file_path'].str.endswith('.sql')]
        for fid, r in sql_files.iterrows():
            full_p = os.path.join(self.dataset_dir, r['file_path'])
            if not os.path.exists(full_p):
                continue
            with open(full_p, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            conn = sqlite3.connect(':memory:')
            try:
                conn.executescript(content)
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [t[0] for t in cur.fetchall()]

                # 1. Failover replica check
                if 'customer_profiles_failover_replica' in tables:
                    cur.execute("SELECT resource_id, user_id, full_name, email, phone, account_status FROM customer_profiles_failover_replica")
                    for row in cur.fetchall():
                        res_id, uid, fn, em, ph, st = row
                        self.observations.append(EvidenceObservation(
                            file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                            system_id='account_service', resource_id=res_id, category='USER_PROFILE',
                            state='PRESENT', user_id=uid, email=em.lower() if em else None,
                            name=fn, phone=ph
                        ))

                # 2. Search documents primary (evidence_57)
                if 'search_documents_primary' in tables:
                    cur.execute("PRAGMA table_info(search_documents_primary)")
                    cols = [c[1] for c in cur.fetchall()]
                    cur.execute("SELECT * FROM search_documents_primary")
                    for row in cur.fetchall():
                        rd = dict(zip(cols, row))
                        self.observations.append(EvidenceObservation(
                            file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                            system_id='search_service', resource_id=rd.get('resource_id', ''),
                            category='SEARCH_INDEX_ENTRY', state='PRESENT',
                            email=str(rd.get('email')).lower() if rd.get('email') else None,
                            name=rd.get('display_name')
                        ))

                # 3. Security audit records
                if 'security_audit_records' in tables:
                    cur.execute("PRAGMA table_info(security_audit_records)")
                    cols = [c[1] for c in cur.fetchall()]
                    cur.execute("SELECT * FROM security_audit_records")
                    for row in cur.fetchall():
                        rd = dict(zip(cols, row))
                        self.observations.append(EvidenceObservation(
                            file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                            system_id='security_service', resource_id=rd.get('resource_id', ''),
                            category='SECURITY_AUDIT_LOG', state='PRESENT',
                            user_id=rd.get('subject_reference') or rd.get('user_id')
                        ))

                # 4. Backup restore entries
                if 'backup_restore_entries' in tables:
                    cur.execute("PRAGMA table_info(backup_restore_entries)")
                    cols = [c[1] for c in cur.fetchall()]
                    cur.execute("SELECT * FROM backup_restore_entries")
                    for row in cur.fetchall():
                        rd = dict(zip(cols, row))
                        st = 'ACTIVE' if str(rd.get('restore_allowed')) in ['1', 'true', 'True'] else 'BLOCKED'
                        self.observations.append(EvidenceObservation(
                            file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                            system_id='backup_service', resource_id=rd.get('resource_id', ''),
                            category='BACKUP_ARCHIVE', state=st,
                            user_id=rd.get('customer_reference') or rd.get('user_id'),
                            email=str(rd.get('customer_email')).lower() if rd.get('customer_email') else None
                        ))

                # 5. Customer data primary / read replica / reporting replica
                for tbl in ['customer_data_primary', 'customer_data_read_replica', 'customer_data_reporting_replica']:
                    if tbl in tables:
                        cur.execute(f"PRAGMA table_info({tbl})")
                        cols = [c[1] for c in cur.fetchall()]
                        json_col = 'record_json' if 'record_json' in cols else ('details' if 'details' in cols else None)
                        if 'resource_id' in cols and json_col:
                            cur.execute(f"SELECT resource_id, origin_system, collection_name, {json_col} FROM {tbl}")
                            for row in cur.fetchall():
                                res_id, sys_id, coll, det = row
                                em = None
                                uid = None
                                hv = None
                                has_pii = False
                                if det:
                                    try:
                                        det_j = json.loads(det) if isinstance(det, str) else det
                                        em = det_j.get('email') or det_j.get('requester_email') or det_j.get('customer_email')
                                        uid = det_j.get('user_id') or det_j.get('subject_reference') or det_j.get('customer_reference')
                                        hv = det_j.get('email_hash')
                                        doc = det_j.get('document')
                                        if isinstance(doc, dict):
                                            em = em or doc.get('email')
                                            uid = uid or doc.get('customer_reference') or doc.get('user_id')
                                            hv = hv or doc.get('email_hash')
                                        has_pii = any(det_j.get(k) for k in ['email', 'phone', 'email_hash', 'requester_email', 'display_name'])
                                    except:
                                        pass

                                st = 'PRESENT'
                                if sys_id == 'analytics_platform':
                                    st = 'PRESENT' if has_pii else 'ANONYMIZED'
                                elif sys_id == 'support_platform':
                                    st = 'PRESENT' if has_pii else 'REDACTED'
                                elif sys_id == 'account_service':
                                    st = 'PRESENT'

                                self.observations.append(EvidenceObservation(
                                    file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                                    system_id=sys_id, resource_id=res_id, category=coll,
                                    state=st, user_id=uid, email=em.lower() if em else None,
                                    hash_val=hv.lower() if hv else None
                                ))
            except Exception:
                pass
            finally:
                conn.close()

    def _index_pdf_files(self):
        pdf_files = self.manifest_df[self.manifest_df['file_path'].str.endswith('.pdf')]
        for fid, r in pdf_files.iterrows():
            full_p = os.path.join(self.dataset_dir, r['file_path'])
            if not os.path.exists(full_p):
                continue
            try:
                reader = pypdf.PdfReader(full_p)
                text = " ".join([page.extract_text() or "" for page in reader.pages])
                res_matches = re.findall(r'(support_\d+|account_\d+|audit_record_\d+|legal_hold_\d+)', text)
                em_matches = re.findall(r'[\w\.-]+@[\w\.-]+', text)
                user_matches = re.findall(r'user_\d+', text)
                
                for res in set(res_matches):
                    svc = 'support_platform' if res.startswith('support_') else ('security_service' if res.startswith('audit_record_') else 'account_service')
                    cat = 'SUPPORT_ATTACHMENT' if res.startswith('support_') else ('SECURITY_AUDIT_LOG' if res.startswith('audit_record_') else 'USER_PROFILE')
                    self.observations.append(EvidenceObservation(
                        file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                        system_id=svc, resource_id=res, category=cat, state='PRESENT',
                        user_id=user_matches[0] if user_matches else None,
                        email=em_matches[0].lower() if em_matches else None,
                        raw_text=text[:300]
                    ))
            except Exception:
                pass

    def _index_image_files(self):
        if not os.path.exists(self.ocr_cache_path):
            return
        with open(self.ocr_cache_path, 'r', encoding='utf-8') as f:
            ocr_cache = json.load(f)

        img_files = self.manifest_df[self.manifest_df['file_path'].str.endswith('.png')]
        for fid, r in img_files.iterrows():
            fname = os.path.basename(r['file_path'])
            text = ocr_cache.get(fname, "")
            if not text:
                continue
            
            res_matches = re.findall(r'(account_\d+|search_\d+|support_\d+|analytics_\d+|backup_\d+|data_flow_\d+|audit_record_\d+|tombstone_\d+|export_\d+)', text)
            em_matches = re.findall(r'[\w\.-]+@[\w\.-]+', text)
            user_matches = re.findall(r'user_\d+', text)

            for res in set(res_matches):
                if res.startswith('account_'):
                    svc = 'account_service'
                    cat = 'USER_PROFILE'
                elif res.startswith('search_'):
                    svc = 'search_service'
                    cat = 'SEARCH_INDEX_ENTRY'
                elif res.startswith('support_'):
                    svc = 'support_platform'
                    cat = 'SUPPORT_MESSAGE'
                elif res.startswith('analytics_'):
                    svc = 'analytics_platform'
                    cat = 'ANALYTICS_PROFILE'
                elif res.startswith('backup_'):
                    svc = 'backup_service'
                    cat = 'BACKUP_ARCHIVE'
                elif res.startswith('data_flow_'):
                    svc = 'integration_service'
                    cat = 'DATA_FLOW'
                elif res.startswith('audit_record_'):
                    svc = 'security_service'
                    cat = 'SECURITY_AUDIT_LOG'
                elif res.startswith('tombstone_'):
                    svc = 'identity_service'
                    cat = 'ACCOUNT_TOMBSTONE'
                elif res.startswith('export_'):
                    svc = 'export_service'
                    cat = 'USER_EXPORT'
                else:
                    svc = 'account_service'
                    cat = 'USER_PROFILE'

                self.observations.append(EvidenceObservation(
                    file_id=fid, file_path=r['file_path'], captured_at=r['captured_at'],
                    system_id=svc, resource_id=res, category=cat, state='PRESENT',
                    user_id=user_matches[0] if user_matches else None,
                    email=em_matches[0].lower() if em_matches else None,
                    raw_text=text[:300]
                ))

    def find_all_user_resources(self, user_id: str, emails: Set[str], hashes: Optional[Set[str]] = None) -> Set[str]:
        """Discovers all resource IDs ever associated with this user across all evidence."""
        res_set = set()
        clean_emails = {e.lower() for e in emails if e}
        clean_hashes = {h.lower() for h in hashes if h} if hashes else set()
        for obs in self.observations:
            if obs.user_id and obs.user_id == user_id:
                res_set.add(obs.resource_id)
            elif obs.email and obs.email.lower() in clean_emails:
                res_set.add(obs.resource_id)
            elif obs.hash_val and obs.hash_val.lower() in clean_hashes:
                res_set.add(obs.resource_id)
        return res_set

    def find_observations_for_user(self, user_id: str, emails: Set[str], audit_at: str, hashes: Optional[Set[str]] = None, known_resources: Optional[Set[str]] = None) -> List[EvidenceObservation]:
        results = []
        clean_emails = {e.lower() for e in emails if e}
        clean_hashes = {h.lower() for h in hashes if h} if hashes else set()
        for obs in self.observations:
            if obs.captured_at > audit_at:
                continue

            matches = False
            # If observation explicitly declares a user_id or email or hash, it MUST match this user
            if obs.user_id:
                if obs.user_id == user_id:
                    matches = True
            elif obs.email:
                if obs.email.lower() in clean_emails:
                    matches = True
            elif obs.hash_val:
                if obs.hash_val.lower() in clean_hashes:
                    matches = True
            elif known_resources and obs.resource_id in known_resources:
                matches = True

            if matches:
                results.append(obs)

        return results
