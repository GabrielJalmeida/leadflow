from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .http import HTTPError
from .runtime import BudgetExceeded, CircuitOpenError, RunCancelled
from .security import UnsafeInput, redact_text


class ErrorCode(str, Enum):
    INVALID_INPUT = "invalid_input"
    AUTH = "provider_auth"
    RATE_LIMIT = "provider_rate_limit"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    NETWORK = "network"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"
    CIRCUIT_OPEN = "circuit_open"
    INTERNAL = "internal"


@dataclass(slots=True, frozen=True)
class PublicError:
    code: ErrorCode
    message: str
    retryable: bool = False


def classify_error(exc: Exception, *, secrets: tuple[str, ...] | list[str] = ()) -> PublicError:
    message = redact_text(exc, secrets=secrets)
    if isinstance(exc, UnsafeInput):
        return PublicError(ErrorCode.INVALID_INPUT, message)
    if isinstance(exc, BudgetExceeded):
        return PublicError(ErrorCode.BUDGET_EXHAUSTED, message)
    if isinstance(exc, RunCancelled):
        return PublicError(ErrorCode.CANCELLED, message)
    if isinstance(exc, CircuitOpenError):
        return PublicError(ErrorCode.CIRCUIT_OPEN, message, retryable=True)
    if isinstance(exc, HTTPError):
        if exc.status_code in {401, 403}:
            return PublicError(ErrorCode.AUTH, "credencial rejeitada pelo provider")
        if exc.status_code == 429:
            return PublicError(ErrorCode.RATE_LIMIT, "limite temporário do provider atingido", retryable=True)
        if exc.status_code in {408, 500, 502, 503, 504}:
            return PublicError(ErrorCode.PROVIDER_UNAVAILABLE, message, retryable=True)
        return PublicError(ErrorCode.NETWORK, message)
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return PublicError(ErrorCode.NETWORK, message, retryable=True)
    return PublicError(ErrorCode.INTERNAL, message)
