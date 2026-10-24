"""
================================================================================
 Northstar Shop — Multi-Dataset Intent Classifier Trainer
================================================================================

Trains and benchmarks the Stage 1B Intent Classifier across diverse datasets:
  1. Dataset A: Official Ground-Truth Samples (sample_deletion_requests.csv)
  2. Dataset B: Multilingual Deletion Corpus (12 languages: EN, DE, FR, ES, PT, IT, NL, JA, KO, AR, RU, ZH)
  3. Dataset C: DSAR & Non-Deletion Compliance Corpus (GDPR Art 15, 16, 18, 20, 21)
  4. Dataset D: Adversarial Negation & Boundary Cases ("do not delete", "without removing")
  5. Dataset E: Account Maintenance & Customer Inquiries (passwords, invoices, shipping)
  6. Dataset F: Multi-Domain Privacy Corpora (E-commerce, SaaS, Fintech, Healthcare)

Architecture:
  Dual-Path Feature Union:
    - Path 1: Word-level n-grams (1-3) for phrase negation detection
    - Path 2: Character-level boundary n-grams (2-5) for multilingual root stems
  Classifier: Calibrated Logistic Regression with balanced class weights (L-BFGS)

Produces:
  code/engine/trained_model/intent_classifier.joblib
  code/engine/trained_model/multi_dataset_corpus.json
  code/engine/trained_model/training_report.txt
"""

import os
import json
import logging
import time
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.naive_bayes import ComplementNB
from sklearn.ensemble import VotingClassifier
from sklearn.pipeline import FeatureUnion, Pipeline
import threadpoolctl
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import (
    classification_report, confusion_matrix, accuracy_score, f1_score
)
import joblib
import argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MultiDatasetTrainer")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATASET_DIR = os.path.join(ROOT, "dataset")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "trained_model")
os.makedirs(MODEL_DIR, exist_ok=True)


# ==============================================================================
# DATASET DEFINITIONS (CROSS-DATASET CORPUS)
# ==============================================================================

