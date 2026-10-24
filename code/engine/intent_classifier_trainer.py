"""
Intent Classifier Trainer
==========================
Trains and evaluates a lightweight TF-IDF + Logistic Regression classifier
for Stage 1B of the NSTVE Intent Gate.

The classifier is trained on:
  1. The labelled public examples from sample_deletion_requests.csv +
     sample_output.csv.
  2. Synthetic examples for both intents.

Produces:
  code/engine/trained_model/intent_classifier.joblib   (TfidfVectorizer + LR pipeline)
  code/engine/trained_model/training_report.txt        (metrics + confusion matrix)

Usage:
  python code/engine/intent_classifier_trainer.py
"""

import os
import logging
import time
from typing import List, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import (
    classification_report, confusion_matrix, accuracy_score, f1_score
)
import joblib

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATASET_DIR = os.path.join(ROOT, "dataset")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "trained_model")
os.makedirs(MODEL_DIR, exist_ok=True)

# ── Synthetic negative (NOT_APPLICABLE) examples ──────────────────────────────

_SYNTHETIC_NOT_APPLICABLE = [
    "Please update my delivery address to 42 Maple Street.",
    "I forgot my password. Can you help me reset it?",
    "Could you send me a copy of my order history?",
    "I'd like to export a CSV of all my transactions.",
    "Under GDPR Article 15, I request access to all personal data you hold about me.",
    "Please keep my account active. I just need to update my phone number.",
    "Can you correct the spelling of my name on the account? Please don't delete anything.",
    "I want to download my data in a portable format. Leave my account as it is.",
    "Please update my email address. I want to continue using the service.",
    "My invoice from last month is missing. Can you resend it?",
    "I cannot log in. Please help me reset my credentials without closing the account.",
    "Please add a new payment method to my account.",
    "Can I get a copy of the personal data you store about me? I still use the account.",
    "Please update my billing address only.",
    "I want to unsubscribe from marketing emails but keep my account.",
    "Send me my annual statements. Do not close the account.",
    "Can you fix the typo in my surname? Please leave the rest untouched.",
    "I need a duplicate invoice for tax purposes. Keep account active.",
    "Please opt me out of promotional notifications. Don't delete my profile.",
    "My order was not delivered. Please help without touching my account.",
    "I would like to retrieve a copy of the terms I agreed to.",
    "Please change my username. Do not delete or change anything else.",
    "I need help with two-factor authentication setup.",
    "Please suspend my account temporarily, not permanently delete it.",
    "Can you verify my identity without removing my account?",
    "I want to add a secondary email address. Leave everything else as it is.",
    "Under Article 15 GDPR, please provide my data without removing any records.",
    "Please do not delete or change anything; I just need a data export.",
    "I'd like to update my marketing preferences. Keep the account active.",
    "Can you send me a password reset link? I still use this account regularly.",
    "I want to correct my date of birth on the profile. Do not close the account.",
    "Please restore my previous delivery address. Do not delete my account.",
    "I need technical support. Leave my account active while you investigate.",
    "Please don't delete my account. I want to continue using the service.",
    "I am having trouble logging in. Please leave the account active.",
    "I need access to my purchase records for legal purposes. Do not delete.",
    "My mobile number needs updating. Leave account as is.",
    "Could you deactivate 2FA temporarily? Do not close or remove the account.",
    "Can I change the language setting? Don't remove any of my records.",
    "Please add an additional address to my shipping options. Keep account active.",
]

_SYNTHETIC_DELETION = [
    "Please delete my account and all associated data.",
    "I want my account erased permanently. Please confirm when done.",
    "Under GDPR Article 17, I request the erasure of all my personal data.",
    "Please close this account and remove all personal information.",
    "I no longer wish to use this service. Please purge my data.",
    "Kindly remove all records associated with my email address.",
    "Please destroy all data you have on me immediately.",
    "I am invoking my right to be forgotten. Delete everything.",
    "Please cancel my account and erase all personal data.",
    "Ich möchte mein Konto löschen und alle persönlichen Daten entfernen.",
    "Je souhaite supprimer mon compte et effacer toutes mes données personnelles.",
    "Por favor, elimina mi cuenta y todos los datos personales.",
    "アカウントを削除してください。個人データをすべて消去してください。",
    "계정을 삭제하고 모든 개인 정보를 지워주세요.",
    "Please close my account permanently. Handle any copies within scope.",
    "I want the account associated with this address to be erased.",
    "Shut down my account and delete all my personal information.",
    "Please process the data deletion request. Confirm when complete.",
    "Remove my profile and all associated records from your systems.",
    "I want to exercise my right to erasure under data protection law.",
    "Please wipe all my data and close the account.",
    "I wish to withdraw from this platform entirely. Delete my data.",
    "My personal data must be purged from all your systems.",
    "Please confirm the deletion of my account and data.",
    "Delete this account. I do not wish to have any data stored.",
    "I request that my profile, order history, and personal data be erased.",
    "Please obliterate all records connected to my email address.",
    "Terminate my account and remove all stored information.",
    "I want confirmation that the profile is gone along with all associated data.",
    "Please handle the deletion and notify me when everything has been removed.",
    "I want to close this account permanently. You may retain backups if required, but they must not be able to restore my personal profile.",
    "Please erase my personal data and close my account. Thank you.",
    "I'm deleting my account — please also clear out my search history.",
    "Request for account closure and full data deletion.",
    "Please remove my name, email, and all purchase records from your database.",
    "I want my data deleted in accordance with GDPR Article 17.",
    "Kindly proceed with the complete deletion of my account.",
    "I wish to have my account permanently deleted with all my information.",
    "Please begin the process of erasing all my personal data immediately.",
    "I no longer consent to data processing. Please erase everything.",
]


