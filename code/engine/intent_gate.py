"""
Stage 1: Semantic Intent Gate & Fast-Path Triage
=================================================
Classifies deletion_requests.request_text to determine whether a genuine
account-deletion was requested.

Strategy:
  Stage 1A (0-Token Regex)  -- deterministic keyword / negative-constraint patterns.
  Stage 1B (Trained ML)     -- TF-IDF + Logistic Regression classifier trained on
                               public labelled samples + synthetic examples.
                               Loaded from code/engine/trained_model/intent_classifier.joblib.
  Stage 1C (LLM Fallback)   -- invoked ONLY if both 1A and 1B are inconclusive.
                               Requires OPENROUTER_API_KEY or GEMINI_API_KEY env var.
"""

import re
import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Trained model loader ──────────────────────────────────────────────────────

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "trained_model", "intent_classifier.joblib")
_trained_clf = None

def _load_trained_model():
    global _trained_clf
    if _trained_clf is not None:
        return _trained_clf
    if os.path.exists(_MODEL_PATH):
        try:
            import joblib
            _trained_clf = joblib.load(_MODEL_PATH)
            logger.debug("Stage 1B: Loaded trained classifier from %s", _MODEL_PATH)
        except Exception as exc:
            logger.warning("Stage 1B: Failed to load trained model: %s", exc)
    return _trained_clf

# ── Stage 1A: Zero-token deterministic patterns ──────────────────────────────

# Any of these phrases in the lowercase request → NOT_APPLICABLE immediately
_NON_DELETION_PATTERNS: list[str] = [
    "leave the account active",
    "keep the account as it is",
    "leave my profile and purchase history in place",
    "continue using the service",
    "don't delete or change anything",
    "do not delete or change anything",
    "without removing any of my records",
    "without deleting",
    "keinesfalls löschen",
    "keinesfalls loeschen",
    "do not close",
    "please do not delete",
    "bitte nicht löschen",
    "ne pas supprimer",
    "no eliminar",
    # GDPR Art-15 data-access only (not erasure)
    "article 15",
    "access to my data",
    "copy of my data",
    "data portability",
    "export my data",
    "download my data",
    # Password / shipping / billing non-deletion verbs
    "reset my password",
    "update my shipping",
    "update my billing",
    "marketing opt",
    "unsubscribe from",
]

_NEGATED_DELETION_PATTERNS = [
    re.compile(
        r"\b(?:i\s+)?(?:do\s+not|don't|dont)\s+want\s+"
        r"(?:my\s+)?(?:account|profile|data)\s+(?:to\s+be\s+)?"
        r"(?:deleted|erased|removed|closed)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bno\s+(?:quiero|queremos)\s+(?:eliminar|borrar|suprimir)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\bje\s+ne\s+(?:veux|souhaite)\s+pas\s+(?:supprimer|effacer)\b",
        flags=re.IGNORECASE,
    ),
]

# At least one of these stems/phrases → confirms deletion intent (prefix match)
_DELETION_STEMS: list[str] = [
    "delet",       # delete / deletion / deleting
    "erase",
    "erasure",
    "close my account",
    "close the account",
    "close this account",
    "close.*account",   # regex: any "close … account" variant
    "remov",
    "purg",
    "destroy",
    "right to be forgotten",
    "shut down my account",
    "cancel my account",
    "cancel account",
    "profile is gone",
    "confirm that the profile is gone",
    # Multilingual keywords
    "exclus",      # Portuguese
    "suppr",       # French
    "eliminac",    # Spanish
    "eliminar",
    "löschen",
    "loeschen",
    "löschung",
    "削除",
    "消去",
    "삭제",
    "해지",
    "탈퇴",
    "حذف",
    "gdpr.*article 17",
]

_DELETION_REGEX = re.compile(
    "|".join(_DELETION_STEMS), flags=re.IGNORECASE | re.UNICODE
)


def _stage1a(request_text: str) -> Optional[str]:
    """
    Returns "DELETION", "NOT_APPLICABLE", or None (ambiguous).
    """
    text = str(request_text).strip()
    lower = text.lower()

    # Explicit non-deletion overrides
    for pat in _NON_DELETION_PATTERNS:
        if pat in lower:
            return "NOT_APPLICABLE"
    if any(pattern.search(text) for pattern in _NEGATED_DELETION_PATTERNS):
        return "NOT_APPLICABLE"

    # Explicit deletion keywords
    if _DELETION_REGEX.search(text):
        return "DELETION"

    return None  # ambiguous – escalate to Stage 1B


def _stage1b_ml(request_text: str) -> Optional[str]:
    """
    Stage 1B: TF-IDF + Logistic Regression classifier.
    Returns "DELETION", "NOT_APPLICABLE", or None (low confidence → escalate).
    """
    clf = _load_trained_model()
    if clf is None:
        return None
    try:
        proba = clf.predict_proba([request_text])[0]
        # proba[0] = NOT_APPLICABLE, proba[1] = DELETION
        if proba[1] >= 0.65:
            return "DELETION"
        if proba[0] >= 0.65:
            return "NOT_APPLICABLE"
        return None  # low confidence — escalate to 1C
    except Exception as exc:
        logger.debug("Stage 1B ML inference failed: %s", exc)
        return None


def _stage1c_llm(request_text: str) -> str:
    """
    Stage 1C: LLM micro-classifier for truly ambiguous text via LLMClient.
    Returns "DELETION" or "NOT_APPLICABLE". Falls back to NOT_APPLICABLE on error.
    """
    try:
        from code.engine.llm_client import LLMClient
    except ImportError:
        try:
            from engine.llm_client import LLMClient
        except ImportError:
            return "NOT_APPLICABLE"

    client = LLMClient()
    if not client.is_active:
        return "NOT_APPLICABLE"

    result = client.classify_intent(request_text)
    if result and isinstance(result, dict):
        return "DELETION" if result.get("is_deletion") else "NOT_APPLICABLE"

    # Fallback to simple completion if json parse fails
    resp = client.call_chat([
        {"role": "user", "content": f"Is this a customer account deletion request? Answer DELETION or NOT_APPLICABLE.\nText: {request_text[:800]}"}
    ], max_tokens=10)

    if resp and "NOT" in resp.upper():
        return "NOT_APPLICABLE"
    elif resp and "DELET" in resp.upper():
        return "DELETION"

    return "NOT_APPLICABLE"


class IntentGate:
    """
    Stage 1: Intent classification with 3-tier pipeline:
      1A — 0-token regex (deterministic, instant)
      1B — Trained TF-IDF + LR classifier
      1C — LLM micro-classifier (only for low-confidence ambiguous text)
    """

    def __init__(self):
        # Pre-load trained model at construction time
        _load_trained_model()

    def classify(self, request_text: str, use_llm_fallback: bool = True) -> str:
        """
        Returns "DELETION" or "NOT_APPLICABLE".
        """
        # Stage 1A: 0-token regex fast path
        result = _stage1a(request_text)
        if result is not None:
            return result

        # Stage 1B: Trained ML classifier
        result = _stage1b_ml(request_text)
        if result is not None:
            return result

        # Stage 1C: Neural LLM fallback (when API key is configured)
        if use_llm_fallback:
            return _stage1c_llm(request_text)

        # Conservative default: treat low-confidence ambiguous text as NOT_APPLICABLE
        return "NOT_APPLICABLE"
