"""
================================================================================
 Northstar Shop — LLM Client & Neural Transducer Adapter
================================================================================

Provides unified, robust access to frontier & free-tier LLM models via
OpenRouter / Google Gemini for:
  1. Semantic Intent Classification (Stage 1C)
  2. Evidence Cross-Verification & Quote Grounding (Stage 4)
  3. Executive Compliance Briefing & Audit Justifications (Stages 5/6)

Automatically falls back to local symbolic inference if API keys are absent
or network requests encounter rate limits / timeouts.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Try loading .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class LLMClient:
    """
    Unified LLM Client connecting to OpenRouter / Gemini API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 20,
    ):
        self.api_key = (
            api_key
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("GEMINI_API_KEY")
        )
        self.model = (
            model
            or os.getenv("OPENROUTER_MODEL")
            or "openrouter/free"
        )
        self.timeout = timeout
        self.is_active = bool(self.api_key)

        if self.is_active:
            masked = self.api_key[:8] + "..." + self.api_key[-4:] if len(self.api_key) > 12 else "***"
            logger.info("LLMClient initialized: Provider=OpenRouter Model=%s Key=%s", self.model, masked)
        else:
            logger.debug("LLMClient initialized in offline/symbolic mode (no API key detected)")

    def call_chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 300,
        temperature: float = 0.0,
    ) -> Optional[str]:
        """
        Send a chat completion request to the OpenRouter API.
        """
        if not self.api_key:
            return None

        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/TeJAS512-MAX/ai-agent-hackerank",
            "X-Title": "Northstar Shop Deletion Audit Agent",
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    return content.strip() if content else None
        except Exception as exc:
            logger.warning("LLM API call failed (%s): %s", type(exc).__name__, exc)
            return None

    def classify_intent(self, request_text: str) -> Optional[Dict[str, Any]]:
        """
        Classifies request_text using the LLM for ambiguous edge cases.
        Returns dict with is_deletion (bool), confidence (float), reasoning (str).
        """
        prompt = (
            "You are an AI Privacy Compliance Auditor. Analyze the customer request text below.\n"
            "Determine if the user is asking to DELETE / CLOSE / ERASE their account and personal data, "
            "or if this is NOT a deletion request (e.g. password reset, email update, shipping address change, "
            "or a GDPR Article 15 data export request where they want to KEEP their account active).\n\n"
            f"Request Text:\n\"{request_text[:1200]}\"\n\n"
            "Reply with a pure JSON object in this format:\n"
            "{\n"
            "  \"is_deletion\": true,\n"
            "  \"confidence\": 0.95,\n"
            "  \"category\": \"FULL_ERASURE\",\n"
            "  \"reasoning\": \"Brief explanation\"\n"
            "}"
        )

        resp = self.call_chat(
            messages=[
                {"role": "system", "content": "You are a strict data-privacy legal auditor. Output valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250,
            temperature=0.0
        )

        import re
        if not resp:
            return None

        # Robust JSON extraction
        m = re.search(r"\{.*\}", resp, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return None

    def generate_audit_narrative(
        self,
        case_id: str,
        email: str,
        deletion_status: str,
        steps: List[Dict[str, Any]],
        request_text: str = "",
    ) -> str:
        """
        Synthesizes an executive compliance summary and justification briefing.
        """
        if not self.is_active:
            return (
                f"[Local Symbolic Analysis] Case {case_id} ({email}) audited with status {deletion_status}. "
                f"Generated {len(steps)} deterministic policy findings, remediation actions, and verification checks."
            )

        prompt = (
            f"You are the Chief Privacy Officer reviewing an automated audit report.\n"
            f"Case ID: {case_id}\n"
            f"User Email: {email}\n"
            f"Audit Status: {deletion_status}\n"
            f"Customer Request: \"{request_text[:300]}\"\n"
            f"Audit Findings & Steps ({len(steps)} steps):\n"
            f"{json.dumps(steps[:8], indent=2)}\n\n"
            "Provide a concise, professional 2-3 sentence executive briefing explaining:\n"
            "1. Why the deletion status is COMPLETE or INCOMPLETE (highlighting specific ghost data or active risks if any).\n"
            "2. What mandatory legal remediation actions must be executed under deletion_rules.csv."
        )

        resp = self.call_chat(
            messages=[
                {"role": "system", "content": "You are an executive privacy compliance officer. Speak with precision and authority."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.2
        )

        return resp or (
            f"Case {case_id} resolved with status {deletion_status}. "
            f"The 7-stage NSTVE pipeline compiled {len(steps)} verified steps."
        )
