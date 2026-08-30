# Campus MCP servers in this image

Reference for how the four METU MCP servers get from this image into a
running agent. Verified against `nousresearch/hermes-agent` — the schema below
is what `hermes mcp add` itself writes.

## Where they live

`/opt/mcp/<slug>/` — one shallow clone plus one virtualenv per server, built
in a separate stage and copied in. The venvs hardcode their interpreter path,
so `/opt/mcp` must stay at that exact path.

| slug | launched as |
|---|---|
| `sais` | `/opt/mcp/sais/.venv/bin/python -m sais_mcp.server --transport stdio` |
| `course-info` | `/opt/mcp/course-info/.venv/bin/python -m metu_course_info_mcp --transport stdio` |
| `webmail` | `/opt/mcp/webmail/.venv/bin/python -m metu_webmail_mcp --transport stdio` |
| `odtuclass` | `/opt/mcp/odtuclass/.venv/bin/python /opt/mcp/odtuclass/odtuclass_mcp.py` |

## How they get configured

Hermes reads MCP servers from `$HERMES_HOME/config.yaml` (here,
`/opt/data/config.yaml`) under the `mcp_servers` key — **not** from a separate
`.mcp.json`. Entries look like this:

```yaml
mcp_servers:
  sais:
    command: /opt/mcp/sais/.venv/bin/python
    args: [-m, sais_mcp.server, --transport, stdio]
    env:
      SAIS_USERNAME: e123456
      SAIS_PASSWORD: <the student's METU password>
      LOCALE: tr
    cwd: /opt/data/mcp/sais
    enabled: true
```

The broker never writes that file directly. It renders the `mcp_servers`
mapping (`app/campus/mcp_config.py`), uploads it as JSON to
`/opt/data/.devrimo/campus-mcp.json`, and execs `bin/apply-campus-mcp.py`,
which merges it in with `ruamel.yaml` and deletes the staged file. The merge
preserves Hermes' own comments and unrelated keys, and only touches the server
names the broker declares as managed — anything added with `hermes mcp add`
survives.

## Credentials

Nothing in this image carries a credential. Every value above is injected
per-container at create time from the student's own encrypted record. See the
"Campus MCP tools" section of `backend/README.md`.

## Smoke test

`hermes mcp add` probes a server and lists its tools, which is the quickest
way to confirm one still works after bumping its pinned ref:

```bash
docker run --rm --entrypoint sh devrimo/hermes:latest -c '
  cd /opt/hermes && ./bin/hermes mcp add sais \
    --command /opt/mcp/sais/.venv/bin/python \
    --env SAIS_USERNAME=e123456 SAIS_PASSWORD=... \
    --args -m sais_mcp.server --transport stdio'
```
