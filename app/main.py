from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from typing import Annotated

from app.config import Settings, get_settings
from app.providers import PROVIDERS, CursorBridge, ProviderError, complete, statuses


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout_seconds))
    app.state.cursor = CursorBridge()
    try:
        yield
    finally:
        await app.state.http.aclose()
        await app.state.cursor.aclose()


app = FastAPI(
    title="A Thing for FastAPI",
    version="0.2.0",
    description="Chat API with a switch for the built-in bot, Ollama, Claude, IBM Bob, or Cursor.",
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    provider: str | None = None

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message is empty")
        return value

    @field_validator("provider")
    @classmethod
    def known_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if value not in PROVIDERS:
            raise ValueError(f"provider must be one of: {', '.join(PROVIDERS)}")
        return value


class ChatResponse(BaseModel):
    reply: str
    provider: str
    model: str | None = None


class ProviderResponse(BaseModel):
    name: str
    configured: bool
    model: str | None = None
    detail: str


def _authorize(settings: Settings, authorization: str | None) -> None:
    expected = settings.app_api_key.strip()
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")


def _choose(requested: str | None, settings: Settings) -> str:
    provider = (requested or settings.chat_provider).strip().lower()
    if provider not in PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{provider}'. Choose from: {', '.join(PROVIDERS)}.",
        )
    return provider


async def _answer(request: Request, provider: str, message: str, settings: Settings) -> ChatResponse:
    try:
        reply = await complete(
            provider,
            message,
            settings=settings,
            http=request.app.state.http,
            cursor=request.app.state.cursor,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return ChatResponse(reply=reply.text, provider=provider, model=reply.model)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[ProviderResponse]:
    return [ProviderResponse.model_validate(item, from_attributes=True) for item in statuses(settings)]


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> ChatResponse:
    _authorize(settings, authorization)
    provider = _choose(body.provider, settings)
    return await _answer(request, provider, body.message, settings)


@app.get("/bot/{query}", response_model=ChatResponse)
async def bot(
    query: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> ChatResponse:
    _authorize(settings, authorization)
    chosen = _choose(provider, settings)
    message = query.strip()
    if not message:
        raise HTTPException(status_code=400, detail="query is empty")
    return await _answer(request, chosen, message, settings)
