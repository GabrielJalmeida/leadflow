from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader so the MVP has no third-party dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(slots=True)
class Settings:
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    tavily_api_key: str = ""
    outscraper_api_key: str = ""
    brave_api_key: str = ""
    db_path: str = "leadflow.db"

    @classmethod
    def load(cls, dotenv_path: str | Path = ".env") -> "Settings":
        _load_dotenv(Path(dotenv_path))
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip() or "gemini-3.1-flash-lite",
            tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip(),
            outscraper_api_key=os.getenv("OUTSCRAPER_API_KEY", "").strip(),
            brave_api_key=os.getenv("BRAVE_SEARCH_API_KEY", "").strip(),
            db_path=os.getenv("LEADFLOW_DB", "leadflow.db").strip() or "leadflow.db",
        )
