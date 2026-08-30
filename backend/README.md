# Devrimo Agent Broker

A FastAPI backend that gives every authenticated user a private
[Agno](https://github.com/agno-agi/agno) agent with access to their METU
campus systems, and serves chat + history to the [`frontend/`](../frontend)
app.

The API surface (`/api/v1/...`) is fixed by `frontend/lib/api/*.ts` and
`frontend/lib/types.ts` — this backend exists to satisfy that contract, not
the other way around.

## Layout

```
app/
  main.py               FastAPI app, CORS, lifespan (reconciler + pool teardown)
  config.py              Settings, read from env / .env
  auth/                  Supabase JWT verification (JWKS + legacy HS256)
  db/                     SQLAlchemy models (Agent, ChatSession) + session
  agents/
    pool.py               Resident agents, one per user, with their MCP subprocesses
    toolset.py            The only module that spawns campus MCP servers
    store.py              The Agno database — where conversation history lives
    manager.py            State machine, turn locks, entitlement
    reconciler.py         Idle eviction, background loop
    echo_model.py         Model test double for AGENT_RUNTIME=fake
    persona.md            The agent's instructions
  campus/
    catalog.py            The four METU MCP servers, and what each one needs
    mcp_config.py         Renders one student's launch specs (pure function)
    credentials.py        The only module that decrypts a METU password
    verify.py             One SSO sign-in, to check credentials before storing
    service.py            Profile + credential persistence
  api/v1/                 Routes: agents, campus, chat, profile, sessions, health
  schemas.py              Response shapes, kept in lockstep with the frontend
alembic/                  Schema migrations
tests/                    Full API test suite against the echo model
```

## Architecture

The agent runs **in the broker process**, not in a container of its own.
`app/agents/pool.py` holds one live `agno.Agent` per active user; building one
spawns a campus MCP subprocess per connected server and costs about a second,
so agents are created on the turn that needs them and evicted once idle.

Eviction is safe because it is invisible: conversation history lives in the
database (`agno_*` tables, see `app/agents/store.py`), so reading a month-old
thread is a query and the next turn after an eviction transparently rebuilds.

`chat.py` owns the wire format rather than proxying one. It translates Agno's
run events into OpenAI `chat.completion.chunk` objects, which is what
`frontend/lib/api/chat.ts` parses. Tool activity is emitted on the same stream
as chunks carrying an empty delta plus a namespaced `devrimo` object — today's
frontend ignores them, and the assistant-ui tool components can be wired to
them without a backend change.

### Isolation

Campus MCP servers are subprocesses of the broker, spawned one set per student.
The isolation that used to come from one container per student now comes from
process environment: the MCP SDK spawns each server with only
`HOME/LOGNAME/PATH/SHELL/TERM/USER` inherited plus that server's own rendered
`env`, so a campus server sees its own student's METU password and neither
another student's nor the broker's `SECRET_ENCRYPTION_KEY`, `DATABASE_URL`, or
model-provider key.

This is a real reduction in isolation from the container design, taken
deliberately: all four upstream servers are first-party, and the broker already
decrypts every student's password. The residual risk is a bug in one of those
scrapers reading another student's environment. Two things follow from that and
should not be dropped:

- **The MCP server refs are pinned** to exact commits (Dockerfile build args),
  and the build records what each one resolved to in `/opt/mcp/MANIFEST`,
  reported by `GET /health`. Pinning buys reproducibility, not review — nobody
  has audited those commits, and pinning is what makes auditing them worth
  doing. Bumping one is `git ls-remote <repo> <branch>`, edit the arg, rebuild.
- **Webmail grants more authority than its consent copy claims.** The pinned
  commit exposes six mutating tools, including `forward_email` and a
  `delete_email` whose non-permanent mode can still destroy mail; the onboarding
  text promises only read and send. Nothing but the system prompt stands between
  a hostile course announcement and a forwarded transcript. This is the largest
  remaining exposure, and it is a tool-layer problem rather than a network one —
  see [Decision: webmail write authority](../docs/decisions/0001-webmail-write-authority.md),
  which is open and should be closed before webmail reaches students.

Restoring full per-student isolation later does not require undoing this work:
run the four servers behind Streamable HTTP in a per-student sandbox and point
`MCPTools` at the URL instead of a `StdioServerParameters`. `app/agents/toolset.py`
is the only module that would change.

### Egress

There is no egress allowlist, and the note that used to say one "moved to the
broker" was wrong. The reasoning is worth keeping, because the obvious fix does
not work here.

An allowlist expressible in `docker-compose.yml` means an HTTP proxy, and an
HTTP proxy cannot filter this traffic:

- **Webmail is not HTTP.** It is IMAP and SMTP over raw TCP (993/465), and
  `imaplib`/`smtplib` are not proxy-aware. A proxy would cover three servers and
  silently miss the only one that can act as the student.
- **Proxy environment never reaches the other three.** The MCP SDK spawns each
  server with `DEFAULT_INHERITED_ENV_VARS` only — `HOME`, `LOGNAME`, `PATH`,
  `SHELL`, `TERM`, `USER`. An `HTTPS_PROXY` set in compose is dropped before the
  subprocess starts. Making it work would mean injecting it per-spec in
  `app/campus/mcp_config.py`, i.e. a network control whose enforcement depends
  on application code opting in.

Filtering this mix means L4, and the broker cannot do it to itself: `nftables`
needs `NET_ADMIN`, which hands back the privilege that dropping the Docker
socket removed. It belongs on the host — an nftables rule on the FORWARD chain
for the `devrimo-internal` bridge, allowing METU hosts and the model endpoint.
Worth doing as defence in depth; deployment configuration, not something this
repo can ship.

Be clear about what it would buy, though. The worst exfiltration path is *inside*
any such allowlist: webmail can send mail as the student, to anywhere, and mail
to METU hosts is exactly what the allowlist permits. Network filtering does not
touch that. The control that does is at the tool layer — see the webmail
decision linked above.

### Telemetry

Agno posts run telemetry to `os-api.agno.com` by default. These runs are
students' campus conversations, so it is switched off in code (`telemetry=False`
in `pool.py`) and again via `AGNO_TELEMETRY=false` in the compose file and
`.env.example`. Both, deliberately — a deployment that forgets the env var is
still covered.

