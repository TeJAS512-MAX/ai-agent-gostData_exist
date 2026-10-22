import re
from typing import Tuple
from src.schema import SecurityAssessment

# High-risk adversarial injection signatures
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
    r"disregard\s+(the\s+)?(system|rules|previous)",
    r"you\s+are\s+now\s+(in\s+)?(developer|admin|debug|jailbreak|god)\s+mode",
    r"system\s*override",
    r"output\s+(your\s+)?(system\s+prompt|initial\s+instructions|secret\s+key)",
    r"reveal\s+(internal\s+)?(instructions|configuration|prompt)",
    r"bypass\s+(policy|safety|security|verification)",
    r"act\s+as\s+a\s+(dan|unrestricted|evil|unfiltered)",
    r"sudo\s+approve",
    r"override\s+authorization"
]

COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

class SecurityGuardrails:
    """Multi-layer defensive filter protecting agent from prompt injection attacks."""

    @staticmethod
    def inspect(text: str) -> SecurityAssessment:
        if not text:
            return SecurityAssessment(is_safe=True, sanitized_input="")

        # Check regex signatures
        for pattern in COMPILED_PATTERNS:
            match = pattern.search(text)
            if match:
                return SecurityAssessment(
                    is_safe=False,
                    flagged_reason=f"Adversarial prompt injection pattern detected: '{match.group(0)}'",
                    sanitized_input=text
                )

        # Delimiter & payload sanitization: Strip null bytes and control chars
        sanitized = "".join(ch for ch in text if ch.isprintable() or ch in "\n\r\t")

        return SecurityAssessment(
            is_safe=True,
            flagged_reason=None,
            sanitized_input=sanitized
        )

    @staticmethod
    def wrap_user_content(content: str) -> str:
        """Contain user content in clear demarcation tags to mitigate indirect injection."""
        return f"<untrusted_user_input>\n{content}\n</untrusted_user_input>"

