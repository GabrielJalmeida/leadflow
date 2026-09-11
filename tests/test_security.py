from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leadflow_agent.errors import ErrorCode, classify_error
from leadflow_agent.http import HTTPError
from leadflow_agent.security import UnsafeInput, normalize_user_text, redact_text, safe_child_path, safe_slug


class SecurityBoundaryTests(unittest.TestCase):
    def test_redacts_explicit_secret_and_common_tokens(self):
        text = "Authorization: Bearer abc123 api_key=xyz token=qwerty"
        redacted = redact_text(text, secrets=["abc123"])
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("xyz", redacted)
        self.assertNotIn("qwerty", redacted)
        self.assertGreaterEqual(redacted.count("[REDACTED]"), 3)

    def test_normalize_rejects_control_and_bidi_override(self):
        with self.assertRaises(UnsafeInput):
            normalize_user_text("marcenaria\x00teste", field="segmento", max_length=120)
        with self.assertRaises(UnsafeInput):
            normalize_user_text("marcenaria\u202etxt", field="segmento", max_length=120)

    def test_normalize_preserves_unicode_and_collapses_spaces(self):
        self.assertEqual(
            normalize_user_text("  móveis   planejados  ", field="segmento", max_length=120),
            "móveis planejados",
        )

    def test_safe_paths_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "output"
            root.mkdir()
            with self.assertRaises(UnsafeInput):
                safe_child_path(root, "../secret.txt")
            safe = safe_child_path(root, f"{safe_slug('../../Empresa')}-.json")
            self.assertEqual(safe.parent, root.resolve())

    def test_error_taxonomy_hides_provider_auth_detail(self):
        error = classify_error(HTTPError("HTTP 401: api_key=secret-value", status_code=401))
        self.assertEqual(error.code, ErrorCode.AUTH)
        self.assertNotIn("secret-value", error.message)


if __name__ == "__main__":
    unittest.main()
