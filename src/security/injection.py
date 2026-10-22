import re
import base64
from typing import List, Tuple, Set

# Zero-width and control characters often used to evade keyword filters
ZERO_WIDTH_CHARS = re.compile(r"[\u200B-\u200D\uFEFF\u00A0\u200E\u200F\u202A-\u202E]")

# Common leetspeak substitutions
LEET_DICT = {
    '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's',
    '7': 't', '@': 'a', '$': 's', '!': 'i'
}

# Advanced multi-vector adversarial patterns
INJECTION_SUITES = {
    "DIRECT_OVERRIDE": [
        r"ignore\s+(all\s+)?(previous|prior|above|system)\s+(instructions|prompts|rules|commands)",
        r"disregard\s+(the\s+)?(system|rules|previous|safety)",
        r"system\s*override",
        r"reset\s+all\s+rules",
        r"you\s+are\s+now\s+(unrestricted|free|freed|unfiltered)",
    ],
    "DEVELOPER_MODE_SPOOFING": [
        r"you\s+are\s+now\s+(in\s+)?(developer|admin|debug|jailbreak|god|superuser)\s+mode",
        r"enable\s+(dev|debug|god|unrestricted)\s+mode",
        r"act\s+as\s+a\s+(dan|developer\s+mode|unfiltered\s+ai)",
        r"simulate\s+unrestricted\s+mode",
    ],
    "PROMPT_LEAKAGE": [
        r"(output|repeat|print|reveal|show|display)\s+(your\s+)?(system\s+prompt|initial\s+instructions|secret\s+key|internal\s+guidelines)",
        r"what\s+are\s+your\s+(exact\s+)?(instructions|system\s+prompts)",
        r"dump\s+(all\s+)?prompts",
    ],
    "PRIVILEGE_ESCALATION": [
        r"sudo\s+(approve|grant|execute|escalate|refund)",
        r"override\s+(authorization|permission|limit)",
        r"grant\s+(me\s+)?(admin|root|superuser|tier\s*3)\s+access",
        r"force\s+(payout|refund|approval)",
    ],
    "DELIMITER_HIJACKING": [
        r"</untrusted_user_input>",
        r"<system>",
        r"</system>",
        r"\[INST\]",
        r"\[/INST\]",
        r"```(system|admin|override)",
    ]
}

class InjectionDetector:
    """Multi-stage adversarial injection detector with deobfuscation and multi-vector pattern analysis."""

    @staticmethod
    def normalize_text(text: str) -> str:
        """Removes zero-width characters and normalizes leetspeak."""
        # 1. Strip zero-width chars
        cleaned = ZERO_WIDTH_CHARS.sub("", text)
        # 2. Leet decoding
        normalized = "".join(LEET_DICT.get(c.lower(), c.lower()) for c in cleaned)
        # 3. Collapse multiple whitespace and dashes
        normalized = re.sub(r"[\s\-_.]+", " ", normalized)
        return normalized

    @classmethod
    def inspect(cls, raw_text: str) -> Tuple[bool, List[str], float]:
        """
        Inspects text for prompt injection vectors.
        Returns: (is_safe, attack_vectors_detected, threat_score)
        """
        if not raw_text or not raw_text.strip():
            return True, [], 0.0

        normalized = cls.normalize_text(raw_text)
        detected_vectors: Set[str] = set()

        # 1. Pattern checks across normalized text
        for category, patterns in INJECTION_SUITES.items():
            for p in patterns:
                if re.search(p, normalized, re.IGNORECASE) or re.search(p, raw_text, re.IGNORECASE):
                    detected_vectors.add(category)
                    break

        # 2. Inspect potential base64 embedded payload
        base64_candidates = re.findall(r"[A-Za-z0-9+/]{20,}={0,2}", raw_text)
        for candidate in base64_candidates:
            try:
                decoded = base64.b64decode(candidate).decode("utf-8", errors="ignore")
                decoded_norm = cls.normalize_text(decoded)
                for category, patterns in INJECTION_SUITES.items():
                    for p in patterns:
                        if re.search(p, decoded_norm, re.IGNORECASE):
                            detected_vectors.add(f"{category}_BASE64_OBFUSCATED")
                            break
            except Exception:
                pass

        threat_score = min(1.0, len(detected_vectors) * 0.35)
        is_safe = len(detected_vectors) == 0

        return is_safe, sorted(list(detected_vectors)), round(threat_score, 2)