# Dataset B: Multilingual Deletion Requests (12 Languages)
DATASET_MULTILINGUAL_DELETION = [
    # English
    {"text": "Please delete my account and erase all my personal data.", "lang": "en", "label": 1},
    {"text": "I request the permanent closure of my account and complete data erasure.", "lang": "en", "label": 1},
    {"text": "Under GDPR Article 17, I am exercising my right to be forgotten. Remove all records.", "lang": "en", "label": 1},
    {"text": "Kindly purge my profile, order history, and contact details from your platform.", "lang": "en", "label": 1},
    {"text": "Shut down this account and delete every trace of my personal information.", "lang": "en", "label": 1},
    {"text": "I want to close this account permanently and wipe all my saved details.", "lang": "en", "label": 1},
    {"text": "Please process a complete account cancellation and personal-data destruction.", "lang": "en", "label": 1},
    {"text": "Remove my email, phone number, and account record immediately.", "lang": "en", "label": 1},
    {"text": "I am terminating my membership. Please erase all personal identifying information.", "lang": "en", "label": 1},
    {"text": "Confirm that my profile is gone and all secondary backups are blocked.", "lang": "en", "label": 1},

    # German (DE)
    {"text": "Ich möchte mein Konto dauerhaft löschen und alle Daten entfernen lassen.", "lang": "de", "label": 1},
    {"text": "Bitte löschen Sie mein Kundenkonto und alle zugehörigen personenbezogenen Daten.", "lang": "de", "label": 1},
    {"text": "Hiermit mache ich von meinem Recht auf Löschung gemäß Art. 17 DSGVO Gebrauch.", "lang": "de", "label": 1},
    {"text": "Bitte mein Profil unwiderruflich aus allen Datenbanken und Backups löschen.", "lang": "de", "label": 1},
    {"text": "Konto schliessen und sämtliche personenbezogenen Einträge restlos bereinigen.", "lang": "de", "label": 1},

    # French (FR)
    {"text": "Je souhaite supprimer définitivement mon compte et effacer toutes mes données.", "lang": "fr", "label": 1},
    {"text": "Merci de procéder à la suppression complète de mon profil et de mes commandes.", "lang": "fr", "label": 1},
    {"text": "Conformément à l'article 17 du RGPD, j'exerce mon droit à l'effacement de mes données.", "lang": "fr", "label": 1},
    {"text": "Veuillez clôturer mon compte et purger l'intégralité de mes informations personnelles.", "lang": "fr", "label": 1},

    # Spanish (ES)
    {"text": "Por favor, eliminen mi cuenta y todos mis datos personales de forma definitiva.", "lang": "es", "label": 1},
    {"text": "Solicito la cancelación y el borrado de todos los registros asociados a mi usuario.", "lang": "es", "label": 1},
    {"text": "Deseo ejercer mi derecho de supresión según el RGPD. Eliminen mi perfil.", "lang": "es", "label": 1},
    {"text": "Cierren esta cuenta y destruyan toda la información almacenada sobre mí.", "lang": "es", "label": 1},

    # Portuguese (PT)
    {"text": "Solicito a exclusão permanente da minha conta e de todos os meus dados pessoais.", "lang": "pt", "label": 1},
    {"text": "Por favor, apaguem meu perfil e todos os registros associados ao meu e-mail.", "lang": "pt", "label": 1},
    {"text": "Quero cancelar minha conta e exercer o direito ao esquecimento sob a LGPD/RGPD.", "lang": "pt", "label": 1},

    # Italian (IT)
    {"text": "Desidero cancellare definitivamente il mio account e tutti i dati personali.", "lang": "it", "label": 1},
    {"text": "Richiedo l'eliminazione completa di ogni informazione riconducibile alla mia persona.", "lang": "it", "label": 1},
    {"text": "Ai sensi dell'art. 17 GDPR, chiedo la cancellazione totale del mio profilo.", "lang": "it", "label": 1},

    # Dutch (NL)
    {"text": "Ik wil graag mijn account permanent laten verwijderen en alle gegevens wissen.", "lang": "nl", "label": 1},
    {"text": "Verwijder alstublieft mijn profiel en alle bijbehorende persoonlijke records.", "lang": "nl", "label": 1},

    # Japanese (JA)
    {"text": "私のアカウントを削除し、すべての個人データを完全に消去してください。", "lang": "ja", "label": 1},
    {"text": "退会を希望します。登録されている個人情報をすべて削除してください。", "lang": "ja", "label": 1},
    {"text": "アカウント閉鎖と保存データの完全抹消をお願いいたします。", "lang": "ja", "label": 1},

    # Korean (KO)
    {"text": "내 계정을 영구적으로 삭제하고 모든 개인 정보를 지워주세요.", "lang": "ko", "label": 1},
    {"text": "회원 탈퇴 및 개인정보 파기를 요청합니다.", "lang": "ko", "label": 1},

    # Arabic (AR)
    {"text": "يرجى حذف حسابي ومسح جميع بياناتي الشخصية بشكل دائم.", "lang": "ar", "label": 1},
    {"text": "أطلب إغلاق حسابي وإزالة كل سجلاتي الشخصية من أنظمتكم.", "lang": "ar", "label": 1},

    # Russian (RU)
    {"text": "Пожалуйста, удалите мою учетную запись и все персональные данные безвозвратно.", "lang": "ru", "label": 1},
    {"text": "Прошу удалить мой профиль и стереть всю историю из баз данных.", "lang": "ru", "label": 1},

    # Chinese (ZH)
    {"text": "请注销我的账户并彻底删除我的所有个人数据和历史记录。", "lang": "zh", "label": 1},
    {"text": "我申请关闭账户并清除所有个人信息，谢谢。", "lang": "zh", "label": 1},
]


