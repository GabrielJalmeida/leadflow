from __future__ import annotations

import unittest

from leadflow_agent.validation import is_plausible_phone


class PhoneValidationTests(unittest.TestCase):
    def test_valid_brazil_mobile(self):
        self.assertTrue(is_plausible_phone("(13) 97426-5722"))

    def test_valid_brazil_fixed_line(self):
        self.assertTrue(is_plausible_phone("(13) 3491-6447"))

    def test_truncated_mobile_like_number_is_rejected(self):
        self.assertFalse(is_plausible_phone("(13) 99666-309"))

    def test_country_code_is_supported(self):
        self.assertTrue(is_plausible_phone("+55 13 99125-6276"))


if __name__ == "__main__":
    unittest.main()
