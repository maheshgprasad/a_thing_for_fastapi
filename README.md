# A Thing for FastAPI

A small chat API. One endpoint, and a `provider` switch for where the reply comes from.

| `provider` | What it calls | What you need |
| --- | --- | --- |
| `dictionary` | Built-in replies, including today's date and time | Nothing |
| `ollama` | A model on a local [Ollama](https://ollama.com) server | `ollama serve` and a pulled model |
| `claude` | Anthropic Messages API | `ANTHROPIC_API_KEY` |
| `bob` | [IBM Bob](https://bob.ibm.com) inference (`/inference/v1/chat/completions`) | `IBM_BOB_API_KEY` or `BOB_API_KEY` |
| `cursor` | A Cursor agent that only returns text | `CURSOR_API_KEY` and the `cursor` extra |

`dictionary` is the default, so the app still runs with no keys.

## Run

Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn main:app --port 9190 --reload
```

Interactive docs: http://127.0.0.1:9190/docs

```bash
curl -s http://127.0.0.1:9190/chat \
  -H 'content-type: application/json' \
  -d '{"message":"what is the date?"}'
```

The reply names today's date, and `provider` is `dictionary`.

## Switch provider

Set `provider` on the request. `CHAT_PROVIDER` in `.env` changes the default.

```bash
curl -s http://127.0.0.1:9190/chat \
  -H 'content-type: application/json' \
  -d '{"message":"Summarize what a health check is","provider":"ollama"}'
```

`GET /providers` shows each option, the model name, and whether a key is present. `GET /bot/{query}?provider=ollama` is the same switch on the old path.

Ollama uses `OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`) and `OLLAMA_MODEL`. Pull the model first, for example `ollama pull llama3.2`.

Claude uses `CLAUDE_MODEL`. Bob uses `IBM_BOB_MODEL` (default `premium`) and sends `Authorization: Apikey ...`. A general Bob key also needs `IBM_BOB_TEAM_ID`. An inference key does not.

Cursor is optional because it installs the Cursor SDK:

```bash
python -m pip install -e ".[cursor]"
```

That provider starts a local Cursor agent with tools turned off, so the call answers in text and does not edit the working tree. It is slower than the HTTP providers. A user or team service-account key from [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations) goes in `CURSOR_API_KEY`.

If `APP_API_KEY` is set, `/chat` and `/bot` require `Authorization: Bearer <that key>`. `/health` stays open for probes.

## Tests

```bash
python -m pytest
```

## Docker

The image includes the HTTP providers. It does not include the Cursor SDK.

```bash
docker build -t a-thing-for-fastapi .
docker run --rm -p 9190:9190 --env-file .env a-thing-for-fastapi
```

To reach Ollama on the host from the container, set `OLLAMA_BASE_URL=http://host.docker.internal:11434` and run Ollama with a host that accepts that connection.
