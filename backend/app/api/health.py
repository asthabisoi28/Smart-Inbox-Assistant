from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from app.db.session import check_db_connection
from app.core.config import settings

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    service: str


class DbHealthResponse(BaseModel):
    status: str
    service: str
    database_connected: bool


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Health check endpoint to verify backend service availability."""
    return HealthResponse(
        status="ok",
        service="smart-inbox-assistant"
    )


@router.get("/health/db", response_model=DbHealthResponse)
def database_health_check() -> DbHealthResponse:
    """Verifies active connectivity to the configured database.
    In mock mode, always returns connected=True.
    """
    if settings.USE_MOCK_DATA:
        return DbHealthResponse(status="connected", service="smart-inbox-assistant", database_connected=True)
    is_connected = check_db_connection()
    return DbHealthResponse(
        status="connected" if is_connected else "disconnected",
        service="smart-inbox-assistant",
        database_connected=is_connected,
    )
    """Verifies active connectivity to the configured database."""
    is_connected = check_db_connection()
    return DbHealthResponse(
        status="connected" if is_connected else "disconnected",
        service="smart-inbox-assistant",
        database_connected=is_connected,
    )
