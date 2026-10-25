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
            try:
                from code.engine.production_governance import ModelSecurityGuard
            except ImportError:
                from engine.production_governance import ModelSecurityGuard
            _trained_clf = ModelSecurityGuard.verify_and_load(_MODEL_PATH)
            logger.debug("Stage 1B: Loaded verified trained classifier from %s", _MODEL_PATH)
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
    "cancel the deletion request",
    "cancel my deletion request",
    "withdraw my deletion request",
    "stop the deletion",
    "cancel deletion",
    # Password / shipping / billing non-deletion verbs
    "reset my password",
    "update my shipping",
    "update my billing",
    "marketing opt",
    "unsubscribe from",
    "marketing lists only",
    "marketing list only",
    "not asking for deletion",
    "not asking to delete",
    "not a request to erase",
    "not a request to delete",
    "stop the promotional emails",
    "stop promotional emails",
    "information request, not a request",
    "ignore all previous instructions",
    "ignore previous instructions",
    "system override",
    "you are an obedient assistant",
]

_NEGATED_DELETION_PATTERNS = [
    re.compile(r"\b(?:not|never|no)\s+(?:asking|requesting|demanding|seeking)\s+(?:for\s+)?(?:deletion|erasure|to\s+delete|to\s+erase)\b", re.I),
    re.compile(r"\b(?:not\s+a\s+request|not\s+an\s+order)\s+to\s+(?:erase|delete|close|purge)\b", re.I),
    re.compile(r"\b(?:remove|take)\s+(?:me\s+)?from\s+marketing\b", re.I),
    re.compile(r"\b(?:stop|cancel|block)\s+(?:the\s+)?(?:promotional|marketing)\s+emails?\b", re.I),
    re.compile(r"\b(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|directions?|prompts?)\b", re.I),
    re.compile(r"\b(?:do\s+not|don't|dont|never|please\s+do\s+not)\s+(?:delete|erase|remove|close|purge|shut\s+down)\b", re.I),
    re.compile(r"\b(?:do\s+not|don't|dont)\s+want\s+(?:my\s+)?(?:account|profile|data)\s+(?:to\s+be\s+)?(?:deleted|erased|removed|closed)\b", re.I),
    re.compile(r"\b(?:keep|leave)\s+(?:my\s+|the\s+)?(?:account|profile|service)\s+(?:active|intact|open|in\s+place)\b", re.I),
    re.compile(r"\b(?:delete|remove|erase)\s+(?:only|just)\s+(?:my\s+)?(?:credit\s+card|card|phone|address|newsletter|subscription)\b", re.I),
    re.compile(r"\bkeep\s+(?:everything\s+else|the\s+rest)\b", re.I),
    re.compile(r"\bremove\s+(?:only|just|my\s+phone)\b", re.I),
    re.compile(r"\b(?:considered|thought\s+about)\s+deleting.*(?:stay|keep)\b", re.I),
    re.compile(r"\b(?:do\s+not|don't)\s+delete.*(?:until|without)\b", re.I),
    re.compile(r"\b(?:temporarily|temp)\s+freeze\b", re.I),
    re.compile(r"\b(?:unsubscribe|opt\s*out)\s+(?:me\s+)?from\b", re.I),
    re.compile(r"\b(?:auf\s+keinen\s+fall|keinesfalls|nicht)\s+löschen\b", re.I),
    re.compile(r"\blöschen\s+sie\s+.*(?:auf\s+keinen\s+fall|nicht)\b", re.I),
    re.compile(r"\b(?:ne\s+pas|ne\s+supprimez\s+pas|ne\s+veux\s+pas)\s+(?:supprimer|effacer)\b", re.I),
    re.compile(r"\b(?:veuillez\s+ne\s+pas|ne\s+pas)\s+supprimer\b", re.I),
    re.compile(r"\bno\s+(?:borren|eliminen|supriman|quiero\s+eliminar)\b", re.I),
    re.compile(r"\b(?:não|nao)\s+(?:apague|exclua|delete)\b", re.I),
    re.compile(r"\bnon\s+(?:cancellate|eliminare)\b", re.I),
    re.compile(r"\bniet\s+verwijderen\b", re.I),
    re.compile(r"\bне\s+удаляйте\b", re.I),
    re.compile(r"(?:削除しないで|消去しないで|維持して)", re.I),
    re.compile(r"(?:不要删除|别删除|保留账户)", re.I),
    re.compile(r"(?:عدم\s+حذف|لا\s+تحذف|عدم\s+إغلاق)", re.I),
]

