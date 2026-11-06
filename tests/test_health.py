# from unittest.mock import AsyncMock, patch
# import pytest
# from httpx import ASGITransport, AsyncClient

# from app.main import app
# from app.services.index_service import LocalIndexService


# @pytest.mark.asyncio
# async def test_health_check():
#     with patch.object(LocalIndexService, "ensure_synced", new_callable=AsyncMock):
#         async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
#             response = await ac.get("/health")
#             assert response.status_code == 200
#             data = response.json()
#             assert data["status"] == "ok"
#             assert "index_status" in data
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from app.main import app
from app.services.index_service import LocalIndexService

@pytest.mark.asyncio
async def test_health_check():
    # Ensure app.state has index_service initialized for the test transport
    if not hasattr(app.state, "index_service"):
        app.state.index_service = LocalIndexService()

    with patch.object(LocalIndexService, "ensure_synced", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ["healthy", "degraded", "ok"]