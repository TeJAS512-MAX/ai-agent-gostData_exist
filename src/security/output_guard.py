import re
from typing import Tuple, List

PROMPT_LEAKAGE_SIGNATURES = [
    re.compile(r"you are an autonomous triage agent", re.IGNORECASE),
    re.compile(r"policy context", re.IGNORECASE),
    re.compile(r"--- policy context ---", re.IGNORECASE),
    re.compile(r"untrusted_user_input", re.IGNORECASE),
    re.compile(r"secret_key|api_key|system_prompt", re.IGNORECASE)
]

UNAUTHORIZED_PROMISES = [
    re.compile(r"i have refunded (your|all) (money|amount|\$\d+)", re.IGNORECASE),
    re.compile(r"i have granted you (admin|root|unlimited) access", re.IGNORECASE),
    re.compile(r"your ban has been permanently lifted", re.IGNORECASE)
]

class OutputGuardrail:
    """Pre-flight verification for agent responses to eliminate prompt leaks and unauthorized promises."""

    @staticmethod
    def verify_response(response_text: str) -> Tuple[bool, List[str], str]:
        violations = []
        sanitized = response_text

        # 1. Check for prompt leakage
        for sig in PROMPT_LEAKAGE_SIGNATURES:
            if sig.search(response_text):
                violations.append("SYSTEM_PROMPT_LEAK_PREVENTED")
                sanitized = "I cannot disclose internal system prompts or policies."
                return False, violations, sanitized

        # 2. Check for unauthorized action promises
        for sig in UNAUTHORIZED_PROMISES:
            if sig.search(response_text):
                violations.append("UNAUTHORIZED_ACTION_CLAIM_BLOCKED")
                sanitized = "Your request has been routed to human tier-3 support for formal review."
                return False, violations, sanitized

        return True, [], sanitized