# ── Data loading ──────────────────────────────────────────────────────────────

def load_labelled_examples(
    dataset_dir: str,
) -> Tuple[List[str], List[int]]:
    """
    Returns (texts, labels) where label 1 = DELETION, 0 = NOT_APPLICABLE.
    Sources:
      1. sample_deletion_requests.csv × sample_output.csv (gold labels)
      2. Synthetic examples
    """
    texts: List[str] = []
    labels: List[int] = []

    # output.csv contains predictions, not labels; train only on labelled public examples.
    sr_path = os.path.join(dataset_dir, "sample_deletion_requests.csv")
    so_path = os.path.join(dataset_dir, "sample_output.csv")
    if not os.path.exists(sr_path) or not os.path.exists(so_path):
        raise FileNotFoundError(
            "Training requires sample_deletion_requests.csv and sample_output.csv "
            f"under {dataset_dir}"
        )

    sr = pd.read_csv(sr_path)
    so = pd.read_csv(so_path)
    merged_s = sr.merge(so[["case_id", "deletion_status"]], on="case_id")
    for _, row in merged_s.iterrows():
        txt = str(row.get("request_text", "")).strip()
        status = str(row.get("deletion_status", "")).strip()
        if not txt:
            continue
        if status not in {"NOT_APPLICABLE", "COMPLETE", "INCOMPLETE"}:
            raise ValueError(f"Unexpected deletion_status in sample output: {status!r}")
        label = 0 if status == "NOT_APPLICABLE" else 1
        texts.append(txt)
        labels.append(label)
    if not texts:
        raise ValueError("No labelled training examples were loaded from the public samples")
    logger.info("Loaded %d labelled examples from public sample files", len(merged_s))

    # Synthetic examples
    for txt in _SYNTHETIC_NOT_APPLICABLE:
        texts.append(txt)
        labels.append(0)
    for txt in _SYNTHETIC_DELETION:
        texts.append(txt)
        labels.append(1)
    logger.info("Added %d synthetic NOT_APPLICABLE and %d synthetic DELETION examples",
                len(_SYNTHETIC_NOT_APPLICABLE), len(_SYNTHETIC_DELETION))

    return texts, labels


# ── Model pipeline ────────────────────────────────────────────────────────────

def build_pipeline() -> Pipeline:
    """TF-IDF + Logistic Regression pipeline optimised for short, multilingual text."""
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",        # character n-grams catch stems in any language
            ngram_range=(2, 4),
            min_df=1,
            max_features=30_000,
            sublinear_tf=True,
            strip_accents=None,         # preserve accented characters for multilingual
        )),
        ("clf", LogisticRegression(
            C=3.0,
            class_weight="balanced",
            max_iter=1000,
            solver="lbfgs",
            random_state=42,
        )),
    ])


# ── Training & evaluation ─────────────────────────────────────────────────────

