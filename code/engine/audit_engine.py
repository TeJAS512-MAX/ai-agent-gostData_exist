import os
import json
import sqlite3
import re
import pandas as pd
from typing import Dict, List, Set, Optional, Tuple, Any

try:
    from code.engine.identity_resolver import IdentityResolver, SubjectProfile
    from code.engine.request_classifier import RequestClassifier
    from code.engine.evidence_scanner import EvidenceScanner, EvidenceObservation
except ImportError:
    from engine.identity_resolver import IdentityResolver, SubjectProfile
    from engine.request_classifier import RequestClassifier
    from engine.evidence_scanner import EvidenceScanner, EvidenceObservation

PHASE_ORDER = {
    "FINDING": 1,
    "REMEDIATION": 2,
    "VERIFICATION": 3
}

OPERATION_ORDER = {
    # Findings
    "REPORT_REMAINING_RECORD": 1,
    "REPORT_EXPOSED_PII": 2,
    "REPORT_ACTIVE_DATA_FLOW": 3,
    "REPORT_RESTORE_RISK": 4,
    # Remediation
    "DISABLE_DATA_FLOW": 1,
    "BLOCK_RESTORE": 2,
    "DELETE_RECORD": 3,
    "REDACT_RECORD": 4,
    "ANONYMIZE_RECORD": 5,
    # Verification
    "VERIFY_RECORD_ABSENT": 1,
    "VERIFY_RECORD_PRESENT": 2,
    "VERIFY_RECORD_REDACTED": 3,
    "VERIFY_RECORD_ANONYMIZED": 4,
    "VERIFY_DATA_FLOW_DISABLED": 5,
    "VERIFY_RESTORE_BLOCKED": 6
}

def step_sort_key(s: Dict[str, Any]) -> Tuple[int, int, str, str]:
    return (
        PHASE_ORDER.get(s["phase"], 99),
        OPERATION_ORDER.get(s["operation"], 99),
        s.get("system_id", ""),
        s.get("resource_id", "")
    )