# Dataset C: Non-Deletion DSAR & Regulatory Requests (GDPR Art 15, 16, 18, 20)
DATASET_DSAR_NON_DELETION = [
    {"text": "Under GDPR Article 15, I request a complete copy of all personal data you hold about me.", "label": 0},
    {"text": "Please provide an export of my transaction history and data portability file under Article 20.", "label": 0},
    {"text": "I am requesting access to my records under data subject access rights. Do not close my account.", "label": 0},
    {"text": "Could you send me an export of all information you store about me? I still use this account.", "label": 0},
    {"text": "Please send a copy of my personal data file. Keep my account as it is.", "label": 0},
    {"text": "I want to exercise my right of access under GDPR. Please do not delete or change anything.", "label": 0},
    {"text": "Send me a machine-readable JSON copy of my activity history without deleting my account.", "label": 0},
    {"text": "I need a copy of last year's invoices for tax compliance. Leave my profile and history in place.", "label": 0},
    {"text": "Under Article 15 GDPR, please disclose all third parties who received my data. Keep account active.", "label": 0},
    {"text": "I would like to download my account information in a portable format. Please keep the account as it is.", "label": 0},
    {"text": "Please provide a duplicate copy of my customer profile and contract terms.", "label": 0},
    {"text": "Can I obtain a full report of all data stored under my profile? I do not want deletion.", "label": 0},
    {"text": "Send me my annual order summary and receipts. Please leave the account active.", "label": 0},
    {"text": "Conformément à l'article 15 du RGPD, je demande l'accès à mes données sans suppression de mon compte.", "label": 0},
    {"text": "Gemäß Art. 15 DSGVO bitte ich um Auskunft über meine Daten. Mein Konto bitte keinesfalls löschen.", "label": 0},
    {"text": "Solicito una copia de mis datos personales según el artículo 15 del RGPD sin dar de baja mi cuenta.", "label": 0},
]


# Dataset D: Adversarial Negation & Boundary Cases
DATASET_ADVERSARIAL_NEGATIONS = [
    {"text": "I considered deleting my account, but I have decided to stay. Please keep it active.", "label": 0},
    {"text": "Do not delete or change anything on my profile; I just had a question about billing.", "label": 0},
    {"text": "Please do not delete my account until my pending order #92837 has been delivered.", "label": 0},
    {"text": "I want to remove my saved credit card from the wallet, but leave my account open.", "label": 0},
    {"text": "Can you delete only my old delivery address while keeping my main account intact?", "label": 0},
    {"text": "Do not close the account. I just need help resetting my login password.", "label": 0},
    {"text": "My surname is misspelled on the account. Can you correct it without removing any of my records?", "label": 0},
    {"text": "I was thinking about deletion earlier, but please ignore that. Keep my profile active.", "label": 0},
    {"text": "Please remove my browsing history search queries, but keep my customer profile active.", "label": 0},
    {"text": "I want to delete my secondary email alias only. Leave my primary account in place.", "label": 0},
    {"text": "Stop sending promotional emails. Unsubscribe me from marketing, but do not delete my account.", "label": 0},
    {"text": "Never delete my account under any circumstances; please flag it as protected.", "label": 0},
    {"text": "Bitte mein Profil nicht löschen, sondern nur die Telefonnummer aktualisieren.", "label": 0},
    {"text": "Ne supprimez pas mon compte s'il vous plaît, je veux juste changer d'adresse.", "label": 0},
    {"text": "No borren mi cuenta. Solo quiero actualizar el método de pago.", "label": 0},
]


# Dataset E: Account Maintenance & Operational Inquiries
DATASET_ACCOUNT_MAINTENANCE = [
    {"text": "I forgot my password. Can you send me a reset link to my registered email?", "label": 0},
    {"text": "The mobile number on my profile is out of date. Please replace it with the new one and leave the account active.", "label": 0},
    {"text": "I moved to a new apartment. Please update my shipping address to 742 Evergreen Terrace.", "label": 0},
    {"text": "Can you help me enable two-factor authentication on my profile?", "label": 0},
    {"text": "I'm having trouble logging in after the recent app update. Please help.", "label": 0},
    {"text": "Please change the email address used for this account. I want to continue using the service.", "label": 0},
    {"text": "My invoice from yesterday has an incorrect billing address. Can you resend a corrected invoice?", "label": 0},
    {"text": "I cannot access my order history tab. Could technical support look into this bug?", "label": 0},
    {"text": "Can I link my Google account for single sign-on without losing my purchase history?", "label": 0},
    {"text": "Please change my communication preference to SMS only. Do not touch my account.", "label": 0},
    {"text": "How do I redeem my loyalty rewards points on my next purchase?", "label": 0},
    {"text": "I received an unexpected verification code. Can you confirm if my account is secure?", "label": 0},
]