def train(dataset_dir: str = DATASET_DIR) -> Pipeline:
    logger.info("=" * 60)
    logger.info("  Northstar Shop Intent Classifier Training")
    logger.info("=" * 60)

    texts, labels = load_labelled_examples(dataset_dir)
    X = np.array(texts)
    y = np.array(labels)

    logger.info("Total training examples: %d (label 0=%d, label 1=%d)",
                len(y), (y == 0).sum(), (y == 1).sum())

    # Cross-validation with visible per-fold progress.
    pipeline = build_pipeline()
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = []
    print("\n[1/3] Starting 5-fold cross-validation", flush=True)
    cv_start = time.perf_counter()
    for fold_no, (train_indices, validation_indices) in enumerate(cv.split(X, y), start=1):
        fold_start = time.perf_counter()
        print(f"  Fold {fold_no}/5: fitting...", flush=True)
        fold_pipeline = build_pipeline()
        fold_pipeline.fit(X[train_indices], y[train_indices])
        validation_predictions = fold_pipeline.predict(X[validation_indices])
        fold_score = f1_score(
            y[validation_indices], validation_predictions, average="macro"
        )
        cv_scores.append(fold_score)
        print(
            f"  Fold {fold_no}/5: macro F1={fold_score:.4f} "
            f"({time.perf_counter() - fold_start:.2f}s)",
            flush=True,
        )
    cv_scores = np.asarray(cv_scores)
    print(f"Cross-validation complete in {time.perf_counter() - cv_start:.2f}s", flush=True)
    logger.info("5-Fold CV F1 (macro): %.4f ± %.4f", cv_scores.mean(), cv_scores.std())

    # Full fit
    print("\n[2/3] Fitting final model on all training examples...", flush=True)
    fit_start = time.perf_counter()
    pipeline.fit(X, y)
    print(f"Final model fit complete in {time.perf_counter() - fit_start:.2f}s", flush=True)

    # Training set metrics
    y_pred = pipeline.predict(X)
    train_acc = accuracy_score(y, y_pred)
    train_f1 = f1_score(y, y_pred, average="macro")
    cm = confusion_matrix(y, y_pred)
    report = classification_report(y, y_pred, target_names=["NOT_APPLICABLE", "DELETION"])

    logger.info("Training Accuracy: %.4f | Macro F1: %.4f", train_acc, train_f1)

    # Save model
    model_path = os.path.join(MODEL_DIR, "intent_classifier.joblib")
    print("\n[3/3] Saving trained model and evaluation report...", flush=True)
    joblib.dump(pipeline, model_path)
    logger.info("Model saved → %s", model_path)

    # Write training report
    report_path = os.path.join(MODEL_DIR, "training_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("Northstar Shop — Intent Classifier Training Report\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Total examples     : {len(y)}\n")
        f.write(f"  NOT_APPLICABLE   : {(y==0).sum()}\n")
        f.write(f"  DELETION         : {(y==1).sum()}\n\n")
        f.write(f"5-Fold CV F1       : {cv_scores.mean():.4f} ± {cv_scores.std():.4f}\n")
        f.write(f"Train Accuracy     : {train_acc:.4f}\n")
        f.write(f"Train Macro F1     : {train_f1:.4f}\n\n")
        f.write("Confusion Matrix (rows=actual, cols=pred):\n")
        f.write(f"  Labels: NOT_APPLICABLE=0, DELETION=1\n")
        f.write(str(cm) + "\n\n")
        f.write("Classification Report:\n")
        f.write(report + "\n")

        # Sample predictions
        f.write("Sample Predictions:\n")
        test_cases = [
            ("Please delete my account.", 1),
            ("I want to erase all my data.", 1),
            ("Please keep my account active. Update my address.", 0),
            ("Under GDPR Article 15 I request my data copy.", 0),
            ("Close this account permanently.", 1),
            ("I want to close this account permanently.", 1),
            ("Ich möchte mein Konto löschen.", 1),
            ("Please update my billing details only.", 0),
            ("Erase my profile from all your systems.", 1),
            ("Can I unsubscribe from marketing only? Keep account.", 0),
        ]
        for txt, expected in test_cases:
            pred = pipeline.predict([txt])[0]
            prob = pipeline.predict_proba([txt])[0]
            label_map = {0: "NOT_APPLICABLE", 1: "DELETION"}
            status = "✓" if pred == expected else "✗"
            f.write(f"  {status} [{label_map[pred]:>14}] p={prob[1]:.3f} | {txt[:70]}\n")

    logger.info("Training report saved → %s", report_path)

    # Print summary
    print("\n" + "=" * 60)
    print("  Intent Classifier Training Complete")
    print("=" * 60)
    print(f"  Examples (total)   : {len(y)}")
    print(f"  NOT_APPLICABLE     : {(y==0).sum()}")
    print(f"  DELETION           : {(y==1).sum()}")
    print(f"  5-Fold CV F1       : {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
    print(f"  Train Accuracy     : {train_acc:.4f}")
    print(f"  Macro F1           : {train_f1:.4f}")
    print(f"  Model saved to     : {model_path}")
    print(f"  Report saved to    : {report_path}")
    print("=" * 60)

    return pipeline


if __name__ == "__main__":
    train()
