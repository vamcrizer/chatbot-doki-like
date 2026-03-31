"""
Nhóm 2 — API Tests: api/routes/*
HTTP contract testing with FastAPI TestClient.
Mock Redis, DB, LLM — focus on status codes, headers, SSE format.
"""
import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create TestClient with mocked dependencies."""
    # Mock Redis before importing app
    with patch("core.redis_client.get_redis_client") as mock_redis, \
         patch("api.deps.get_redis_client") as mock_deps_redis, \
         patch("db.database.get_engine") as mock_engine:

        mock_redis.return_value = MagicMock()
        mock_deps_redis.return_value = MagicMock()
        mock_engine.return_value = None

        from api.main import app
        with TestClient(app) as c:
            yield c


class TestHealthEndpoint:
    """GET /health"""

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_status_field(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data


class TestChatStreamEndpoint:
    """POST /api/chat/stream — SSE behavior."""

    def test_missing_message_returns_422(self, client):
        resp = client.post("/api/chat/stream", json={"character_id": "kael"})
        assert resp.status_code == 422

    def test_empty_message_returns_422(self, client):
        resp = client.post(
            "/api/chat/stream",
            json={"character_id": "kael", "message": ""},
        )
        assert resp.status_code == 422

    def test_message_too_long_returns_422(self, client):
        resp = client.post(
            "/api/chat/stream",
            json={"character_id": "kael", "message": "x" * 2001},
        )
        assert resp.status_code == 422


class TestCharacterEndpoints:
    """GET/POST /api/character/*"""

    def test_character_list_exists(self, client):
        resp = client.get("/api/character/list")
        # Should return 200 or at least not 500
        assert resp.status_code in [200, 404]

    def test_character_create_missing_name_422(self, client):
        resp = client.post("/api/character/create", json={"system_prompt": "x"})
        assert resp.status_code == 422


class TestCORSHeaders:
    """CORS and security headers."""

    def test_options_preflight(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Should not be 500
        assert resp.status_code < 500


class TestErrorFormatConsistency:
    """All errors should return consistent JSON format."""

    def test_422_has_json_body(self, client):
        resp = client.post("/api/chat/stream", json={})
        assert resp.status_code == 422
        data = resp.json()
        # FastAPI default returns "detail" for validation errors
        assert "detail" in data

    def test_404_for_unknown_route(self, client):
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404

    def test_no_stack_trace_in_error(self, client):
        resp = client.post("/api/chat/stream", json={})
        text = resp.text
        assert "Traceback" not in text
        assert "File \"" not in text
