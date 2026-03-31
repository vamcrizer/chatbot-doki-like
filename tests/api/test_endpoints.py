"""
Tầng 2 — API Tests: HTTP contract, SSE streaming, middleware.
Sử dụng FastAPI TestClient. Mock Redis, DB, LLM.
Focus: status codes, header format, SSE format, error consistency.
"""
import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Create TestClient with mocked dependencies.

    Mocks: Redis, DB engine, LLM health check.
    Runs once per module to avoid repeated imports.
    """
    with patch("core.redis_client.get_redis") as mock_redis, \
         patch("core.llm_client.chat_complete") as mock_llm, \
         patch("db.database.get_engine") as mock_engine, \
         patch("db.database.get_session_factory") as mock_session, \
         patch("core.db_buffer.flush") as mock_flush, \
         patch("core.db_buffer.get_pending_count") as mock_pending, \
         patch("core.db_buffer.should_flush_early") as mock_early:
        mock_redis.return_value = MagicMock()
        mock_llm.return_value = "pong"
        mock_engine.return_value = None
        mock_session.return_value = None
        mock_flush.return_value = 0
        mock_pending.return_value = 0
        mock_early.return_value = False

        from fastapi.testclient import TestClient
        from api.main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ═══════════════════════════════════════════════════════════════
# 2.1 — Health & Root
# ═══════════════════════════════════════════════════════════════

class TestHealthEndpoint:
    """GET /health — always accessible, no auth."""

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_json_has_required_fields(self, client):
        data = client.get("/health").json()
        for field in ["status", "llm", "version"]:
            assert field in data, f"Missing field: {field}"

    def test_health_version_format(self, client):
        data = client.get("/health").json()
        parts = data["version"].split(".")
        assert len(parts) == 3  # semver


class TestRootEndpoint:
    """GET / — basic info."""

    def test_root_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_root_has_docs_url(self, client):
        data = client.get("/").json()
        assert "docs" in data


# ═══════════════════════════════════════════════════════════════
# 2.2 — Chat Validation (Pydantic at HTTP layer)
# ═══════════════════════════════════════════════════════════════

class TestChatStreamValidation:
    """POST /api/chat/stream — request validation."""

    def test_missing_body_returns_422(self, client):
        resp = client.post("/api/chat/stream")
        assert resp.status_code == 422

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

    def test_missing_character_id_returns_422(self, client):
        resp = client.post("/api/chat/stream", json={"message": "Hello"})
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 2.3 — Character Validation
# ═══════════════════════════════════════════════════════════════

class TestCharacterEndpoints:
    """Character CRUD validation."""

    def test_character_list_endpoint_exists(self, client):
        resp = client.get("/api/character/list")
        assert resp.status_code in [200, 404]

    def test_character_create_missing_name_422(self, client):
        resp = client.post(
            "/api/character/create",
            json={"system_prompt": "test prompt"},
        )
        assert resp.status_code == 422

    def test_character_create_missing_prompt_422(self, client):
        resp = client.post(
            "/api/character/create",
            json={"name": "Test"},
        )
        assert resp.status_code == 422

    def test_character_create_invalid_gender_422(self, client):
        resp = client.post(
            "/api/character/create",
            json={"name": "Test", "system_prompt": "x", "gender": "alien"},
        )
        assert resp.status_code == 422

    def test_character_create_name_too_long_422(self, client):
        resp = client.post(
            "/api/character/create",
            json={"name": "x" * 101, "system_prompt": "x"},
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 2.4 — Auth Validation
# ═══════════════════════════════════════════════════════════════

class TestAuthValidation:
    """POST /api/auth/* — input validation."""

    def test_register_invalid_email_422(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"email": "not-email", "password": "12345678"},
        )
        assert resp.status_code == 422

    def test_register_short_password_422(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"email": "test@test.com", "password": "short"},
        )
        assert resp.status_code == 422

    def test_register_missing_fields_422(self, client):
        resp = client.post("/api/auth/register", json={})
        assert resp.status_code == 422

    def test_login_missing_fields_422(self, client):
        resp = client.post("/api/auth/login", json={})
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 2.5 — CORS Headers
# ═══════════════════════════════════════════════════════════════

class TestCORSHeaders:
    """CORS preflight and response headers."""

    def test_cors_allows_configured_origin(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code < 500

    def test_cors_header_present_on_get(self, client):
        resp = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
        # CORS should add access-control-allow-origin
        allow_origin = resp.headers.get("access-control-allow-origin", "")
        assert "localhost" in allow_origin or allow_origin == "*"


# ═══════════════════════════════════════════════════════════════
# 2.6 — Error Format Consistency
# ═══════════════════════════════════════════════════════════════

class TestErrorFormat:
    """All API errors must return JSON, no stack traces."""

    def test_422_returns_json(self, client):
        resp = client.post("/api/chat/stream", json={})
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_422_has_detail_field(self, client):
        resp = client.post("/api/chat/stream", json={})
        data = resp.json()
        assert "detail" in data

    def test_404_for_unknown_route(self, client):
        resp = client.get("/api/nonexistent-endpoint")
        assert resp.status_code == 404

    def test_no_stack_trace_in_error(self, client):
        resp = client.post("/api/chat/stream", json={})
        text = resp.text
        assert "Traceback" not in text
        assert "File \"" not in text

    def test_no_internal_paths_leaked(self, client):
        resp = client.post("/api/chat/stream", json={})
        text = resp.text
        assert "/Users/" not in text
        assert "/home/" not in text