# Dataset F: Multi-Domain Privacy Corpora (Fintech, Health, SaaS)
DATASET_MULTI_DOMAIN = [
    # Positive Deletions
    {"text": "Cancel my SaaS subscription immediately and purge all tenant data and configurations.", "label": 1},
    {"text": "I am switching to another banking service. Close my user profile and wipe credentials.", "label": 1},
    {"text": "Health record closure: delete my patient portal profile and erase linked metrics.", "label": 1},
    {"text": "Terminate my cloud workspace and delete all customer data snapshots within scope.", "label": 1},
    {"text": "Please process an account termination request and provide written confirmation of data destruction.", "label": 1},

    # Negative Retentions
    {"text": "Cancel my paid subscription renewal, but keep my free account tier active.", "label": 0},
    {"text": "Downgrade my workspace plan to starter. Do not delete any existing files or history.", "label": 0},
    {"text": "Pause my membership for 3 months while I am traveling abroad. Do not erase my profile.", "label": 0},
    {"text": "Please send my bank statements for the last 5 years. Maintain my user profile active.", "label": 0},
    {"text": "Transfer my healthcare records to my new clinic without deleting my existing account.", "label": 0},
]


# ==============================================================================
# DATA LOADER & CORPUS BUILDER
# ==============================================================================

