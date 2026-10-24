# Evaluation Report

## Scope and evidence

- Full prediction input: `dataset/deletion_requests.csv` (518 requests).
- Public calibration set: `dataset/sample_deletion_requests.csv` and
  `dataset/sample_output.csv` (32 labeled cases).
- Prediction output: root `output.csv`.
- No organizer-only files or hidden canonical answers were used.

The 32 public cases were compared with `sample_output.csv`. The full 518-case
run can be checked for contract compliance, but its hidden-answer accuracy
cannot be measured from participant-facing files.

## Public sample results

| Metric | Result |
|---|---:|
| Case-level deletion-status accuracy | 32/32 (100.00%) |
| Exact ordered step-sequence accuracy | 20/32 (62.50%) |
| Exact step-tuple accuracy | 171/193 gold steps (88.60%) |
| Phase field accuracy at aligned positions | 185/185 (100.00%) |
| System field accuracy at aligned positions | 174/185 (94.05%) |
| Resource field accuracy at aligned positions | 171/185 (92.43%) |
| Operation field accuracy at aligned positions | 174/185 (94.05%) |
| State field accuracy at aligned positions | 174/185 (94.05%) |
| Evidence-id field accuracy at aligned positions | 185/185 (100.00%) |
| Gold/predicted step counts | 193 / 186 |

Field metrics are calculated only over aligned step positions; they do not
penalize missing or extra steps. Exact sequence accuracy is the stricter
end-to-end measure. The public samples are not an independent holdout for the
intent model because their labels are among the trainer inputs.

## Full output contract check

The final run produced 518 rows, sorted by `case_id`. The contract validator
passed for required columns, exact input-case coverage, JSON arrays, step
fields/numbers, allowed phase-operation-state combinations, canonical ordering,
and evidence-id rules.

| Predicted status | Count |
|---|---:|
| COMPLETE | 271 |
| INCOMPLETE | 240 |
| NOT_APPLICABLE | 7 |

These are output counts, not measured status accuracy.

## Participant-created regression cases

Six new intent-gate unit cases are maintained in
`evaluation/test_intent_gate.py`; all six passed:

1. Direct English request to delete an account → `DELETION`.
2. GDPR Article 15 access request with an explicit request not to close the
   account → `NOT_APPLICABLE`.
3. Direct French request to erase an account → `DELETION`.
4. English negation (“I do not want my account deleted”) → `NOT_APPLICABLE`.
5. Phone-number correction while keeping the profile active → `NOT_APPLICABLE`.
6. Spanish negation (“No quiero eliminar mi cuenta”) → `NOT_APPLICABLE`.

These are focused authorization tests, not full evidence-audit cases.

## Failures found and improvements made

- The trainer previously treated prediction output as silver labels and
  duplicated the public sample labels. It now trains only on labeled public
  samples plus synthetic examples, and fails explicitly if those labeled files
  are missing.
- New English, French, and Spanish negation tests exposed false `DELETION`
  classifications. Explicit negated-deletion patterns and regression tests
  were added.
- The CLI previously sorted IDs numerically, which differs from lexicographic
  `case_id` order for variable-width IDs. It now sorts by the actual ID string.
- A dedicated submission validator now checks the complete output contract.
- Step-level sample failures remain: five cases omit a retained security-audit
  verification; three cases use a different account resource ID; and four
  cases omit or add an analytics verification. These identity/evidence
  association mismatches need further investigation; they are not hidden by the
  100% status result.

## Next improvements

Prioritize evidence-to-subject linkage for retained audit rows and anonymous
analytics records, then correct account selection using evidence available by
each `audit_at`. Re-run the public step benchmark and preserve the current
full-dataset contract checks after each change.
