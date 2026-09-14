from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from leadflow_agent.api import create_app
from leadflow_agent.config import Settings


class SettingsApiTests(unittest.TestCase):
    def test_defaults_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(db_path=str(Path(tmp) / "leadflow.db"))
            with patch("leadflow_agent.api.Settings.load", return_value=settings), patch("leadflow_agent.storage.Settings", create=True):
                client = TestClient(create_app())
                first = client.get("/api/v1/settings")
                self.assertEqual(first.status_code, 200)
                data = first.json()["settings"]
                self.assertEqual(data["text_ai"], "chatgpt")
                data["text_ai"] = "claude"
                saved = client.put("/api/v1/settings", json=data)
                self.assertEqual(saved.status_code, 200)
                self.assertEqual(saved.json()["settings"]["text_ai"], "claude")


if __name__ == "__main__":
    unittest.main()
