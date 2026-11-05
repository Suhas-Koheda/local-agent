# local-agent

A local, single-agent runtime exposed as a small FastAPI service. It talks to any
OpenAI-compatible chat-completions endpoint, keeps conversation state in SQLite,
compacts long context, and can call built-in tools (including a headless browser).

## Layout

```
src/superagent/
├── main.py                 # FastAPI app: /health and /chat
├── agent/
│   ├── provider.py         # OpenAI-compatible model client
│   └── loop.py             # SingleAgent tool-calling loop
├── context/engine.py       # Token-budgeted context assembly + summarisation
├── runtime/task_manager.py # Task lifecycle, persistence, execution
├── tools/
│   ├── registry.py         # Tool registration and JSON-schema dispatch
│   ├── builtin.py          # Built-in tools (memory, artifacts, ...)
│   └── browser.py          # Playwright + selectolax page fetch/extract
└── storage/database.py     # SQLAlchemy models and async SQLite engine
```

## Requirements

- Python 3.10+
- An OpenAI-compatible server (llama.cpp, vLLM, Ollama, LM Studio, ...)

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn sqlalchemy aiosqlite httpx pydantic playwright selectolax
playwright install chromium

export LLM_ENDPOINT="http://localhost:8080/v1"
PYTHONPATH=src uvicorn superagent.main:app --reload
```

The database is created at `data/superagent.db` on first start, and long tool
output is spilled to `data/spills/`. Both are ignored by git.

## API

```bash
curl localhost:8000/health

curl -X POST localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id": "demo", "message": "Summarise example.com"}'
```

| Method | Path      | Description                                  |
| ------ | --------- | -------------------------------------------- |
| GET    | `/health` | Liveness probe                               |
| POST   | `/chat`   | Run one agent task and return the final text |

`conversation_id` defaults to `default_conv`, so messages with the same id share
history.
