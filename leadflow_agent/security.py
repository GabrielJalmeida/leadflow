from __future__ import annotations

import re
from pathlib import Path

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BIDI_RE = re.compile(r"[\u202a-\u202e\u2066-\u2069]")
_BEARER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)([^\s,;]+)")
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b(\s*[:=]\s*)([^\s,;]+)"
)
_QUERY_SECRET_RE = re.compile(r"(?i)([?&](?:api[_-]?key|key|token|secret)=)([^&#\s]+)")


class UnsafeInput(ValueError):
    pass


def normalize_user_text(
    value: str,
    *,
    field: str,
    max_length: int,
    allow_empty: bool = False,
) -> str:
    """Normalize CLI/UI text without trying to interpret it as code.

    Control and bidi-override characters are rejected because they are rarely
    legitimate in search inputs and can make logs/UI misleading. Ordinary
    Unicode letters/accents remain valid.
    """

    text = " ".join(str(value or "").strip().split())
    if _CONTROL_RE.search(text) or _BIDI_RE.search(text):
        raise UnsafeInput(f"{field} contém caracteres de controle não permitidos")
    if not text and not allow_empty:
        raise UnsafeInput(f"{field} não pode ficar vazio")
    if len(text) > max_length:
        raise UnsafeInput(f"{field} excede {max_length} caracteres")
    return text


def redact_text(value: object, *, secrets: tuple[str, ...] | list[str] = ()) -> str:
    """Return a user/log-safe string with common credential forms redacted."""

    text = str(value)
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = _BEARER_RE.sub(r"\1[REDACTED]", text)
    text = _SECRET_ASSIGN_RE.sub(r"\1\2[REDACTED]", text)
    text = _QUERY_SECRET_RE.sub(r"\1[REDACTED]", text)
    return text


def safe_slug(value: str, *, fallback: str = "artifact", max_length: int = 64) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).casefold()).strip("-")
    return (slug[:max_length] or fallback[:max_length] or "artifact")


def safe_child_path(root: str | Path, child_name: str) -> Path:
    """Resolve a single generated child below root and reject traversal."""

    base = Path(root).resolve()
    candidate = (base / child_name).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise UnsafeInput("caminho gerado tentou sair do diretório permitido") from exc
    return candidate
