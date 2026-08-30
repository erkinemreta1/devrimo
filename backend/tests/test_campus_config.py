"""The MCP config renderer: what actually lands in a student's config.yaml.

The expected shape is Hermes' own ``mcp_servers`` schema, confirmed against a
real image by running ``hermes mcp add`` and reading back what it wrote.
"""

import json

from app.campus.catalog import CAMPUS_TOOLS, normalize_tool_ids
from app.campus.credentials import CampusSecrets
from app.campus.mcp_config import (
    build_mcp_servers,
    managed_server_names,
    render_mcp_config,
    working_directories,
)


def secrets(**overrides) -> CampusSecrets:
    base = {
        "metu_username": "e123456",
        "metu_password": "hunter2",
        "odtuclass_token": "",
        "locale": "tr",
        "odtuclass_base_url": "",
    }
    return CampusSecrets(**{**base, **overrides})


def test_only_enabled_tools_are_rendered():
    servers = build_mcp_servers(["sais"], secrets())
    assert list(servers) == ["sais"]


def test_entry_matches_the_schema_hermes_writes_itself():
    entry = build_mcp_servers(["sais"], secrets())["sais"]
    assert entry == {
        "command": "/opt/mcp/sais/.venv/bin/python",
        "args": ["-m", "sais_mcp.server", "--transport", "stdio"],
        "env": {"SAIS_USERNAME": "e123456", "SAIS_PASSWORD": "hunter2", "LOCALE": "tr"},
        "enabled": True,
        "cwd": "/opt/data/mcp/sais",
    }


def test_every_tool_is_declared_managed():
    # The merge script can only remove a server it is told the broker owns, so
    # a tool missing here would linger in config.yaml after being switched off.
    assert set(managed_server_names()) == {tool.id for tool in CAMPUS_TOOLS}


def test_tools_without_their_credentials_are_dropped():
    # No password and no ODTUClass token: nothing can authenticate, so the
    # config is empty rather than containing servers that will fail at runtime.
    servers = build_mcp_servers([tool.id for tool in CAMPUS_TOOLS], secrets(metu_password=""))
    assert servers == {}


def test_odtuclass_works_from_a_token_alone():
    servers = build_mcp_servers(["odtuclass", "sais"], secrets(metu_password="", odtuclass_token="tok123"))

    assert list(servers) == ["odtuclass"]
    assert servers["odtuclass"]["env"]["ODTUCLASS_TOKEN"] == "tok123"


def test_empty_env_values_are_omitted_not_blanked():
    # A blank ODTUCLASS_TOKEN would make the upstream client prefer an empty
    # token over falling back to username/password login.
    servers = build_mcp_servers(["odtuclass"], secrets())
    assert "ODTUCLASS_TOKEN" not in servers["odtuclass"]["env"]
    assert servers["odtuclass"]["env"]["ODTUCLASS_PASSWORD"] == "hunter2"


def test_every_server_runs_from_its_own_virtualenv():
    servers = build_mcp_servers([tool.id for tool in CAMPUS_TOOLS], secrets(odtuclass_token="tok"))
    commands = {entry["command"] for entry in servers.values()}
    assert len(commands) == len(servers)
    assert all(command.startswith("/opt/mcp/") for command in commands)


def test_working_dirs_live_on_the_writable_volume():
    dirs = working_directories([tool.id for tool in CAMPUS_TOOLS], secrets())
    assert dirs
    assert all(d.startswith("/opt/data/") for d in dirs)


def test_no_secrets_without_a_bundle():
    assert build_mcp_servers(["sais"], None) == {}


def test_unknown_tool_ids_are_ignored():
    assert normalize_tool_ids(["sais", "not-a-tool"]) == ["sais"]


def test_normalize_preserves_catalog_order_and_dedupes():
    assert normalize_tool_ids(["webmail", "sais", "sais"]) == ["sais", "webmail"]


def test_rendered_config_is_valid_json():
    rendered = render_mcp_config(["sais"], secrets())
    assert json.loads(rendered)["sais"]["args"][0] == "-m"


def test_secrets_repr_does_not_leak_the_password():
    assert "hunter2" not in repr(secrets())
