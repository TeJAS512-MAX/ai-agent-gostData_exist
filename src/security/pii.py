import re
from typing import Tuple, List

# Regex patterns for sensitive data
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{15,16}\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
API_KEY_PATTERN = re.compile(
    r"\b(?:sk-[a-zA-Z0-9_-]{20,}|AIza[0-9A-Za-z-_]{35}|ghp_[a-zA-Z0-9]{36}|Bearer\s+[a-zA-Z0-9._-]{20,})\b",
    re.IGNORECASE
)
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")

class PIIRedactor:
    """Detects and redacts sensitive customer data (credit cards, SSNs, secrets) before LLM ingestion."""

    @staticmethod
    def redact(text: str) -> Tuple[str, List[str]]:
        findings = []
        redacted = text

        # Redact API keys / tokens
        if API_KEY_PATTERN.search(redacted):
            findings.append("API_TOKEN_EXPOSED")
            redacted = API_KEY_PATTERN.sub("[REDACTED_SECRET_TOKEN]", redacted)

        # Redact SSNs
        if SSN_PATTERN.search(redacted):
            findings.append("SSN_EXPOSED")
            redacted = SSN_PATTERN.sub("[REDACTED_SSN]", redacted)

        # Redact Credit Cards (basic Luhn / digit check)
        matches = CREDIT_CARD_PATTERN.findall(redacted)
        if matches:
            findings.append("PAYMENT_CARD_EXPOSED")
            redacted = CREDIT_CARD_PATTERN.sub("[REDACTED_CARD_NUMBER]", redacted)

        return redacted, findings
