import hashlib
from typing import Tuple
from src.schema import SecurityAssessment, ThreatLevel
from src.security.pii import PIIRedactor
from src.security.injection import InjectionDetector
from src.security.output_guard import OutputGuardrail

class SecurityGuardrails:
    """
    Enterprise defense-in-depth safety barrier.
    Features:
    1. Zero-width character & obfuscation stripping
    2. PII, credit card, and API credential redaction
    3. Multi-vector prompt injection & jailbreak detection
    4. Cryptographic SHA-256 audit fingerprinting
    5. Strict prompt boundary encapsulation
    6. Post-generation output guardrail
    """

    @classmethod
    def inspect(cls, raw_text: str) -> SecurityAssessment:
        if not raw_text or not raw_text.strip():
            return SecurityAssessment(
                is_safe=True,
                threat_level=ThreatLevel.SAFE,
                sanitized_input=""
            )

        # 1. PII Redaction
        redacted_text, pii_findings = PIIRedactor.redact(raw_text)

        # 2. Injection & Jailbreak Analysis
        is_safe, attack_vectors, threat_score = InjectionDetector.inspect(redacted_text)

        # Determine Threat Level
        if not is_safe:
            if threat_score >= 0.7 or "DIRECT_OVERRIDE" in attack_vectors:
                threat_level = ThreatLevel.CRITICAL
            elif threat_score >= 0.4:
                threat_level = ThreatLevel.HIGH
            else:
                threat_level = ThreatLevel.MEDIUM
        elif pii_findings:
            threat_level = ThreatLevel.LOW
        else:
            threat_level = ThreatLevel.SAFE

        flagged_reason = None
        if not is_safe:
            flagged_reason = f"Security Violation: Detected attack vectors [{', '.join(attack_vectors)}]"
        elif pii_findings:
            flagged_reason = f"PII Shield Active: Redacted sensitive items [{', '.join(pii_findings)}]"

        # 3. Cryptographic Audit Hash
        audit_hash = hashlib.sha256(redacted_text.encode("utf-8")).hexdigest()[:16]

        return SecurityAssessment(
            is_safe=is_safe,
            threat_level=threat_level,
            attack_vectors=attack_vectors,
            pii_detected=pii_findings,
            flagged_reason=flagged_reason,
            sanitized_input=redacted_text,
            audit_hash=audit_hash
        )

    @classmethod
    def wrap_user_content(cls, content: str) -> str:
        """
        Hardened XML boundary isolation to prevent indirect prompt injection.
        """
        # Neutralize any rogue closing tags inside user content
        sanitized = content.replace("</untrusted_user_input>", "&lt;/untrusted_user_input&gt;")
        return (
            "<untrusted_user_input security_hardened=\"true\">\n"
            f"{sanitized}\n"
            "</untrusted_user_input>"
        )

    @classmethod
    def verify_output(cls, response_text: str) -> Tuple[bool, str]:
        """Runs the post-generation guardrail on the agent's drafted response."""
        is_valid, violations, clean_text = OutputGuardrail.verify_response(response_text)
        return is_valid, clean_text