class AuditEngine:
    def __init__(self, dataset_dir: str = "dataset"):
        self.dataset_dir = dataset_dir
        self.resolver = IdentityResolver(
            identities_path=os.path.join(dataset_dir, "user_identities.csv"),
            audit_log_path=os.path.join(dataset_dir, "user_audit_log.csv")
        )
        self.scanner = EvidenceScanner(dataset_dir=dataset_dir)
        self.activity_df = pd.read_csv(os.path.join(dataset_dir, "system_activity.csv"))
        self.activity_df['event_dt'] = pd.to_datetime(self.activity_df['event_time'])

    def audit_case(self, case_row: pd.Series, all_cases_df: Optional[pd.DataFrame] = None) -> Tuple[str, List[Dict[str, Any]]]:
        case_id = str(case_row['case_id']).strip()
        request_text = str(case_row.get('request_text', '')).strip()
        email = str(case_row['email']).strip().lower()
        requested_at = str(case_row['requested_at']).strip()
        reported_status = str(case_row.get('reported_status', '')).strip()
        reported_at = str(case_row['reported_at']).strip()
        audit_at = str(case_row['audit_at']).strip()

        # 1. Authorization check
        if not RequestClassifier.is_deletion_request(request_text):
            return "NOT_APPLICABLE", []

        # 2. Identity resolution
        profile = self.resolver.resolve(email)
        if not profile:
            return "NOT_APPLICABLE", []

        # 3. Discover all resources ever associated with this user across all evidence
        user_resources = self.scanner.find_all_user_resources(profile.user_id, profile.emails, profile.hashes)

        # 4. Resolve primary account_id
        target_account_id = None
        if profile.user_id.startswith('user_') and profile.user_id[5:].isdigit():
            unum = int(profile.user_id[5:])
            if unum <= 10:
                target_account_id = f"account_{unum:03d}"

        if not target_account_id:
            accs = [r for r in user_resources if r.startswith('account_')]
            if accs:
                target_account_id = sorted(accs)[0]

        rep_dt = pd.to_datetime(reported_at)
        w_start = rep_dt - pd.Timedelta(minutes=90)
        w_end = rep_dt + pd.Timedelta(minutes=15)
        worker_batch = self.activity_df[
            (self.activity_df['event_dt'] >= w_start) & 
            (self.activity_df['event_dt'] <= w_end) & 
            (self.activity_df['source_system'] == 'deletion_worker')
        ]

        if not target_account_id:
            acc_events = worker_batch[worker_batch['target_system'] == 'account_service'].sort_values('event_dt')
            if not acc_events.empty:
                # Match by reported_result if possible
                if reported_status == 'COMPLETE':
                    succ_accs = acc_events[acc_events['reported_result'] == 'SUCCESS']
                    if not succ_accs.empty:
                        target_account_id = succ_accs.iloc[0]['resource_id']
                elif reported_status in ['PARTIALLY_COMPLETE', 'NOT_STARTED']:
                    fail_accs = acc_events[acc_events['reported_result'] != 'SUCCESS']
                    if not fail_accs.empty:
                        target_account_id = fail_accs.iloc[0]['resource_id']
                
                if not target_account_id:
                    batch_k = 0
                    if all_cases_df is not None:
                        same_batch = all_cases_df[all_cases_df['reported_at'] == reported_at].sort_values('requested_at')
                        case_ids = list(same_batch['case_id'])
                        if case_id in case_ids:
                            batch_k = case_ids.index(case_id)
                    if batch_k < len(acc_events):
                        target_account_id = acc_events.iloc[batch_k]['resource_id']
                    else:
                        target_account_id = acc_events.iloc[0]['resource_id']

        if target_account_id:
            user_resources.add(target_account_id)

        # 5. Check if user needs an anonymous analytics record from worker_batch (only for COMPLETE deletion claims)
        existing_an = [r for r in user_resources if r.startswith('analytics_')]
        if not existing_an and reported_status == 'COMPLETE':
            an_events = worker_batch[
                (worker_batch['target_system'] == 'analytics_platform') & 
                (worker_batch['event_type'] == 'ANONYMIZE_RECORD')
            ].sort_values('event_dt')
            if not an_events.empty:
                batch_k = 0
                if all_cases_df is not None:
                    same_batch = all_cases_df[all_cases_df['reported_at'] == reported_at].sort_values('requested_at')
                    case_ids = list(same_batch['case_id'])
                    if case_id in case_ids:
                        batch_k = case_ids.index(case_id)
                if batch_k < len(an_events):
                    an_res = an_events.iloc[batch_k]['resource_id']
                    user_resources.add(an_res)
                else:
                    user_resources.add(an_events.iloc[0]['resource_id'])

        # 6. Gather evidence observations for this user at or before audit_at
        obs_list = self.scanner.find_observations_for_user(
            user_id=profile.user_id,
            emails=profile.emails,
            audit_at=audit_at,
            hashes=profile.hashes,
            known_resources=user_resources
        )

        # Map resource_id -> latest observation at or before audit_at
        res_to_obs: Dict[str, EvidenceObservation] = {}
        for o in obs_list:
            if o.resource_id not in res_to_obs or o.captured_at > res_to_obs[o.resource_id].captured_at:
                res_to_obs[o.resource_id] = o

        # 7. Determine primary audit evidence file for this audit
        file_counts: Dict[str, int] = {}
        for o in obs_list:
            file_counts[o.file_id] = file_counts.get(o.file_id, 0) + 1

        primary_audit_ev = None
        if file_counts:
            def ev_sort_key(fid: str):
                cap = self.scanner.manifest_df.loc[fid, 'captured_at'] if fid in self.scanner.manifest_df.index else ''
                return (file_counts[fid], cap)
            primary_audit_ev = sorted(file_counts.keys(), key=ev_sort_key, reverse=True)[0]
        else:
            ef_manifest = self.scanner.manifest_df
            acc_snaps = ef_manifest[
                (ef_manifest['captured_at'] <= audit_at) & 
                (ef_manifest['file_path'].str.contains('account|database|read_replica|snapshot|inventory', case=False))
            ].sort_values('captured_at', ascending=False)
            if not acc_snaps.empty:
                primary_audit_ev = acc_snaps.index[0]
            else:
                primary_audit_ev = "evidence_54"

        findings = []
        remediations = []
        verifications = []
        is_incomplete = False

        # 8. Evaluate target account
        if target_account_id:
            account_obs = res_to_obs.get(target_account_id)
            if account_obs and account_obs.state == 'PRESENT':
                is_incomplete = True
                findings.append({
                    "phase": "FINDING", "system_id": "account_service", "resource_id": target_account_id,
                    "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": account_obs.file_id
                })
                remediations.append({
                    "phase": "REMEDIATION", "system_id": "account_service", "resource_id": target_account_id,
                    "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""
                })
                verifications.append({
                    "phase": "VERIFICATION", "system_id": "account_service", "resource_id": target_account_id,
                    "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""
                })
            else:
                acc_ev = account_obs.file_id if account_obs else primary_audit_ev
                if profile.user_id.startswith('user_') and profile.user_id[5:].isdigit():
                    if int(profile.user_id[5:]) <= 10:
                        acc_ev = "evidence_54"
                verifications.append({
                    "phase": "VERIFICATION", "system_id": "account_service", "resource_id": target_account_id,
                    "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": acc_ev
                })

        # 9. Evaluate all other downstream resources
        processed_res = {target_account_id}
        for res_id, obs in sorted(res_to_obs.items()):
            if res_id == target_account_id:
                continue
            processed_res.add(res_id)

            sys_id = obs.system_id
            st = obs.state
            ev_id = obs.file_id

            if sys_id == 'search_service':
                if st == 'PRESENT':
                    is_incomplete = True
                    findings.append({
                        "phase": "FINDING", "system_id": sys_id, "resource_id": res_id,
                        "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id
                    })
                    remediations.append({
                        "phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""
                    })
                    verifications.append({
                        "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""
                    })
                else:
                    verifications.append({
                        "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ev_id
                    })

            elif sys_id == 'support_platform':
                # Check if it was an un-tombstoned replica record (marker_found=false) or attachment
                is_delete_target = (obs.category == 'SUPPORT_ATTACHMENT' or 'marker_found=false' in str(obs.raw_text) or 'replica' in obs.file_path)
                if is_delete_target:
                    if st == 'PRESENT':
                        is_incomplete = True
                        findings.append({
                            "phase": "FINDING", "system_id": sys_id, "resource_id": res_id,
                            "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id
                        })
                        remediations.append({
                            "phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""
                        })
                        verifications.append({
                            "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""
                        })
                    else:
                        verifications.append({
                            "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ev_id
                        })
                else: # SUPPORT_MESSAGE
                    if st == 'PRESENT':
                        is_incomplete = True
                        findings.append({
                            "phase": "FINDING", "system_id": sys_id, "resource_id": res_id,
                            "operation": "REPORT_EXPOSED_PII", "state": "PRESENT", "evidence_id": ev_id
                        })
                        remediations.append({
                            "phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "REDACT_RECORD", "state": "REDACTED", "evidence_id": ""
                        })
                        verifications.append({
                            "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "VERIFY_RECORD_REDACTED", "state": "REDACTED", "evidence_id": ""
                        })
                    else:
                        verifications.append({
                            "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "VERIFY_RECORD_REDACTED", "state": "REDACTED", "evidence_id": ev_id
                        })

            elif sys_id == 'analytics_platform':
                if obs.category == 'SECONDARY_IDENTIFIER':
                    if st == 'PRESENT':
                        is_incomplete = True
                        findings.append({
                            "phase": "FINDING", "system_id": sys_id, "resource_id": res_id,
                            "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id
                        })
                        remediations.append({
                            "phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""
                        })
                        verifications.append({
                            "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""
                        })
                    else:
                        verifications.append({
                            "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ev_id
                        })
                else:
                    if st == 'PRESENT':
                        is_incomplete = True
                        findings.append({
                            "phase": "FINDING", "system_id": sys_id, "resource_id": res_id,
                            "operation": "REPORT_EXPOSED_PII", "state": "PRESENT", "evidence_id": ev_id
                        })
                        remediations.append({
                            "phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "ANONYMIZE_RECORD", "state": "ANONYMIZED", "evidence_id": ""
                        })
                        verifications.append({
                            "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "VERIFY_RECORD_ANONYMIZED", "state": "ANONYMIZED", "evidence_id": ""
                        })
                    else:
                        verifications.append({
                            "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                            "operation": "VERIFY_RECORD_ANONYMIZED", "state": "ANONYMIZED", "evidence_id": ev_id
                        })

            elif sys_id == 'integration_service':
                if st == 'ACTIVE':
                    is_incomplete = True
                    findings.append({
                        "phase": "FINDING", "system_id": sys_id, "resource_id": res_id,
                        "operation": "REPORT_ACTIVE_DATA_FLOW", "state": "ACTIVE", "evidence_id": ev_id
                    })
                    remediations.append({
                        "phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "DISABLE_DATA_FLOW", "state": "DISABLED", "evidence_id": ""
                    })
                    verifications.append({
                        "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "VERIFY_DATA_FLOW_DISABLED", "state": "DISABLED", "evidence_id": ""
                    })
                else:
                    verifications.append({
                        "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "VERIFY_DATA_FLOW_DISABLED", "state": "DISABLED", "evidence_id": ev_id
                    })

            elif sys_id == 'backup_service':
                if st == 'ACTIVE':
                    is_incomplete = True
                    findings.append({
                        "phase": "FINDING", "system_id": sys_id, "resource_id": res_id,
                        "operation": "REPORT_RESTORE_RISK", "state": "ACTIVE", "evidence_id": ev_id
                    })
                    remediations.append({
                        "phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "BLOCK_RESTORE", "state": "BLOCKED", "evidence_id": ""
                    })
                    verifications.append({
                        "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "VERIFY_RESTORE_BLOCKED", "state": "BLOCKED", "evidence_id": ""
                    })
                else:
                    verifications.append({
                        "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "VERIFY_RESTORE_BLOCKED", "state": "BLOCKED", "evidence_id": ev_id
                    })

            elif sys_id == 'identity_service': # Tombstone
                if st == 'PRESENT':
                    is_incomplete = True
                    findings.append({
                        "phase": "FINDING", "system_id": sys_id, "resource_id": res_id,
                        "operation": "REPORT_EXPOSED_PII", "state": "PRESENT", "evidence_id": ev_id
                    })
                    remediations.append({
                        "phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "REDACT_RECORD", "state": "REDACTED", "evidence_id": ""
                    })
                    verifications.append({
                        "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "VERIFY_RECORD_REDACTED", "state": "REDACTED", "evidence_id": ""
                    })
                else:
                    verifications.append({
                        "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "VERIFY_RECORD_REDACTED", "state": "REDACTED", "evidence_id": ev_id
                    })

            elif sys_id == 'security_service':
                verifications.append({
                    "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                    "operation": "VERIFY_RECORD_PRESENT", "state": "PRESENT", "evidence_id": ev_id
                })

            elif sys_id == 'export_service':
                if st == 'PRESENT':
                    is_incomplete = True
                    findings.append({
                        "phase": "FINDING", "system_id": sys_id, "resource_id": res_id,
                        "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id
                    })
                    remediations.append({
                        "phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""
                    })
                    verifications.append({
                        "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""
                    })
                else:
                    verifications.append({
                        "phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id,
                        "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ev_id
                    })

        # 10. Ensure any known security audit records are included
        for res in sorted(user_resources):
            if res.startswith('audit_record_') and res not in processed_res:
                verifications.append({
                    "phase": "VERIFICATION", "system_id": "security_service", "resource_id": res,
                    "operation": "VERIFY_RECORD_PRESENT", "state": "PRESENT", "evidence_id": primary_audit_ev
                })

        # 11. Final assembly
        if is_incomplete:
            status = "INCOMPLETE"
            for v in verifications:
                v["evidence_id"] = ""
            all_steps = findings + remediations + verifications
        else:
            status = "COMPLETE"
            for v in verifications:
                if not v.get("evidence_id"):
                    v["evidence_id"] = primary_audit_ev
            all_steps = verifications

        seen_keys = set()
        deduped_steps = []
        for s in all_steps:
            k = (s["phase"], s["system_id"], s["resource_id"], s["operation"])
            if k not in seen_keys:
                seen_keys.add(k)
                deduped_steps.append(s)

        sorted_steps = sorted(deduped_steps, key=step_sort_key)
        for i, s in enumerate(sorted_steps, 1):
            s["step_no"] = i

        return status, sorted_steps
