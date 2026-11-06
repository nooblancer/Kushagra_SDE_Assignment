from fastapi import APIRouter
from app.models.domain import HealthResponse

router = APIRouter(prefix="", tags=["System"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health_check() -> HealthResponse:
    """Returns the operational status of the service."""
    return HealthResponse(status="ok", upstream_status="connected")

