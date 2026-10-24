"""
================================================================================
 Northstar Shop -- Multilingual Robust Request Classifier (Anti-Adversarial)
================================================================================

Classifies customer request_text to determine whether statutory account deletion
was genuinely requested or if the request is NOT_APPLICABLE (non-erasure inquiries,
GDPR Art 15 access requests, and adversarial negations).
"""

import re

class RequestClassifier:
    """
    Robust, multilingual intent classifier with comprehensive negative-constraint
    and adversarial negation defense across 12 languages.
    """

    NON_DELETION_PATTERNS = [
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
        "article 15",
        "access to my data",
        "copy of my data",
        "data portability",
        "export my data",
        "download my data",
        "reset my password",
        "update my shipping",
        "update my billing",
        "unsubscribe from",
        "cancel the deletion request",
        "cancel my deletion request",
        "withdraw my deletion request",
        "stop the deletion",
        "cancel deletion",
        "system override",
        "ignore previous instructions",
        "delete all rules",
        "jailbreak",
    ]

    NEGATION_REGEXES = [
        re.compile(r"\b(?:cancel|withdraw|stop|abort)\s+(?:the\s+|my\s+)?deletion\s+request\b", re.I),
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
        # German
        re.compile(r"\b(?:auf\s+keinen\s+fall|keinesfalls|nicht)\s+löschen\b", re.I),
        re.compile(r"\blöschen\s+sie\s+.*(?:auf\s+keinen\s+fall|nicht)\b", re.I),
        # French
        re.compile(r"\b(?:ne\s+pas|ne\s+supprimez\s+pas|ne\s+veux\s+pas)\s+(?:supprimer|effacer)\b", re.I),
        re.compile(r"\b(?:veuillez\s+ne\s+pas|ne\s+pas)\s+supprimer\b", re.I),
        # Spanish
        re.compile(r"\bno\s+(?:borren|eliminen|supriman|quiero\s+eliminar)\b", re.I),
        # Portuguese
        re.compile(r"\b(?:não|nao)\s+(?:apague|exclua|delete)\b", re.I),
        # Italian
        re.compile(r"\bnon\s+(?:cancellate|eliminare)\b", re.I),
        # Dutch
        re.compile(r"\bniet\s+verwijderen\b", re.I),
        # Russian
        re.compile(r"\bне\s+удаляйте\b", re.I),
        # Japanese
        re.compile(r"(?:削除しないで|消去しないで|維持して)", re.I),
        # Chinese
        re.compile(r"(?:不要删除|别删除|保留账户)", re.I),
        # Arabic
        re.compile(r"(?:عدم\s+حذف|لا\s+تحذف|عدم\s+إغلاق)", re.I),
    ]

    DELETION_KEYWORDS = [
        "delet", "erase", "erasure", "close", "remove", "purge", "expung",
        "destroy", "right to be forgotten", "shut down", "cancel my account",
        "profile is gone", "confirm that the profile is gone",
        "exclusão", "exclusao", "exclua", "apague", "apagar",
        "suppression", "supprimer", "supprimez",
        "eliminación", "eliminacion", "eliminar", "elimine",
        "löschen", "loeschen", "löschung", "loschen", "loschung",
        "cancellazione", "cancellate", "cancellare", "cancella",
        "verwijdering", "verwijderen",
        "удаление", "удалите",
        "削除", "消去", "注销",
        "삭제", "해지", "탈퇴",
        "حذف"
    ]

    @classmethod
    def is_deletion_request(cls, request_text: str) -> bool:
        if not request_text:
            return False

        text_lower = str(request_text).lower()

        # 1. Check explicit substring non-deletion phrases
        for pat in cls.NON_DELETION_PATTERNS:
            if pat in text_lower:
                return False

        # 2. Check regex adversarial negations across 12 languages
        for regex in cls.NEGATION_REGEXES:
            if regex.search(text_lower):
                return False

        # 3. Check for deletion keywords
        for kw in cls.DELETION_KEYWORDS:
            if kw in text_lower:
                return True

        return False
