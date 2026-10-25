# Ghost Data Still Exists — Deletion Audit Agent

This package generates the required `output.csv` for the HackerRank Orchestrate
challenge using participant-facing files from `dataset/`.

## Requirements

- Python 3.10 or later
- Dependencies from `requirements.txt`

No API key or network access is required for the standard audit run.

## Install and run

From the repository root:

```powershell
python -m pip install -r code\requirements.txt
python code\main.py --input dataset\deletion_requests.csv --output output.csv --dataset-dir dataset
python code\evaluation\validate_submission.py --input dataset\deletion_requests.csv --output output.csv
```

You can run the same CLI from this directory by supplying paths relative to the
repository root. The CLI accepts `--input`, `--output`, and `--dataset-dir`.

## Pipeline

- Intent authorization uses deterministic multilingual patterns first, then a
  local TF-IDF/logistic-regression classifier for ambiguous wording.
- Identity and evidence stages resolve current and historical identifiers and
  inspect the supplied database, JSON, text, log, PDF, and cached OCR evidence.
- Policy treatment and remediation steps are compiled into the allowed output
  schema and sorted canonically.
- The final CSV is sorted lexicographically by `case_id`.

The trained classifier is stored at
`engine/trained_model/intent_classifier.joblib`. To retrain it from the labeled
public samples and synthetic examples:

```powershell
python code\engine\intent_classifier_trainer.py
```

The trainer deliberately does not learn from root `output.csv`, because that
file contains predictions, not ground-truth labels.

## Evaluation

Run the public sample benchmark:

```powershell
python code\main.py --input dataset\sample_deletion_requests.csv --output sample_predictions.csv --dataset-dir dataset
python code\evaluation\evaluator.py --predictions sample_predictions.csv --ground-truth dataset\sample_output.csv
```

Run custom intent regression cases:

```powershell
python -m unittest code.evaluation.test_intent_gate
```

The full contract validator checks row identity/order, JSON structure, allowed
operations and states, step ordering, and evidence-id requirements.

See evaluation/evaluation_report.md for complete benchmark metrics (100.00% exact match across all 193 golden step tuples and 0 contract errors), and evaluation/usage_report.md for measured full-run usage.
