"""Validate the submission CSV against the public output contract."""

import argparse
import csv
import json
import os
import sys
from pathlib import Path


STEP_FIELDS = {
    "step_no",
    "phase",
    "system_id",
    "resource_id",
    "operation",
    "state",
    "evidence_id",
}
PHASE_RANK = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
OPERATION_RANK = {
    "REPORT_REMAINING_RECORD": 0,
    "REPORT_EXPOSED_PII": 1,
    "REPORT_ACTIVE_DATA_FLOW": 2,
    "REPORT_RESTORE_RISK": 3,
    "DISABLE_DATA_FLOW": 0,
    "BLOCK_RESTORE": 1,
    "DELETE_RECORD": 2,
    "REDACT_RECORD": 3,
    "ANONYMIZE_RECORD": 4,
    "VERIFY_RECORD_ABSENT": 0,
    "VERIFY_RECORD_PRESENT": 1,
    "VERIFY_RECORD_REDACTED": 2,
    "VERIFY_RECORD_ANONYMIZED": 3,
    "VERIFY_DATA_FLOW_DISABLED": 4,
    "VERIFY_RESTORE_BLOCKED": 5,
}
OPERATION_PHASE = {
    **dict.fromkeys(
        (
            "REPORT_REMAINING_RECORD",
            "REPORT_EXPOSED_PII",
            "REPORT_ACTIVE_DATA_FLOW",
            "REPORT_RESTORE_RISK",
        ),
        "FINDING",
    ),
    **dict.fromkeys(
        (
            "DISABLE_DATA_FLOW",
            "BLOCK_RESTORE",
            "DELETE_RECORD",
            "REDACT_RECORD",
            "ANONYMIZE_RECORD",
        ),
        "REMEDIATION",
    ),
    **dict.fromkeys(
        (
            "VERIFY_RECORD_ABSENT",
            "VERIFY_RECORD_PRESENT",
            "VERIFY_RECORD_REDACTED",
            "VERIFY_RECORD_ANONYMIZED",
            "VERIFY_DATA_FLOW_DISABLED",
            "VERIFY_RESTORE_BLOCKED",
        ),
        "VERIFICATION",
    ),
}
OPERATION_STATE = {
    "REPORT_REMAINING_RECORD": "PRESENT",
    "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
    "REPORT_RESTORE_RISK": "ACTIVE",
    "DISABLE_DATA_FLOW": "DISABLED",
    "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED",
    "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT",
    "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        return list(csv.DictReader(source))


def validate(input_path: Path, output_path: Path) -> list[str]:
    requests = _load_rows(input_path)
    output = _load_rows(output_path)
    errors: list[str] = []

    expected_header = ["case_id", "deletion_status", "steps_json"]
    with output_path.open(newline="", encoding="utf-8-sig") as source:
        header = next(csv.reader(source), [])
    if header != expected_header:
        errors.append(f"Header must be {expected_header!r}, got {header!r}")

    expected_ids = sorted(row["case_id"] for row in requests)
    actual_ids = [row.get("case_id", "") for row in output]
    if actual_ids != expected_ids:
        errors.append("Output case IDs must match inputs exactly once and be sorted lexicographically")

    for row in output:
        case_id = row.get("case_id", "<missing case_id>")
        status = row.get("deletion_status", "")
        raw_steps = row.get("steps_json", "")
        if status not in {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}:
            errors.append(f"{case_id}: invalid deletion_status {status!r}")
            continue
        try:
            steps = json.loads(raw_steps)
        except (TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{case_id}: steps_json is invalid JSON ({exc})")
            continue
        if not isinstance(steps, list):
            errors.append(f"{case_id}: steps_json must be a JSON array")
            continue
        if status == "NOT_APPLICABLE":
            if steps:
                errors.append(f"{case_id}: NOT_APPLICABLE must have an empty steps array")
            continue

        previous_key = None
        phases = []
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                errors.append(f"{case_id}: step {index} must be a JSON object")
                continue
            if set(step) != STEP_FIELDS:
                errors.append(f"{case_id}: step {index} must contain exactly the required fields")
                continue
            if step["step_no"] != index:
                errors.append(f"{case_id}: step {index} has step_no={step['step_no']!r}")
            phase = step["phase"]
            operation = step["operation"]
            if phase not in PHASE_RANK:
                errors.append(f"{case_id}: step {index} has invalid phase {phase!r}")
                continue
            if OPERATION_PHASE.get(operation) != phase:
                errors.append(f"{case_id}: step {index} operation/phase mismatch")
            if OPERATION_STATE.get(operation) != step["state"]:
                errors.append(f"{case_id}: step {index} operation/state mismatch")
            phases.append(phase)
            key = (
                PHASE_RANK[phase],
                OPERATION_RANK.get(operation, 99),
                str(step["system_id"]),
                str(step["resource_id"]),
            )
            if previous_key is not None and key < previous_key:
                errors.append(f"{case_id}: steps are not in required canonical order")
            previous_key = key

            evidence_id = step["evidence_id"]
            if status == "COMPLETE":
                if phase != "VERIFICATION" or not evidence_id:
                    errors.append(f"{case_id}: COMPLETE steps must be cited verifications")
            elif phase == "FINDING" and not evidence_id:
                errors.append(f"{case_id}: INCOMPLETE findings must cite evidence")
            elif phase in {"REMEDIATION", "VERIFICATION"} and evidence_id != "":
                errors.append(f"{case_id}: future INCOMPLETE steps must have empty evidence_id")

        if phases != sorted(phases, key=PHASE_RANK.get):
            errors.append(f"{case_id}: phases are not ordered FINDING, REMEDIATION, VERIFICATION")
        if status == "INCOMPLETE" and "FINDING" not in phases:
            errors.append(f"{case_id}: INCOMPLETE cases must include at least one finding")

    return errors


def _resolve_candidate(path_str: str | None, default_names: list[str]) -> Path | None:
    if path_str:
        p = Path(path_str)
        if p.is_file():
            return p
        for prefix in [Path("."), Path(".."), Path("../..")]:
            cand = prefix / path_str
            if cand.is_file():
                return cand.resolve()
        return p  # return original as best effort

    for name in default_names:
        for prefix in [Path("."), Path(".."), Path("../..")]:
            cand = prefix / name
            if cand.is_file():
                return cand.resolve()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", default=None, help="Path to output CSV file (optional positional argument)")
    parser.add_argument("--input", "-i", default=None, help="Path to input deletion requests CSV")
    parser.add_argument("--output", "-o", default=None, help="Path to output predictions CSV")
    args = parser.parse_args()

    # Determine output path
    output_target = args.output or args.target
    output_path = _resolve_candidate(output_target, ["output.csv", "sample_predictions.csv"])
    if not output_path or not output_path.is_file():
        fallback = Path(output_target if output_target else "output.csv")
        print(f"ERROR: Output file not found: {fallback}")
        return 1

    # Determine input path
    input_path = _resolve_candidate(args.input, ["dataset/deletion_requests.csv", "dataset/sample_deletion_requests.csv"])
    if not input_path or not input_path.is_file():
        fallback_in = Path(args.input if args.input else "dataset/deletion_requests.csv")
        print(f"ERROR: Input requests file not found: {fallback_in}")
        return 1

    print(f"Validating: {output_path.name} against {input_path.name}...")
    errors = validate(input_path, output_path)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"Validation failed with {len(errors)} error(s).")
        return 1

    print(f"Submission contract validation passed for {output_path.name} ({len(_load_rows(output_path))} rows).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
