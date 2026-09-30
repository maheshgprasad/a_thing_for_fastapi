import asyncio
import json
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.chatbot import get_response
from app.config import Settings, get_settings
from app.main import app
from app.providers import CursorBridge, ProviderError, complete


def _settings(**overrides) -> Settings:
    base = dict(
        chat_provider="dictionary",
        app_api_key="",
        anthropic_api_key="",
        ibm_bob_api_key="",
        bob_api_key="",
        cursor_api_key="",
        ollama_base_url="http://ollama.local",
        ollama_model="llama3.2",
        claude_model="claude-sonnet-4-5",
        ibm_bob_model="premium",
        ibm_bob_base_url="https://bob.example/inference/v1",
        ibm_bob_auth_scheme="Apikey",
        ibm_bob_instance_id="",
        ibm_bob_team_id="",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CHAT_PROVIDER", "dictionary")
    monkeypatch.setenv("APP_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("IBM_BOB_API_KEY", "")
    monkeypatch.setenv("BOB_API_KEY", "")
    monkeypatch.setenv("CURSOR_API_KEY", "")
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_dictionary_greeting_and_date():
    assert get_response("hello") == "Hello!"
    today = datetime.now().astimezone()
    reply = get_response("what is the date")
    assert f"{today:%B} {today.day}, {today.year}" in reply
    assert get_response("what day is it") == reply


def test_chat_uses_dictionary_by_default(client):
    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "dictionary"
    assert body["reply"] == "Hello!"
    assert body["model"] is None


def test_provider_switch_is_rejected_when_unknown(client):
    response = client.post("/chat", json={"message": "hello", "provider": "gpt"})
    assert response.status_code == 422


def test_providers_lists_the_switch(client):
    response = client.get("/providers")
    assert response.status_code == 200
    names = [item["name"] for item in response.json()]
    assert names == ["dictionary", "ollama", "claude", "bob", "cursor"]
    by_name = {item["name"]: item for item in response.json()}
    assert by_name["dictionary"]["configured"] is True
    assert by_name["claude"]["configured"] is False
    assert by_name["ollama"]["configured"] is True


def test_claude_without_a_key_is_unavailable(client):
    response = client.post("/chat", json={"message": "hello", "provider": "claude"})
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_legacy_bot_path_accepts_a_provider_query(client):
    response = client.get("/bot/hello", params={"provider": "dictionary"})
    assert response.status_code == 200
    assert response.json()["reply"] == "Hello!"


def test_app_key_is_required_only_when_set(monkeypatch):
    monkeypatch.setenv("APP_API_KEY", "secret")
    monkeypatch.setenv("CHAT_PROVIDER", "dictionary")
    get_settings.cache_clear()
    with TestClient(app) as client:
        open_health = client.get("/health")
        denied = client.post("/chat", json={"message": "hello"})
        allowed = client.post(
            "/chat",
            json={"message": "hello"},
            headers={"Authorization": "Bearer secret"},
        )
    get_settings.cache_clear()
    assert open_health.status_code == 200
    assert denied.status_code == 401
    assert allowed.status_code == 200


def test_ollama_claude_and_bob_request_shapes():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "ollama.local":
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "from ollama"}})
        if request.url.host == "api.anthropic.com":
            return httpx.Response(
                200,
                json={"model": "claude-sonnet-4-5", "content": [{"type": "text", "text": "from claude"}]},
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "from bob"}}]},
        )

    async def run():
        settings = _settings(
            anthropic_api_key="sk-test",
            ibm_bob_api_key="bob-test",
            ibm_bob_team_id="team-1",
        )
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            ollama = await complete("ollama", "hi", settings=settings, http=http, cursor=CursorBridge())
            claude = await complete("claude", "hi", settings=settings, http=http, cursor=CursorBridge())
            bob = await complete("bob", "hi", settings=settings, http=http, cursor=CursorBridge())
        return ollama, claude, bob

    ollama, claude, bob = asyncio.run(run())
    assert (ollama.text, claude.text, bob.text) == ("from ollama", "from claude", "from bob")
    assert claude.model == "claude-sonnet-4-5"

    ollama_body = json.loads(seen[0].content)
    assert seen[0].url.path == "/api/chat"
    assert ollama_body["model"] == "llama3.2"
    assert ollama_body["stream"] is False

    assert seen[1].headers["x-api-key"] == "sk-test"
    assert seen[1].headers["anthropic-version"] == "2023-06-01"
    claude_body = json.loads(seen[1].content)
    assert claude_body["messages"] == [{"role": "user", "content": "hi"}]

    assert seen[2].headers["authorization"] == "Apikey bob-test"
    assert seen[2].headers["x-team-id"] == "team-1"
    assert seen[2].url.path == "/inference/v1/chat/completions"


def test_cursor_reports_a_missing_sdk():
    try:
        import cursor_sdk  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("cursor-sdk is installed")

    async def run():
        settings = _settings(cursor_api_key="cursor_test")
        async with httpx.AsyncClient() as http:
            with pytest.raises(ProviderError) as caught:
                await complete("cursor", "hi", settings=settings, http=http, cursor=CursorBridge())
        return caught.value

    error = asyncio.run(run())
    assert error.status_code == 503
    assert "cursor-sdk" in error.message
