import unittest

from analytics import formatter


class FormatterTest(unittest.TestCase):
    def test_gfit_auth_warning_escapes_markdown_detail(self):
        text = formatter.gfit_auth_warning(
            "Bitte google_fit_token.json mit GOOGLE_FIT_INTERACTIVE_AUTH=1 neu autorisieren."
        )

        self.assertIn("google\\_fit\\_token.json", text)
        self.assertIn("GOOGLE\\_FIT\\_INTERACTIVE\\_AUTH=1", text)


if __name__ == "__main__":
    unittest.main()
