from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Machine-readable error payload."""

    message: str
    code: str
    error_code: str | None = None
    severity: str | None = None
    retryable: bool | None = None
    reference_id: str | None = None
    details: list[dict] | None = None


class ErrorResponse(BaseModel):
    """Envelope for error responses."""

    error: ErrorDetail


class ApiResponse(BaseModel, Generic[T]):
    """Envelope for successful responses."""

    data: T
    meta: dict | None = None
