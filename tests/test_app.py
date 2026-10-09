import io
import pytest
from app import create_app
from app.utils import sanitize_chat_text, process_chat_log


@pytest.fixture
def app():
    """Create test application instance with CSRF disabled for API testing."""
    test_app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-secret-key-12345",
    })
    yield test_app


@pytest.fixture
def client(app):
    """Test client fixture."""
    return app.test_client()


def test_index_page(client):
    """Test that the index route renders with semantic HTML and appropriate headers."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Verify semantic HTML5 elements and title
    assert "What Did I Miss?" in html
    assert "<main" in html
    assert "<section" in html
    assert "<header" in html
    assert "<footer" in html
    assert 'name="chat_file"' in html
    assert 'aria-label=' in html

    # Verify security headers
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"


def test_api_summarize_valid_txt(client, monkeypatch):
    """Test the POST /api/summarize route with a valid .txt chat export file."""
    import json
    from unittest.mock import MagicMock, AsyncMock

    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "summary": "Team synchronized on v1 release deliverables and accessibility audit.",
        "action_items": ["Conduct frontend accessibility audit", "Deploy staging environment by 4 PM"],
        "mentions": ["@alice", "@bob", "@charlie"]
    })

    monkeypatch.setattr(
        "google.generativeai.GenerativeModel.generate_content_async",
        AsyncMock(return_value=mock_resp)
    )

    chat_content = (
        "10:00 AM @alice: Hey everyone, let's sync on the v1 release.\n"
        "10:02 AM @bob: I will do the frontend accessibility audit today.\n"
        "10:05 AM @charlie: TODO: deploy the staging environment by 4 PM.\n"
    ).encode("utf-8")

    data = {
        "chat_file": (io.BytesIO(chat_content), "slack_export.txt")
    }

    response = client.post(
        "/api/summarize",
        data=data,
        content_type="multipart/form-data"
    )

    assert response.status_code == 200
    json_data = response.get_json()

    # Verify all expected keys are present in JSON response
    assert "summary" in json_data
    assert "action_items" in json_data
    assert "mentions" in json_data

    # Verify types
    assert isinstance(json_data["summary"], str)
    assert isinstance(json_data["action_items"], list)
    assert isinstance(json_data["mentions"], list)
    assert len(json_data["action_items"]) > 0
    assert len(json_data["mentions"]) > 0


def test_api_summarize_invalid_extension(client):
    """Test rejection of non-.txt files."""
    data = {
        "chat_file": (io.BytesIO(b"%PDF-1.4..."), "chat_log.pdf")
    }
    response = client.post(
        "/api/summarize",
        data=data,
        content_type="multipart/form-data"
    )
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data


def test_api_summarize_empty_file(client):
    """Test rejection of empty 0-byte file."""
    data = {
        "chat_file": (io.BytesIO(b""), "empty.txt")
    }
    response = client.post(
        "/api/summarize",
        data=data,
        content_type="multipart/form-data"
    )
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data


def test_api_summarize_missing_file(client):
    """Test rejection when no file is supplied in the request."""
    response = client.post(
        "/api/summarize",
        data={},
        content_type="multipart/form-data"
    )
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data


def test_sanitize_chat_text_strips_xss():
    """Verify that sanitize_chat_text completely strips malicious XSS tags and control characters."""
    dangerous_input = "<script>alert('XSS')</script>Hello <b>World</b><img src=x onerror=alert(1)>"
    sanitized = sanitize_chat_text(dangerous_input)

    assert "<script>" not in sanitized
    assert "alert('XSS')" not in sanitized
    assert "<b>" not in sanitized
    assert "<img" not in sanitized
    assert "Hello World" in sanitized


@pytest.mark.asyncio
async def test_async_process_chat_log_logic(monkeypatch):
    """Verify asynchronous Gemini processing returns required keys and non-empty insights."""
    import json
    from unittest.mock import MagicMock, AsyncMock

    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "summary": "Team checked security report and scheduled auth vulnerability patch.",
        "action_items": ["Patch vulnerability in auth module"],
        "mentions": ["@lead", "@developer"]
    })

    monkeypatch.setattr(
        "google.generativeai.GenerativeModel.generate_content_async",
        AsyncMock(return_value=mock_resp)
    )

    sample_text = (
        "@lead: Team, please check the security report.\n"
        "@developer: TODO: patch the vulnerability in auth module.\n"
    )

    result = await process_chat_log(sample_text)

    assert "summary" in result
    assert "action_items" in result
    assert "mentions" in result
    assert isinstance(result["summary"], str) and len(result["summary"]) > 0
    assert isinstance(result["action_items"], list) and len(result["action_items"]) > 0
    assert isinstance(result["mentions"], list) and len(result["mentions"]) > 0


def test_api_summarize_gemini_failure_returns_500(client, monkeypatch):
    """Verify that if Gemini API fails, the route returns HTTP 500 with error details and NO fake fallback."""
    async def mock_failing_process(text):
        raise RuntimeError("Simulated Gemini API quota or connection failure")

    monkeypatch.setattr("app.routes.process_chat_log", mock_failing_process)

    data = {
        "chat_file": (io.BytesIO(b"Hello world chat"), "chat.txt")
    }

    response = client.post(
        "/api/summarize",
        data=data,
        content_type="multipart/form-data"
    )

    assert response.status_code == 500
    json_data = response.get_json()
    assert json_data["error"] == "Gemini API processing failed"
    assert "Simulated Gemini API quota or connection failure" in json_data["message"]


@pytest.mark.asyncio
async def test_process_chat_log_missing_key_raises_error(monkeypatch):
    """Verify that process_chat_log raises ValueError when GEMINI_API_KEY is missing or empty."""
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable is missing"):
        await process_chat_log("Sample chat")


def test_csrf_protection_blocks_unauthenticated_post():
    """Verify that when CSRF protection is active, requests without a valid token are rejected."""
    csrf_app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": True,
        "SECRET_KEY": "csrf-protected-key"
    })
    csrf_client = csrf_app.test_client()

    data = {
        "chat_file": (io.BytesIO(b"Hello from chat"), "test.txt")
    }

    response = csrf_client.post(
        "/api/summarize",
        data=data,
        content_type="multipart/form-data"
    )

    # CSRF failure yields 400 bad request
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data

