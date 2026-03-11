import unittest

from cyberdeck.launcher import i18n


class LauncherI18nBehaviorTests(unittest.TestCase):
    def test_repair_text_recovers_common_cp1251_mojibake(self):
        """Validate scenario: mojibake text should be repaired into readable Cyrillic."""
        broken = "РџСЂРёРІРµС‚"
        self.assertEqual(i18n._repair_text(broken), "Привет")

    def test_repair_text_keeps_clean_text_unchanged(self):
        """Validate scenario: already clean text should remain unchanged."""
        clean = "CyberDeck Launcher"
        self.assertEqual(i18n._repair_text(clean), clean)

    def test_language_label_uses_readable_russian_name(self):
        """Validate scenario: language label should be a readable Russian word."""
        self.assertEqual(i18n.language_label("ru"), "Русский")


if __name__ == "__main__":
    unittest.main()
