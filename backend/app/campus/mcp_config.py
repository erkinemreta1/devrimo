"""Render one student's campus MCP servers in Hermes' own config schema.

Hermes keeps MCP servers in ``$HERMES_HOME/config.yaml`` under the
``mcp_servers`` key — verified against the real image, whose ``hermes mcp add``
produces exactly the shape emitted here:

    mcp_servers:
      sais:
        command: /opt/mcp/sais/.venv/bin/python
        args: [-m, sais_mcp.server, --transport, stdio]
        env: {SAIS_USERNAME: e123456, SAIS_PASSWORD: ..., LOCALE: tr}
        enabled: true

The broker emits that mapping as JSON and stages it in the container;
``images/hermes/bin/apply-campus-mcp.py`` merges it into config.yaml with
ruamel so Hermes' own comments and unrelated keys survive.

Nothing here touches the database or the network, which is what makes it cheap
to test: given a catalog entry and a secrets bundle, the JSON is a pure
function of the two.
"""

import json

from app.campus.catalog import CAMPUS_TOOLS, CampusTool
from app.campus.credentials import CampusSecrets

# Where the broker stages the rendered mapping inside the container. Not the
# live config — the merge script reads this, folds it into config.yaml, and
# deletes it, because it carries the student's METU password.
STAGED_CONFIG_PATH = "/opt/data/.devrimo/campus-mcp.json"
MERGE_SCRIPT_PATH = "/opt/devrimo/bin/apply-campus-mcp.py"


def _render_env(tool: CampusTool, values: dict[str, str]) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for key, template in tool.env_template.items():
        try:
            value = template.format(**values)
        except KeyError:
            # A template referencing a value the bundle doesn't carry is a
            # catalog bug, not a user error; skip the key rather than break
            # every other server in the file.
            continue
        # Empty is meaningfully different from absent here: an empty
        # ODTUCLASS_TOKEN would make the upstream client prefer a blank token
        # over falling back to username/password login.
        if value:
            rendered[key] = value
    return rendered


def enabled_tools(enabled_ids: list[str], secrets: CampusSecrets | None) -> list[CampusTool]:
    """The tools the student asked for that they've actually supplied credentials for."""
    if secrets is None:
        return []
    chosen = set(enabled_ids)
    return [
        tool for tool in CAMPUS_TOOLS if tool.id in chosen and all(secrets.has(kind) for kind in tool.requires)
    ]


def build_mcp_servers(enabled_ids: list[str], secrets: CampusSecrets | None) -> dict:
    """The ``mcp_servers`` mapping, keyed by tool id."""
    values = secrets.as_template_values() if secrets else {}
    servers: dict[str, dict] = {}
    for tool in enabled_tools(enabled_ids, secrets):
        entry: dict[str, object] = {
            "command": tool.command,
            "args": list(tool.args),
            "env": _render_env(tool, values),
            # Hermes gates each server on this; without it the entry is stored
            # but never launched.
            "enabled": True,
        }
        if tool.cwd:
            entry["cwd"] = tool.cwd
        servers[tool.id] = entry
    return servers


def render_mcp_config(enabled_ids: list[str], secrets: CampusSecrets | None) -> str:
    return json.dumps(build_mcp_servers(enabled_ids, secrets), indent=2, ensure_ascii=False)


def managed_server_names() -> tuple[str, ...]:
    """Every name the broker owns in config.yaml, enabled or not.

    The merge script needs the full set, not just what's currently on: a tool
    the student just switched off has to be removed from config.yaml, and it
    can only be removed if it's named.
    """
    return tuple(tool.id for tool in CAMPUS_TOOLS)


def working_directories(enabled_ids: list[str], secrets: CampusSecrets | None) -> list[str]:
    """CWDs that must exist on the volume before the servers are launched."""
    return [tool.cwd for tool in enabled_tools(enabled_ids, secrets) if tool.cwd]
