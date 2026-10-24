class RequestClassifier:
    """
    Classifies customer request_text to determine whether account deletion
    was genuinely requested or if the request is NOT_APPLICABLE.
    """

    NON_DELETION_PATTERNS = [
        "leave the account active",
        "keep the account as it is",
        "leave my profile and purchase history in place",
        "continue using the service",
        "don't delete or change anything",
        "do not delete or change anything",
        "without removing any of my records",
    ]

    DELETION_KEYWORDS = [
        "delet", "erase", "erasure", "close", "remove", "purge",
        "destroy", "right to be forgotten", "shut down", "cancel my account",
        "profile is gone", "confirm that the profile is gone",
        # Portuguese
        "exclusão", "exclusao",
        # French
        "suppression", "supprimer",
        # Spanish
        "eliminación", "eliminacion", "eliminar",
        # German
        "löschen", "loeschen",
        # Japanese
        "削除", "消去",
        # Korean
        "삭제", "해지", "탈퇴",
        # Arabic
        "حذف"
    ]

    @classmethod
    def is_deletion_request(cls, request_text: str) -> bool:
        if not request_text:
            return False

        text_lower = str(request_text).lower()

        # Explicit non-deletion requests
        for pat in cls.NON_DELETION_PATTERNS:
            if pat in text_lower:
                return False

        # Must contain deletion keyword
        for kw in cls.DELETION_KEYWORDS:
            if kw in text_lower:
                return True

        return False
