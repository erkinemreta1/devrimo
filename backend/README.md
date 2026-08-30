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
  campus/
    catalog.py           The four METU MCP servers, and what each one needs
    mcp_config.py        Renders one student's mcp_servers block (pure function)
    credentials.py       The only module that decrypts a METU password
    verify.py            One SSO sign-in, to check credentials before storing
    service.py           Profile + credential persistence
  api/v1/                 Routes: agents, campus, chat, profile, sessions, health
  schemas.py              Response shapes, kept in lockstep with the frontend
images/hermes/           The devrimo/hermes image (SOUL.md, vendored MCPs)
  bin/apply-campus-mcp.py  Merges the broker's servers into Hermes' config.yaml
  CAMPUS-MCP.md            How the four servers are wired, and how to smoke-test
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
this environment. Worth confirming against a real container before relying on:

- **A full chat turn that actually calls a campus tool.** The servers are
  confirmed to launch and advertise their tools (`hermes mcp add` probed
  `sais` and discovered all six), and the config schema is confirmed against
  the real image — but no end-to-end turn has driven a tool call through the
  model and back.
- **`images/hermes/CAMPUS-MCP.md` documents the smoke test** for re-checking a
  server after bumping its pinned ref.

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

Four real MCP servers give the agent access to METU systems:

| id | Server | What it reaches |
|---|---|---|
| `sais` | [metu-sais-mcp](https://github.com/atesahmet0/metu-sais-mcp) | Transcript, CGPA, weekly schedule, portal announcements |
| `course_info` | [metu-course-info-mcp](https://github.com/atesahmet0/metu-course-info-mcp) | Course catalog, sections, prerequisites, curriculum categories |
| `odtuclass` | [metu-odtuclass-mcp](https://github.com/erkinemreta1/metu-odtuclass-mcp) | Enrolled courses, announcements, syllabi, assignment deadlines |
| `webmail` | [metu-webmail-mcp](https://github.com/atesahmet0/metu-webmail-mcp) | Read/search/send mail on the student's `@metu.edu.tr` account |

### How they run

All four are baked into the `devrimo/hermes` image at build time, each in its
own virtualenv under `/opt/mcp` (their upstream pins don't co-resolve — one
needs `fastmcp`, the others pin `mcp` directly). They are launched **inside
each student's own container** over stdio, not as shared HTTP services.

That choice is the whole security design. Three of the four upstream servers
are single-tenant and read credentials from process environment, and the
per-user container is already this system's isolation boundary — so one
student's METU password is only ever in one student's container. A shared
multi-tenant deployment would put every student's credentials in one process.

Hermes reads MCP servers from `$HERMES_HOME/config.yaml` under `mcp_servers`
(`/opt/data/config.yaml` in this image) — confirmed by running `hermes mcp add`
against the real image and reading back what it wrote.
`app/campus/mcp_config.py` renders that mapping, `docker_runtime.py` uploads it
as a tar stream (not an `exec` command line, which is visible to anything that
can inspect the daemon) at mode 0600, and `images/hermes/bin/apply-campus-mcp.py`
merges it in with `ruamel.yaml` — preserving Hermes' comments, unrelated keys,
and any server the student added with `hermes mcp add` — then deletes the
staged file. See `images/hermes/CAMPUS-MCP.md`.

### Credentials

There is no delegated-token flow at `student.metu.edu.tr`, so these servers
authenticate as the student with their real METU password. Consequently:

- The password is collected once, through frontend onboarding, over TLS.
- It is verified against METU SSO before being stored (`app/campus/verify.py`),
  so a typo fails on the form rather than silently breaking four tools.
- It is stored Fernet-encrypted under `SECRET_ENCRYPTION_KEY`, decrypted only
  in `app/campus/credentials.py`, and is in **no** response schema — the API
  reports `has_password: true`, never the value.
- Disconnecting from Settings deletes it and rebuilds the container without it.

`webmail` is the only server that can act rather than read, so it is opt-in
(`default_enabled=False`) and flagged as such in the onboarding UI.

### Changing a connection

Credentials live in the config file's per-server `env`, not in container
environment, so applying a change rewrites that file and restarts the gateway
(`AgentRuntime.reconfigure`) — the container and its volume survive.

`PUT /campus/connection` does this eagerly when the agent is running. When it
isn't — or when the eager push fails — `campus_credentials.config_dirty` stays
set, and the config is pushed on the next `manager.start`, or on demand via
`POST /campus/apply`. Without that, an agent stopped by the idle reaper would
come back running the toolset it was originally created with.

## Security notes

- Agent containers run with `cap-drop: ALL`, `no-new-privileges`, memory/CPU/PID
  limits, and no published ports — see `docker_runtime.py`.
- Per-user `API_SERVER_KEY`s are generated at provision time and stored
  encrypted (Fernet, keyed by `SECRET_ENCRYPTION_KEY`) — never returned to
  the frontend. Students' METU passwords use the same key and the same rule.
- `SECRET_ENCRYPTION_KEY` now protects real user passwords, not just internal
  API keys. It should be a managed secret, and rotating it needs a
  re-encryption pass — otherwise every campus connection breaks at once.
- The broker holds plaintext METU passwords in memory only while rendering a
  container's MCP config. They are not logged (see `verify.py`, which never
  logs its request payload) and `CampusSecrets.__repr__` is overridden so an
  accidental interpolation can't print one.
- The `devrimo-agents` Docker network currently allows outbound internet
  (agents need it to reach the model provider) but has no route to
  Postgres or the broker's internal endpoints. Tightening outbound to an
  allowlisted egress proxy is the next hardening step, not yet built.
