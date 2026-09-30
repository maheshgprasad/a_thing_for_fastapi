import asyncio
from dataclasses import dataclass

import httpx

from app.chatbot import get_response
from app.config import Settings

SYSTEM_PROMPT = (
    "You are Mi-Joo, a concise personal assistant. "
    "Answer the user directly in plain text."
)

PROVIDERS = ("dictionary", "ollama", "claude", "bob", "cursor")


class ProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class ChatReply:
    text: str
    model: str | None


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    configured: bool
    model: str | None
    detail: str


class CursorBridge:
    """Holds one Cursor SDK bridge for the life of the process."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._context = None
        self._client = None

    async def client(self, cwd: str):
        async with self._lock:
            if self._client is None:
                from cursor_sdk import AsyncClient

                self._context = await AsyncClient.launch_bridge(workspace=cwd or None)
                self._client = await self._context.__aenter__()
            return self._client

    async def aclose(self) -> None:
        async with self._lock:
            if self._context is not None:
                await self._context.__aexit__(None, None, None)
            self._context = None
            self._client = None


def statuses(settings: Settings) -> list[ProviderStatus]:
    bob_ready = bool(settings.resolved_bob_api_key)
    return [
        ProviderStatus(
            "dictionary",
            True,
            None,
            "Built-in replies. Works with no keys and no network.",
        ),
        ProviderStatus(
            "ollama",
            True,
            settings.ollama_model,
            f"Local Ollama at {settings.ollama_base_url.rstrip('/')}/api/chat",
        ),
        ProviderStatus(
            "claude",
            bool(settings.anthropic_api_key.strip()),
            settings.claude_model,
            "Anthropic Messages API. Set ANTHROPIC_API_KEY.",
        ),
        ProviderStatus(
            "bob",
            bob_ready,
            settings.ibm_bob_model,
            "IBM Bob inference. Set IBM_BOB_API_KEY or BOB_API_KEY. "
            "General keys also need IBM_BOB_TEAM_ID.",
        ),
        ProviderStatus(
            "cursor",
            bool(settings.cursor_api_key.strip()),
            settings.cursor_model,
            "Cursor SDK local agent with tools disabled. "
            "Set CURSOR_API_KEY and install the cursor extra.",
        ),
    ]


async def complete(
    provider: str,
    message: str,
    *,
    settings: Settings,
    http: httpx.AsyncClient,
    cursor: CursorBridge,
) -> ChatReply:
    if provider == "dictionary":
        return ChatReply(get_response(message), None)
    if provider == "ollama":
        return await _ollama(message, settings, http)
    if provider == "claude":
        return await _claude(message, settings, http)
    if provider == "bob":
        return await _bob(message, settings, http)
    if provider == "cursor":
        return await _cursor(message, settings, cursor)
    raise ProviderError(
        f"Unknown provider '{provider}'. Choose from: {', '.join(PROVIDERS)}.",
        400,
    )


async def _post_json(
    http: httpx.AsyncClient,
    url: str,
    *,
    provider: str,
    headers: dict[str, str],
    payload: dict,
) -> dict:
    try:
        response = await http.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except httpx.ConnectError as exc:
        raise ProviderError(f"Could not reach {provider} at {url}", 503) from exc
    except httpx.TimeoutException as exc:
        raise ProviderError(f"{provider} timed out", 504) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300].strip()
        raise ProviderError(
            f"{provider} returned HTTP {exc.response.status_code}: {detail}",
            502,
        ) from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderError(f"{provider} returned a non-JSON body", 502) from exc
    if not isinstance(data, dict):
        raise ProviderError(f"{provider} returned an unexpected payload", 502)
    return data


def _openai_text(payload: dict, provider: str) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"{provider} returned no message") from exc
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    if not isinstance(content, str) or not content.strip():
        raise ProviderError(f"{provider} returned no text")
    return content.strip()


async def _ollama(message: str, settings: Settings, http: httpx.AsyncClient) -> ChatReply:
    base = settings.ollama_base_url.rstrip("/")
    payload = await _post_json(
        http,
        f"{base}/api/chat",
        provider="Ollama",
        headers={},
        payload={
            "model": settings.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
        },
    )
    content = payload.get("message", {}).get("content") if isinstance(payload.get("message"), dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ProviderError("Ollama returned no text")
    return ChatReply(content.strip(), settings.ollama_model)


async def _claude(message: str, settings: Settings, http: httpx.AsyncClient) -> ChatReply:
    key = settings.anthropic_api_key.strip()
    if not key:
        raise ProviderError("Claude is not configured. Set ANTHROPIC_API_KEY.", 503)
    payload = await _post_json(
        http,
        "https://api.anthropic.com/v1/messages",
        provider="Claude",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        payload={
            "model": settings.claude_model,
            "max_tokens": settings.claude_max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": message}],
        },
    )
    parts: list[str] = []
    for block in payload.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    text = "".join(parts).strip()
    if not text:
        raise ProviderError("Claude returned no text")
    model = payload.get("model")
    return ChatReply(text, model if isinstance(model, str) else settings.claude_model)


async def _bob(message: str, settings: Settings, http: httpx.AsyncClient) -> ChatReply:
    key = settings.resolved_bob_api_key
    if not key:
        raise ProviderError(
            "IBM Bob is not configured. Set IBM_BOB_API_KEY or BOB_API_KEY.",
            503,
        )
    headers = {
        "Authorization": f"{settings.ibm_bob_auth_scheme.strip() or 'Apikey'} {key}",
        "content-type": "application/json",
    }
    if settings.ibm_bob_instance_id.strip():
        headers["x-instance-id"] = settings.ibm_bob_instance_id.strip()
    if settings.ibm_bob_team_id.strip():
        headers["x-team-id"] = settings.ibm_bob_team_id.strip()
    base = settings.ibm_bob_base_url.rstrip("/")
    payload = await _post_json(
        http,
        f"{base}/chat/completions",
        provider="IBM Bob",
        headers=headers,
        payload={
            "model": settings.ibm_bob_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
        },
    )
    return ChatReply(_openai_text(payload, "IBM Bob"), settings.ibm_bob_model)


async def _cursor(message: str, settings: Settings, cursor: CursorBridge) -> ChatReply:
    key = settings.cursor_api_key.strip()
    if not key:
        raise ProviderError("Cursor is not configured. Set CURSOR_API_KEY.", 503)
    try:
        from cursor_sdk import CursorAgentError, LocalAgentOptions
    except ImportError as exc:
        raise ProviderError(
            "cursor-sdk is not installed. Install this project with the cursor extra.",
            503,
        ) from exc

    prompt = (
        "Reply in plain text only. Do not edit files, run commands, or use tools.\n\n"
        f"{SYSTEM_PROMPT}\n\nUser: {message}"
    )
    cwd = settings.cursor_cwd.strip() or "."
    try:
        client = await cursor.client(cwd)
        async with await client.agents.create(
            model=settings.cursor_model,
            api_key=key,
            local=LocalAgentOptions(cwd=cwd),
            tools=[],
        ) as agent:
            run = await agent.send(prompt)
            result = await run.wait()
    except CursorAgentError as exc:
        detail = getattr(exc, "message", None) or str(exc)
        raise ProviderError(f"Cursor could not start the run: {detail}", 502) from exc

    if result.status == "error":
        raise ProviderError(f"Cursor run failed ({result.id})", 502)
    if result.status != "finished":
        raise ProviderError(f"Cursor run ended with status {result.status}", 502)
    text = (result.result or "").strip()
    if not text:
        raise ProviderError("Cursor finished without any text")
    model = getattr(result.model, "id", None) or settings.cursor_model
    return ChatReply(text, model)
