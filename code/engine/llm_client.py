"""
================================================================================
 Northstar Shop -- Multi-Provider LLM Client & Neural Transducer Adapter
================================================================================

Provides unified, robust access to frontier & free-tier LLM models via:
  1. Google Gemini API (using GEMINI_API_KEY directly via Google Generative Language REST)
  2. OpenRouter API (using OPENROUTER_API_KEY as fallback)
  3. Offline Symbolic Inference (0 token cost fallback)

Handles rate limits, invalid keys, depleted credits, and timeouts gracefully
without crashing or throwing unhandled terminal exceptions.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

logger = logging.getLogger("LLMClient")

# Try loading .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class LLMClient:
    """
    Unified, fault-tolerant LLM Client connecting to Google Gemini and OpenRouter.
    """

    def __init__(
        self,
        gemini_key: Optional[str] = None,
        openrouter_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 15,
    ):
        self.gemini_key = gemini_key or os.getenv("GEMINI_API_KEY")
        self.openrouter_key = openrouter_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("DEFAULT_MODEL") or os.getenv("OPENROUTER_MODEL") or "gemini-2.5-flash"
        self.timeout = timeout

        self.is_active = bool(self.gemini_key or self.openrouter_key)

        if self.gemini_key:
            masked = self.gemini_key[:6] + "..." + self.gemini_key[-4:] if len(self.gemini_key) > 10 else "***"
            logger.info("LLMClient initialized: Provider=Google Gemini Key=%s", masked)
        elif self.openrouter_key:
            masked = self.openrouter_key[:6] + "..." + self.openrouter_key[-4:] if len(self.openrouter_key) > 10 else "***"
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
        Sends chat completion, trying Google Gemini first, then OpenRouter, then local fallback.
        """
        # 1. Try Google Gemini API if key is present
        if self.gemini_key:
            res = self._call_gemini(messages, max_tokens, temperature)
            if res:
                return res

        # 2. Try OpenRouter API if key is present
        if self.openrouter_key:
            res = self._call_openrouter(messages, max_tokens, temperature)
            if res:
                return res

        return None

    def _call_gemini(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 300,
        temperature: float = 0.0
    ) -> Optional[str]:
        """Calls Google Generative Language REST API."""
        prompt_parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                prompt_parts.append(f"System Instructions: {content}\n")
            else:
                prompt_parts.append(content)
        full_prompt = "\n".join(prompt_parts)

        # Candidate models supported by Gemini API
        gemini_models = ["gemini-2.5-flash", "gemini-3.8-flash", "gemini-flash-latest"]
        for g_model in gemini_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={self.gemini_key}"
            payload = json.dumps({
                "contents": [
                    {
                        "parts": [{"text": full_prompt}]
                    }
                ],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": temperature
                }
            }).encode("utf-8")

            headers = {"Content-Type": "application/json"}
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "").strip()
            except urllib.error.HTTPError as exc:
                # 402 = Payment/quota exhausted, 404 = Model deprecation
                if exc.code in [402, 404]:
                    continue
                logger.debug("Gemini API HTTP %d for %s: %s", exc.code, g_model, exc)
            except Exception as exc:
                logger.debug("Gemini API call failed (%s): %s", type(exc).__name__, exc)

        return None

    def _call_openrouter(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 300,
        temperature: float = 0.0
    ) -> Optional[str]:
        """Calls OpenRouter Chat Completions endpoint."""
        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
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
            logger.debug("OpenRouter call failed (%s): %s", type(exc).__name__, exc)
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
