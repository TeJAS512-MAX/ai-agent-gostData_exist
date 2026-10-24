"""
Stage 1: Semantic Intent Gate & Fast-Path Triage
=================================================
Classifies deletion_requests.request_text to determine whether a genuine
account-deletion was requested.

Strategy:
  Stage 1A (0-Token Regex) -- deterministic keyword / negative-constraint patterns.
  Stage 1B (LLM Micro-Classifier Fallback) -- invoked ONLY for genuinely ambiguous
  text that Stage 1A cannot confidently classify.  Requires OPENROUTER_API_KEY or
  GEMINI_API_KEY environment variable.  Falls back gracefully to NOT_APPLICABLE if
  the network call fails.
"""

import re
import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

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

    # Explicit deletion keywords
    if _DELETION_REGEX.search(text):
        return "DELETION"

    return None  # ambiguous – escalate to Stage 1B


def _stage1b_llm(request_text: str) -> str:
    """
    Lightweight LLM binary classifier.  Returns "DELETION" or "NOT_APPLICABLE".
    Falls back to NOT_APPLICABLE on any error.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("Stage 1B: No API key found; defaulting to NOT_APPLICABLE for ambiguous text.")
        return "NOT_APPLICABLE"

    try:
        import urllib.request
        prompt = (
            "You are a binary classifier. Answer with exactly one word: "
            "DELETION if the customer is requesting account/data deletion, "
            "NOT_APPLICABLE otherwise.\n\n"
            f"Request text:\n{request_text[:1000]}\n\nAnswer:"
        )
        payload = json.dumps({
            "model": "google/gemini-2.5-flash",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 5,
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        answer = data["choices"][0]["message"]["content"].strip().upper()
        if "NOT" in answer:
            return "NOT_APPLICABLE"
        return "DELETION"
    except Exception as exc:
        logger.warning("Stage 1B LLM call failed (%s); defaulting to NOT_APPLICABLE.", exc)
        return "NOT_APPLICABLE"


class IntentGate:
    """
    Stage 1: Intent classification with 0-token fast path and LLM fallback.
    """

    def classify(self, request_text: str, use_llm_fallback: bool = False) -> str:
        """
        Returns "DELETION" or "NOT_APPLICABLE".
        """
        result = _stage1a(request_text)
        if result is not None:
            return result
        # Ambiguous: use LLM fallback only when explicitly enabled
        if use_llm_fallback:
            return _stage1b_llm(request_text)
        # Conservative default for production: treat ambiguous as NOT_APPLICABLE
        return "NOT_APPLICABLE"
