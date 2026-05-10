"""Wire DTO for the /healthz endpoint."""

from pydantic import BaseModel


class HealthInfo(BaseModel):
    """Wire payload returned by ``GET /healthz``.

    Both fields are string sentinels rather than booleans so the response can
    carry additional detail (e.g. a specific error message) without a schema
    change.

    Attributes:
        status: Overall service health; ``"ok"`` when the application is
            running normally.
        db: Database connectivity status; ``"ok"`` when a test query succeeds,
            or a short error description otherwise.
    """

    status: str
    db: str