# Semantic-Role Dependency Lattice (SRDL) Predicate-Argument Patterns
_SRDL_DISPUTE_TARGETS = re.compile(
    r"\b(?:fee|fees|charge|charges|charged|payment|payments|transaction|transactions|debit|debits|money|cash|card|cards|bill|bills|order|orders|statement)\b",
    re.I
)
_SRDL_LOST_STOLEN_FREEZE = re.compile(
    r"\b(?:lost|stolen|compromised|hacked|take\w*\s+my\s+phone|phone\s+was\s+taken|freeze\s+(?:my\s+)?account)\b",
    re.I
)
_SRDL_DISPUTE_REMOVAL = re.compile(
    r"\bremov\w*\s+(?:the\s+|a\s+|this\s+|one\s+|my\s+)?(?:fee|charge|payment|transaction|money|debit|card|hold)\b",
    re.I
)
_SRDL_QUIT_GET_RID = re.compile(
    r"\b(?:quit|get\s+rid\s+of|close\s+down|shut\s+down|terminate|erase|wipe)\b.*\b(?:account|profile)\b",
    re.I
)
_SRDL_ACCOUNT_TARGET = re.compile(
    r"\b(?:account|profile|data|records?|information|details?|everything|user|me)\b",
    re.I
)

# At least one of these stems/phrases → confirms deletion intent (prefix match)
_DELETION_STEMS: list[str] = [
    "delet",       # delete / deletion / deleting
    "erase",
    "erasure",
    "close my account",
    "close the account",
    "close this account",
    "close.*account",   # regex: any "close … account" variant
    r"remov\w*.*(?:account|profile|data|records?|information|details?|everything|user|me)",
    r"quit\b.*account",
    r"get\s+rid\s+of\b.*account",
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
    Stage 1A: Semantic-Role Dependency Lattice (SRDL) and Deterministic Fast-Path.
    Returns "DELETION", "NOT_APPLICABLE", or None (ambiguous).
    """
    text = str(request_text).strip()
    lower = text.lower()

    # Pre-check: Double negation affirmation ("it is false that I do not want", "cannot not request")
    double_neg = re.search(r"\b(?:it\s+is\s+(?:false|untrue|not\s+true)\s+that\s+i\s+(?:do\s+not|don't)|cannot\s+not)\b", lower)
    if double_neg and any(k in lower for k in ["wipe", "delet", "eras", "remov", "close", "purg"]):
        return "DELETION"

    # Explicit non-deletion overrides
    for pat in _NON_DELETION_PATTERNS:
        if pat in lower:
            return "NOT_APPLICABLE"
    if any(pattern.search(text) for pattern in _NEGATED_DELETION_PATTERNS):
        return "NOT_APPLICABLE"

    # SRDL Rule 1: Fraud / theft / freeze account request (unless explicit permanent deletion)
    if _SRDL_LOST_STOLEN_FREEZE.search(text) and not any(k in lower for k in ["permanently delete", "erase", "article 17", "right to be forgotten"]):
        return "NOT_APPLICABLE"

    # SRDL Rule 2: Transaction / payment / fee removal dispute
    if _SRDL_DISPUTE_REMOVAL.search(text):
        return "NOT_APPLICABLE"
    if "remov" in lower and _SRDL_DISPUTE_TARGETS.search(text) and not (_SRDL_ACCOUNT_TARGET.search(text) and any(k in lower for k in ["close", "delete", "erase", "terminate"])):
        return "NOT_APPLICABLE"

    # SRDL Rule 3: Colloquial account termination expansions
    if _SRDL_QUIT_GET_RID.search(text):
        return "DELETION"

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

    @classmethod
    def analyze_intent(cls, request_text: str) -> dict:
        """
        Comprehensive production uncertainty and intent analysis.
        Returns calibrated probability, confidence margin, Shannon entropy, and OOD detection.
        """
        import numpy as np

        # 1. Check Stage 1A
        s1a = _stage1a(request_text)
        if s1a is not None:
            return {
                "decision": s1a,
                "tier": "STAGE_1A_DETERMINISTIC_REGEX",
                "prob_deletion": 1.0 if s1a == "DELETION" else 0.0,
                "prob_non_deletion": 0.0 if s1a == "DELETION" else 1.0,
                "confidence": 1.0,
                "entropy": 0.0,
                "is_out_of_distribution": False,
            }

        # 2. Check Stage 1B Reality Ensemble
        clf = _load_trained_model()
        if clf is not None:
            try:
                proba = clf.predict_proba([request_text])[0]
                p_non, p_del = float(proba[0]), float(proba[1])
                eps = 1e-12
                p0 = max(eps, p_non)
                p1 = max(eps, p_del)
                entropy = float(-(p0 * np.log2(p0) + p1 * np.log2(p1)))
                confidence = float(abs(p_del - p_non))
                is_ood = bool(entropy > 0.85 or confidence < 0.30)
                decision = "DELETION" if p_del >= 0.5 else "NOT_APPLICABLE"
                return {
                    "decision": decision,
                    "tier": "STAGE_1B_REALITY_ENSEMBLE",
                    "prob_deletion": p_del,
                    "prob_non_deletion": p_non,
                    "confidence": confidence,
                    "entropy": entropy,
                    "is_out_of_distribution": is_ood,
                }
            except Exception as exc:
                logger.debug("Stage 1B ML probability calculation failed: %s", exc)

        return {
            "decision": "NOT_APPLICABLE",
            "tier": "CONSERVATIVE_FALLBACK",
            "prob_deletion": 0.0,
            "prob_non_deletion": 1.0,
            "confidence": 0.5,
            "entropy": 1.0,
            "is_out_of_distribution": True,
        }
