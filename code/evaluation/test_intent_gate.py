import unittest

import sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
_code = Path(__file__).resolve().parent.parent
if str(_code) not in sys.path:
    sys.path.insert(0, str(_code))
try:
    from code.engine.intent_gate import IntentGate
except (ModuleNotFoundError, ImportError):
    from engine.intent_gate import IntentGate


class IntentGateCustomCases(unittest.TestCase):
    def setUp(self):
        self.gate = IntentGate()

    def test_explicit_english_deletion(self):
        self.assertEqual(
            self.gate.classify("Please delete my account and all personal data."),
            "DELETION",
        )

    def test_access_request_with_explicit_non_deletion(self):
        self.assertEqual(
            self.gate.classify(
                "Under GDPR Article 15, send me a copy of my data; "
                "do not close my account."
            ),
            "NOT_APPLICABLE",
        )

    def test_french_deletion(self):
        self.assertEqual(
            self.gate.classify("Je souhaite supprimer définitivement mon compte."),
            "DELETION",
        )

    def test_negated_english_deletion(self):
        self.assertEqual(
            self.gate.classify(
                "I do not want my account deleted; I only want to export my records."
            ),
            "NOT_APPLICABLE",
        )

    def test_account_maintenance_request(self):
        self.assertEqual(
            self.gate.classify(
                "Please update my phone number and keep my profile active."
            ),
            "NOT_APPLICABLE",
        )

    def test_negated_spanish_deletion(self):
        self.assertEqual(
            self.gate.classify(
                "No quiero eliminar mi cuenta; solo quiero exportar mis datos."
            ),
            "NOT_APPLICABLE",
        )


if __name__ == "__main__":
    unittest.main()