## Running it

### Local dev (no campus servers needed)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # edit SUPABASE_URL at minimum
alembic upgrade head
AGENT_RUNTIME=fake uvicorn app.main:app --reload
```

`AGENT_RUNTIME=fake` swaps in an echo model (`app/agents/echo_model.py`) so the
whole chat and session flow works against the real frontend without a model
provider or the four campus servers installed. Everything else — the Agent, its
database, session persistence, SSE serialization — is the production path.
Point the frontend's `NEXT_PUBLIC_API_URL` at `http://localhost:8000`.

### Full stack

```bash
cp .env.example .env   # AGENT_RUNTIME=agno, real SUPABASE_URL, AGENT_OPENAI_API_KEY
docker compose up --build
```

The broker image builds the four campus MCP servers into `/opt/mcp`, each in
its own virtualenv (their upstream pins don't co-resolve — one needs `fastmcp`,
the others pin `mcp` directly). There is no second image and no Docker socket
mount any more, so the broker runs as an unprivileged user.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Dependency pins worth knowing

- **`mcp<2.0` is deliberate.** 2.x renamed `McpError` to `MCPError` and agno 3.x
  still imports the old name; an unpinned install fails at import with a
  misleading "`mcp` not installed".
- **`psycopg` alongside `asyncpg`.** Agno's database layer is synchronous and
  builds its own engine, so Postgres deployments need both drivers.
- **`AGENT_MAX_TOKENS`.** Agno's `OpenRouter` class defaults `max_tokens` to
  1024, which truncates a long transcript summary mid-sentence.

## Campus MCP tools

| id | Server | What it reaches |
|---|---|---|
| `sais` | [metu-sais-mcp](https://github.com/atesahmet0/metu-sais-mcp) | Transcript, CGPA, weekly schedule, portal announcements |
| `course_info` | [metu-course-info-mcp](https://github.com/atesahmet0/metu-course-info-mcp) | Course catalog, sections, prerequisites, curriculum categories |
| `odtuclass` | [metu-odtuclass-mcp](https://github.com/erkinemreta1/metu-odtuclass-mcp) | Enrolled courses, announcements, syllabi, assignment deadlines |
| `webmail` | [metu-webmail-mcp](https://github.com/atesahmet0/metu-webmail-mcp) | Read/search/send mail on the student's `@metu.edu.tr` account |

`app/campus/mcp_config.py` renders each student's launch specs — command, argv,
environment, working directory — and `app/agents/toolset.py` turns them into
connected `MCPTools`. Each server gets `tool_name_prefix` (the four were written
independently and several use generic tool names) and a private 0700 working
directory under `CAMPUS_STATE_ROOT`, because odtuclass caches its Moodle session
token relative to its CWD.

A server that fails to connect is dropped and logged rather than failing the
whole agent; the persona tells the model to say plainly when a tool it expected
is missing. Note that `MCPTools.connect()` swallows its own exceptions, so
`toolset.py` checks whether the toolkit actually initialized.

### Credentials

There is no delegated-token flow at `student.metu.edu.tr`, so these servers
authenticate as the student with their real METU password. Consequently:

- The password is collected once, through frontend onboarding, over TLS.
- It is verified against METU SSO before being stored (`app/campus/verify.py`),
  so a typo fails on the form rather than silently breaking four tools.
- It is stored Fernet-encrypted under `SECRET_ENCRYPTION_KEY`, decrypted only
  in `app/campus/credentials.py`, and is in **no** response schema — the API
  reports `has_password: true`, never the value.
- Disconnecting from Settings deletes it and drops the resident agent.

`webmail` is the only server that can act rather than read, so it is opt-in
(`default_enabled=False`) and flagged as such in the onboarding UI. `CampusTool`
also carries an `exclude_tools` field, which would let webmail be offered
read-only rather than all-or-nothing — not currently used.

### Changing a connection

Credentials are read fresh on every turn and compared against what the resident
agent was built with, so a change takes effect on the next turn without a
restart. `PUT /campus/connection` also drops the resident agent eagerly, so a
student who revokes a tool stops having it immediately rather than at the end of
their current session.

## What's genuinely unverified

- **A full chat turn that actually calls a campus tool.** The spec renderer and
  the toolkit wiring are covered by tests, but no end-to-end turn has driven a
  real campus tool call through a real model. `AGENT_RUNTIME=fake` deliberately
  never calls a tool.
- **The four servers under agno's MCP client.** They were previously launched by
  Hermes' own client. The transport is the same stdio protocol and the specs are
  asserted in `tests/test_campus_config.py`, but the handshake has not been run
  against the real servers.
