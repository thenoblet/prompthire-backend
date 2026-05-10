from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Machine-readable error payload embedded in every error response.

    Populated by ``core/error_handlers.py`` from the attributes of a
    ``GenerationError`` subclass or from FastAPI's ``RequestValidationError``.

    Attributes:
        message: Human-readable description of the error.
        code: Stable string identifier for the error type
            (e.g. ``"RATE_LIMITED"``, ``"VALIDATION_ERROR"``). Intended for
            programmatic handling by the frontend.
        error_code: Optional secondary code for additional classification;
            currently unused.
        severity: Log-level hint for the frontend (``"error"`` or
            ``"warning"``).
        retryable: Whether the client should offer a retry action.
        reference_id: Optional correlation ID for tracing; not yet populated.
        details: Optional list of field-level validation errors, present on
            ``422`` responses.
    """

    message: str
    code: str
    error_code: str | None = None
    severity: str | None = None
    retryable: bool | None = None
    reference_id: str | None = None
    details: list[dict] | None = None


class ErrorResponse(BaseModel):
    """Top-level envelope for all error responses.

    Attributes:
        error: The structured error detail payload.
    """

    error: ErrorDetail


class ApiResponse(BaseModel, Generic[T]):
    """Top-level envelope for all successful responses.

    Attributes:
        data: The typed response payload. Parameterised via ``Generic[T]``
            so callers can declare ``ApiResponse[GenerateResponse]`` etc.
        meta: Optional metadata dict for pagination, rate-limit headers, or
            other out-of-band information; currently always ``None``.
    """

    data: T
    meta: dict | None = None
