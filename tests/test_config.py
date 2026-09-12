from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import leadflow_agent.config as config
from leadflow_agent.config import Settings, _resolve_dotenv_path


class ConfigTests(unittest.TestCase):
    def test_default_env_falls_back_to_project_root_from_frontend_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "leadflow_agent"
            frontend_dir = root / "frontend"
            package_dir.mkdir()
            frontend_dir.mkdir()
            env_path = root / ".env"
            env_path.write_text(
                "GEMINI_API_KEY=test-gemini\n"
                "TAVILY_API_KEY=test-tavily\n",
                encoding="utf-8",
            )

            fake_config_file = package_dir / "config.py"
            old_cwd = Path.cwd()
            try:
                os.chdir(frontend_dir)
                with patch.object(config, "__file__", str(fake_config_file)):
                    resolved = _resolve_dotenv_path(".env")
                    self.assertEqual(resolved, env_path)

                    with patch.dict(
                        os.environ,
                        {
                            "GEMINI_API_KEY": "",
                            "TAVILY_API_KEY": "",
                        },
                        clear=False,
                    ):
                        os.environ.pop("GEMINI_API_KEY", None)
                        os.environ.pop("TAVILY_API_KEY", None)
                        settings = Settings.load()
                        self.assertEqual(settings.gemini_api_key, "test-gemini")
                        self.assertEqual(settings.tavily_api_key, "test-tavily")
            finally:
                os.chdir(old_cwd)

    def test_explicit_env_path_is_respected(self) -> None:
        custom = Path("custom.env")
        self.assertEqual(_resolve_dotenv_path(custom), custom)


if __name__ == "__main__":
    unittest.main()
