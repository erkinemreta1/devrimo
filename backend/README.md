# Devrimo Agent Broker

A FastAPI backend that gives every authenticated user a private, persistent
[Hermes](https://github.com/nousresearch/hermes-agent) agent in its own
Docker container, and proxies chat + history between the
[`frontend/`](../frontend) app and that container. See the design writeup
this implements for the full architecture rationale.

The API surface (`/api/v1/...`) is fixed by `frontend/lib/api/*.ts` and
`frontend/lib/types.ts` — this backend exists to satisfy that contract, not
the other way around.

## Layout

```
app/
  main.py              FastAPI app, CORS, lifespan (starts the reconciler)
  config.py             Settings, read from env / .env
  auth/                 Supabase JWT verification (JWKS + legacy HS256)
  db/                    SQLAlchemy models (Agent, ChatSession) + session
  agents/
    runtime.py           AgentRuntime protocol — the only seam that matters
    docker_runtime.py     The only module allowed to import the Docker SDK
    fake_runtime.py       In-memory runtime for dev/tests without a daemon
    manager.py            State machine, turn locks, provisioning
    reconciler.py         Idle reaping, crash healing, background loop
  hermes/client.py       Typed client for one user's Hermes container
  api/v1/                 Routes: agents, chat, sessions, health
  schemas.py              Response shapes, kept in lockstep with the frontend
images/hermes/           The devrimo/hermes image (SOUL.md, MCP template)
alembic/                  Schema migrations
tests/                    Full API test suite against the fake runtime
```

## Running it

### Local dev (no Docker daemon needed)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # edit SUPABASE_URL at minimum
alembic upgrade head
AGENT_RUNTIME=fake uvicorn app.main:app --reload
```

`AGENT_RUNTIME=fake` swaps in an in-memory runtime so you can exercise the
whole agent lifecycle and chat flow against the real frontend without a
Docker daemon or a real Hermes container. Point the frontend's
`NEXT_PUBLIC_API_URL` at `http://localhost:8000`.

### Full stack (real containers)

```bash
docker build -t devrimo/hermes:latest ./images/hermes
cp .env.example .env   # AGENT_RUNTIME=docker, real SUPABASE_URL, etc.
docker compose up --build
```

This starts Postgres, the broker, and creates the `devrimo-agents` network
that per-user Hermes containers join. The broker needs the host's Docker
socket to create/manage those containers — see the comment in
`docker-compose.yml` about scoping that down with a socket proxy before
this goes anywhere near production.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests run against `AGENT_RUNTIME=fake` and a throwaway sqlite database — no
Docker daemon or live Hermes container required. `HermesClient` is stubbed
per-test so the chat/session endpoints are exercised without real HTTP
calls.

## What's genuinely unverified

This was built against Hermes's published docs, not a running instance —
there was no way to pull `nousresearch/hermes-agent` and test against it in
this environment. Two things are worth confirming against a real container
before relying on them:

- **Session adoption.** `chat.py` sends the client's thread id straight
  through as `X-Hermes-Session-Id`, assuming Hermes adopts an id it hasn't
  seen before. If it doesn't, the first turn of a thread needs
  `POST /api/sessions` first. The `chat_sessions.hermes_session_id` column
  already exists separately from the client id specifically so this can
  change without a schema migration.
- **`/api/sessions/{id}/messages` response shape.** `hermes/client.py`
  accepts either a bare list or `{"messages": [...]}`, and reads
  `role`/`content`/`created_at` per item with a couple of fallback key
  names. Worth pinning down with a real response and a fixture.

## Campus MCP tools

`images/hermes/mcp/campus.mcp.json.example` mirrors the five tools listed in
`frontend/lib/campus.ts` (ODTÜClass, catalog, calendar, library, campus),
but none of those have a real MCP server behind them yet — that's a
separate build. Ship the image without this file until they exist; Hermes
runs fine on its built-in tools alone.

## Security notes

- Agent containers run with `cap-drop: ALL`, `no-new-privileges`, memory/CPU/PID
  limits, and no published ports — see `docker_runtime.py`.
- Per-user `API_SERVER_KEY`s are generated at provision time and stored
  encrypted (Fernet, keyed by `SECRET_ENCRYPTION_KEY`) — never returned to
  the frontend.
- The `devrimo-agents` Docker network currently allows outbound internet
  (agents need it to reach the model provider) but has no route to
  Postgres or the broker's internal endpoints. Tightening outbound to an
  allowlisted egress proxy is the next hardening step, not yet built.
