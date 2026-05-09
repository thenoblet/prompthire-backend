"""Wire DTO for the /healthz endpoint."""

from pydantic import BaseModel


class HealthInfo(BaseModel):
    status: str
    db: str
