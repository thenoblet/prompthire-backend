import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import GenerationError
from app.schemas.response import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _ref_id() -> str:
    return uuid.uuid4().hex


def _envelope(detail: ErrorDetail, http_status: int) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content=ErrorResponse(error=detail).model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        ref = _ref_id()
        logger.info("request validation failed ref=%s", ref)
        details = [
            {
                "loc": ".".join(str(x) for x in e.get("loc", ())),
                "type": e.get("type"),
                "msg": e.get("msg"),
            }
            for e in exc.errors()
        ]
        return _envelope(
            ErrorDetail(
                message="Invalid request payload.",
                code="VALIDATION_ERROR",
                severity="warning",
                retryable=False,
                reference_id=ref,
                details=details,
            ),
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    @app.exception_handler(GenerationError)
    async def _generation(_: Request, exc: GenerationError) -> JSONResponse:
        ref = _ref_id()
        return _envelope(
            ErrorDetail(
                message=exc.user_message,
                code=exc.code,
                severity=exc.severity,
                retryable=exc.retryable,
                reference_id=ref,
            ),
            exc.http_status,
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        ref = _ref_id()
        logger.exception("unhandled exception ref=%s type=%s", ref, type(exc).__name__)
        return _envelope(
            ErrorDetail(
                message="Internal server error.",
                code="INTERNAL_ERROR",
                severity="error",
                retryable=False,
                reference_id=ref,
            ),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