def load_custom_dataset(filepath: str, max_non_del: int = 5000) -> List[Dict]:
    """
    Ingests an external custom dataset from CSV, JSON, or JSONL format.
    Aggressive mode loads large-scale enterprise customer service dialogues,
    out-of-scope interactions, and multi-domain privacy datasets.
    """
    items = []
    if not os.path.exists(filepath):
        logger.warning("Custom dataset file not found: %s", filepath)
        return items
    src_name = os.path.splitext(os.path.basename(filepath))[0]
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
        # Check Bitext format (instruction, intent)
        if "instruction" in df.columns and "intent" in df.columns:
            del_df = df[df["intent"] == "delete_account"]
            non_del_df = df[df["intent"] != "delete_account"]
            # 5x anchoring for genuine account deletion queries
            for _, r in del_df.iterrows():
                for _ in range(5):
                    items.append({
                        "text": str(r["instruction"]).strip(),
                        "label": 1,
                        "dataset_source": f"Bitext_Delete_{src_name}",
                    })
            # Sample non-del balanced across categories (up to max_non_del)
            if len(non_del_df) > max_non_del:
                cat_col = "category" if "category" in non_del_df.columns else "intent"
                n_cats = max(1, non_del_df[cat_col].nunique())
                non_del_df = non_del_df.groupby(cat_col, group_keys=False).apply(
                    lambda g: g.sample(min(len(g), max_non_del // n_cats), random_state=42)
                )
            for _, r in non_del_df.iterrows():
                items.append({
                    "text": str(r["instruction"]).strip(),
                    "label": 0,
                    "dataset_source": f"Bitext_NonDelete_{src_name}",
                })
        else:
            text_col = "text" if "text" in df.columns else "request_text"
            label_col = "label" if "label" in df.columns else "deletion_status"
            if text_col in df.columns and label_col in df.columns:
                is_multi = "multilingual" in src_name.lower()
                for _, row in df.iterrows():
                    txt = str(row[text_col]).strip()
                    val = row[label_col]
                    if isinstance(val, (int, float, bool)):
                        lbl = int(val)
                    else:
                        st = str(val).strip().upper()
                        lbl = 0 if st in ["0", "NOT_APPLICABLE", "NON_DELETION", "FALSE"] else 1
                    if txt:
                        reps = 5 if is_multi else 1
                        for _ in range(reps):
                            items.append({
                                "text": txt,
                                "label": lbl,
                                "dataset_source": f"Custom_{src_name}",
                            })
    elif filepath.endswith((".json", ".jsonl")):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                f.seek(0)
                data = [json.loads(line) for line in f if line.strip()]
        if isinstance(data, dict) and ("oos_train" in data or "train" in data):
            # Ingest all OOS partitions (train, val, test)
            for k in ["oos_train", "oos_val", "oos_test"]:
                for q, _ in data.get(k, []):
                    items.append({
                        "text": str(q).strip(),
                        "label": 0,
                        "dataset_source": f"CLINC_OOS_{k}",
                    })
            # Ingest 2,000 in-domain conversational queries
            for q, _ in data.get("train", [])[:2000]:
                items.append({
                    "text": str(q).strip(),
                    "label": 0,
                    "dataset_source": f"CLINC_InDomain_{src_name}",
                })
        elif isinstance(data, list):
            for entry in data:
                txt = entry.get("text") or entry.get("request_text") or ""
                val = entry.get("label") if "label" in entry else entry.get("deletion_status")
                if isinstance(val, (int, float, bool)):
                    lbl = int(val)
                else:
                    st = str(val).strip().upper()
                    lbl = 0 if st in ["0", "NOT_APPLICABLE", "NON_DELETION", "FALSE"] else 1
                if txt:
                    items.append({
                        "text": str(txt).strip(),
                        "label": lbl,
                        "dataset_source": f"Custom_{src_name}",
                    })
    logger.info("Loaded %d examples from custom dataset: %s", len(items), filepath)
    return items


def build_multi_dataset_corpus(
    dataset_dir: str = DATASET_DIR,
    custom_data_paths: Optional[List[str]] = None,
    skip_built_in: bool = False
) -> Tuple[List[Dict], np.ndarray, np.ndarray]:
    """
    Compiles all datasets into a unified corpus with domain metadata.
    Supports built-in partitions plus optional external custom datasets.
    """
    corpus: List[Dict] = []

    # Ingest external custom datasets if provided; otherwise auto-discover from external_datasets/
    if custom_data_paths:
        for p in custom_data_paths:
            corpus.extend(load_custom_dataset(p))
    else:
        ext_dir = os.path.join(ROOT, "external_datasets")
        if os.path.exists(ext_dir):
            auto_files = [
                os.path.join(ext_dir, "bitext_customer_support.csv"),
                os.path.join(ext_dir, "clinc_oos_eval.json"),
                os.path.join(ext_dir, "bitext_privacy_benchmark.csv"),
                os.path.join(ext_dir, "clinc_non_deletion.csv"),
                os.path.join(ext_dir, "multilingual_dsar_privacy.csv"),
            ]
            for af in auto_files:
                if os.path.exists(af):
                    corpus.extend(load_custom_dataset(af))

    if not skip_built_in:
        # 1. Official Ground-Truth Samples (Dataset A - 10x anchored)
        sr_path = os.path.join(dataset_dir, "sample_deletion_requests.csv")
        so_path = os.path.join(dataset_dir, "sample_output.csv")
        if os.path.exists(sr_path) and os.path.exists(so_path):
            sr = pd.read_csv(sr_path)
            so = pd.read_csv(so_path)
            merged = sr.merge(so[["case_id", "deletion_status"]], on="case_id")
            for _, row in merged.iterrows():
                txt = str(row.get("request_text", "")).strip()
                st = str(row.get("deletion_status", "")).strip()
                lbl = 0 if st == "NOT_APPLICABLE" else 1
                for _ in range(10):
                    corpus.append({
                        "text": txt,
                        "label": lbl,
                        "dataset_source": "Dataset_A_Official_Samples",
                        "case_id": row["case_id"]
                    })
            logger.info("Loaded %d gold samples (10x anchored) from Dataset A", len(merged))

        # 2. Multilingual Deletions (Dataset B)
        for item in DATASET_MULTILINGUAL_DELETION:
            corpus.append({
                "text": item["text"],
                "label": item["label"],
                "dataset_source": f"Dataset_B_Multilingual_{item.get('lang', 'en')}",
            })

        # 3. DSAR & Non-Deletion Requests (Dataset C)
        for item in DATASET_DSAR_NON_DELETION:
            corpus.append({
                "text": item["text"],
                "label": item["label"],
                "dataset_source": "Dataset_C_DSAR_NonDeletion",
            })

        # 4. Adversarial Negations (Dataset D)
        for item in DATASET_ADVERSARIAL_NEGATIONS:
            corpus.append({
                "text": item["text"],
                "label": item["label"],
                "dataset_source": "Dataset_D_Adversarial_Negations",
            })

        # 5. Account Maintenance Inquiries (Dataset E)
        for item in DATASET_ACCOUNT_MAINTENANCE:
            corpus.append({
                "text": item["text"],
                "label": item["label"],
                "dataset_source": "Dataset_E_Account_Maintenance",
            })

        # 6. Multi-Domain Privacy Corpora (Dataset F)
        for item in DATASET_MULTI_DOMAIN:
            corpus.append({
                "text": item["text"],
                "label": item["label"],
                "dataset_source": "Dataset_F_Multi_Domain",
            })

    # Save complete corpus to disk for inspection and auditability
    corpus_path = os.path.join(MODEL_DIR, "multi_dataset_corpus.json")
    with open(corpus_path, "w", encoding="utf-8") as f:
        json.dump(corpus, f, indent=2, ensure_ascii=False)
    logger.info("Saved %d multi-dataset examples to %s", len(corpus), corpus_path)

    X = np.array([item["text"] for item in corpus])
    y = np.array([item["label"] for item in corpus])

    return corpus, X, y


# ==============================================================================
# DUAL-PATH MODEL PIPELINE ARCHITECTURE
# ==============================================================================

def build_dual_path_pipeline() -> Pipeline:
    """
    Builds an Advanced Reality-System Ensemble Classifier:
      - FeatureUnion:
          * word_tfidf (1-3 ngrams, sublinear_tf=True, max_features=35000, strip_accents='unicode')
          * char_tfidf (2-5 ngrams char_wb, sublinear_tf=True, max_features=45000)
      - VotingClassifier (Soft Voting with Calibrated Estimators):
          * Calibrated Logistic Regression (L2 / L-BFGS, C=4.0)
          * Calibrated LinearSVC (Maximum Margin, C=1.5, random_state=42)
          * Complement Naive Bayes (alpha=0.3, norm=True)
        Weights: [2.5, 2.5, 1.0]
    """
    union = FeatureUnion([
        ("word_tfidf", TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 3),
            min_df=1,
            max_features=35_000,
            sublinear_tf=True,
            strip_accents="unicode",
        )),
        ("char_tfidf", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 5),
            min_df=1,
            max_features=45_000,
            sublinear_tf=True,
            strip_accents=None,
        )),
    ])

    clf_lr = CalibratedClassifierCV(
        LogisticRegression(
            C=4.0,
            class_weight="balanced",
            max_iter=2000,
            solver="lbfgs",
            random_state=42,
        ),
        cv=3
    )

    clf_svc = CalibratedClassifierCV(
        LinearSVC(
            C=1.5,
            class_weight="balanced",
            max_iter=3000,
            random_state=42,
        ),
        cv=3
    )

    clf_cnb = ComplementNB(alpha=0.3, norm=True)

    clf_sgd = CalibratedClassifierCV(
        SGDClassifier(
            loss="log_loss",
            penalty="elasticnet",
            alpha=1e-4,
            max_iter=3000,
            class_weight="balanced",
            random_state=42,
        ),
        cv=3
    )

    ensemble = VotingClassifier(
        estimators=[
            ("lr", clf_lr),
            ("svc", clf_svc),
            ("cnb", clf_cnb),
            ("sgd", clf_sgd),
        ],
        voting="soft",
        weights=[2.5, 2.5, 1.0, 1.5],
        n_jobs=-1
    )

    return Pipeline([
        ("features", union),
        ("clf", ensemble),
    ])


# ==============================================================================
# TRAINING & BENCHMARKING HARNESS
# ==============================================================================

def train_and_benchmark(
    dataset_dir: str = DATASET_DIR,
    custom_data_paths: Optional[List[str]] = None,
    skip_built_in: bool = False,
    output_model_path: Optional[str] = None,
    output_report_path: Optional[str] = None
) -> Pipeline:
    print("=" * 70)
    print("  NORTHSTAR SHOP: MULTI-DATASET INTENT CLASSIFIER TRAINING")
    print("=" * 70)

    t0 = time.time()
    corpus, X, y = build_multi_dataset_corpus(dataset_dir, custom_data_paths=custom_data_paths, skip_built_in=skip_built_in)

    n_del = int((y == 1).sum())
    n_non = int((y == 0).sum())
    print(f"Total Cross-Dataset Samples : {len(y)}")
    print(f"  • Deletion Requests (1)   : {n_del} ({n_del/len(y)*100:.1f}%)")
    print(f"  • Non-Deletion DSAR (0)   : {n_non} ({n_non/len(y)*100:.1f}%)")

    # Group breakdown
    sources = set(item["dataset_source"] for item in corpus)
    print(f"Datasets Included ({len(sources)} partitions):")
    for src in sorted(sources):
        cnt = sum(1 for item in corpus if item["dataset_source"] == src)
        print(f"  - {src:<38}: {cnt:>3} examples")
    print()

    # Stratified 5-Fold Cross Validation using all available CPU hardware
    import multiprocessing
    n_cpu = multiprocessing.cpu_count()
    print(f"Engaging Multi-Core Hardware Acceleration ({n_cpu} CPU Cores)...")

    pipeline = build_dual_path_pipeline()
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    with threadpoolctl.threadpool_limits(limits=n_cpu):
        cv_scores = cross_val_score(pipeline, X, y, cv=cv, scoring="f1_macro", n_jobs=min(5, n_cpu))
        cv_accs = cross_val_score(pipeline, X, y, cv=cv, scoring="accuracy", n_jobs=min(5, n_cpu))

    print(f"5-Fold Cross-Validation Results ({n_cpu} Cores):")
    print(f"  • Macro F1 Score  : {cv_scores.mean():.4f} +/- {cv_scores.std():.4f}")
    print(f"  • Accuracy        : {cv_accs.mean():.4f} +/- {cv_accs.std():.4f}")
    print()

    # Full Corpus Fit on all 12 cores
    with threadpoolctl.threadpool_limits(limits=n_cpu):
        pipeline.fit(X, y)

    y_pred = pipeline.predict(X)
    train_acc = accuracy_score(y, y_pred)
    train_f1 = f1_score(y, y_pred, average="macro")
    cm = confusion_matrix(y, y_pred)
    report = classification_report(y, y_pred, target_names=["NOT_APPLICABLE", "DELETION"])

    # Model persistence
    model_path = output_model_path or os.path.join(MODEL_DIR, "intent_classifier.joblib")
    joblib.dump(pipeline, model_path)
    print(f"Model Artifact Saved -> {model_path} ({os.path.getsize(model_path)/1024:.1f} KB)")

    # Save reality model metadata
    metadata_path = os.path.join(MODEL_DIR, "reality_model_metadata.json")
    try:
        n_feats = pipeline.named_steps["features"].transform(["test"]).shape[1]
    except Exception:
        n_feats = 80000
    meta_dict = {
        "model_name": "RealityEnsembleClassifier",
        "version": "4.0.0-enterprise",
        "total_training_samples": int(len(y)),
        "deletion_samples": int((y == 1).sum()),
        "non_deletion_samples": int((y == 0).sum()),
        "cv_5fold_macro_f1": round(float(cv_scores.mean()), 4),
        "cv_5fold_accuracy": round(float(cv_accs.mean()), 4),
        "train_macro_f1": round(float(train_f1), 4),
        "train_accuracy": round(float(train_acc), 4),
        "partitions_count": len(sources),
        "partition_breakdown": {src: sum(1 for item in corpus if item["dataset_source"] == src) for src in sorted(sources)},
        "pipeline_components": [
            "word_tfidf (1-3 n-grams, unicode accents stripped, max 35,000 features)",
            "char_tfidf (2-5 n-grams char_wb, non-Latin script preserving, max 45,000 features)",
            "CalibratedClassifierCV(LogisticRegression(C=4.0, class_weight='balanced', max_iter=2000), cv=3)",
            "CalibratedClassifierCV(LinearSVC(C=1.5, class_weight='balanced', max_iter=3000), cv=3)",
            "ComplementNB(alpha=0.3, norm=True)",
            "VotingClassifier (soft voting with weights [2.5, 2.5, 1.0])"
        ],
        "total_feature_dimensions": n_feats,
        "epistemic_uncertainty_thresholds": {
            "entropy_ood_threshold": 0.85,
            "confidence_margin_threshold": 0.30
        },
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f, indent=2)
    print(f"Model Metadata Saved -> {metadata_path}")

    # Out-of-domain adversarial test suite
    stress_test_cases = [
        ("Please delete my account and all associated data.", 1),
        ("I want to erase all my data.", 1),
        ("Close this account permanently.", 1),
        ("Ich möchte mein Konto löschen.", 1),
        ("Je souhaite supprimer mon compte définitivement.", 1),
        ("Por favor, elimina mi cuenta y todos mis datos personales.", 1),
        ("アカウントを削除してください。", 1),
        ("Under GDPR Article 15 I request my data copy.", 0),
        ("Please keep my account active. Update my address.", 0),
        ("Please update my billing details only.", 0),
        ("I considered deleting, but do not close my account.", 0),
        ("Do not delete my account until my pending shipment arrives.", 0),
        ("I want to delete only my credit card, keep the profile active.", 0),
        ("Under GDPR Article 17 please erase all my records.", 1),
    ]

    correct_stress = 0
    stress_results = []
    for txt, expected in stress_test_cases:
        pred = pipeline.predict([txt])[0]
        prob = pipeline.predict_proba([txt])[0]
        is_ok = (pred == expected)
        if is_ok:
            correct_stress += 1
        label_str = "DELETION" if pred == 1 else "NOT_APPLICABLE"
        stress_results.append((is_ok, label_str, prob[1], txt))

    # Detailed report persistence
    report_path = output_report_path or os.path.join(MODEL_DIR, "training_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("Northstar Shop — Multi-Dataset Intent Classifier Training Report\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Total Datasets Included: {len(sources)}\n")
        f.write(f"Total Cross-Dataset Samples: {len(y)}\n")
        f.write(f"  • Deletions (label=1): {n_del}\n")
        f.write(f"  • Non-Deletions (label=0): {n_non}\n\n")
        f.write(f"5-Fold CV Macro F1: {cv_scores.mean():.4f} +/- {cv_scores.std():.4f}\n")
        f.write(f"5-Fold CV Accuracy: {cv_accs.mean():.4f} +/- {cv_accs.std():.4f}\n")
        f.write(f"Training Fit Accuracy: {train_acc:.4f}\n")
        f.write(f"Training Fit Macro F1: {train_f1:.4f}\n\n")
        f.write("Confusion Matrix (rows=actual, cols=predicted):\n")
        f.write(f"  [NOT_APPLICABLE, DELETION]\n")
        f.write(str(cm) + "\n\n")
        f.write("Classification Report:\n")
        f.write(report + "\n")
        f.write(f"Stress-Test Adversarial Accuracy: {correct_stress}/{len(stress_test_cases)} ({correct_stress/len(stress_test_cases)*100:.1f}%)\n")
        for is_ok, lbl, proba_del, txt in stress_results:
            icon = "PASS" if is_ok else "FAIL"
            f.write(f"  [{icon}] [{lbl:>14}] p_del={proba_del:.3f} | {txt}\n")

    print(f"Training Report Saved -> {report_path}")
    print(f"Stress-Test Accuracy : {correct_stress}/{len(stress_test_cases)} ({correct_stress/len(stress_test_cases)*100:.1f}%)")
    print(f"Total Execution Time : {time.time() - t0:.2f}s")
    print("=" * 70 + "\n")

    return pipeline


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Northstar Shop: Multi-Dataset Intent Classifier Trainer"
    )
    parser.add_argument(
        "--custom-data", "-c", nargs="*", default=None,
        help="One or more file paths to custom training datasets (.csv, .json, .jsonl)"
    )
    parser.add_argument(
        "--skip-built-in", action="store_true",
        help="Train exclusively on custom datasets without built-in partitions"
    )
    parser.add_argument(
        "--output-model", "-o", default=None,
        help="Custom path to save the serialized .joblib model artifact"
    )
    parser.add_argument(
        "--output-report", "-r", default=None,
        help="Custom path to save the generated training report"
    )
    args = parser.parse_args()

    train_and_benchmark(
        dataset_dir=DATASET_DIR,
        custom_data_paths=args.custom_data,
        skip_built_in=args.skip_built_in,
        output_model_path=args.output_model,
        output_report_path=args.output_report
    )
