#!/usr/bin/env python
"""Merge the broker's campus MCP servers into Hermes' own config.yaml.

Runs *inside* the agent container, with Hermes' interpreter, because that's
where ``ruamel.yaml`` lives and where ``$HERMES_HOME`` resolves. The broker
stages a JSON mapping of ``{server_name: entry}`` and execs this; keeping the
merge here means the broker never has to model Hermes' config format beyond
the ``mcp_servers`` entries themselves.

Why merge rather than write the file: config.yaml is Hermes' own, full of
documentation comments and unrelated keys (model, security, fallback_model).
ruamel's round-trip loader preserves all of it.

Why merge rather than replace ``mcp_servers`` wholesale: a student may have
added their own servers with ``hermes mcp add``. Only the names the broker
manages — passed in ``--managed`` — are touched, so a name we no longer ship
is removed while anything they added by hand survives.

Usage:
    apply-campus-mcp.py --staged /path/to/servers.json --managed sais,webmail
"""

import argparse
import json
import os
import sys
from pathlib import Path

from ruamel.yaml import YAML


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", required=True, help="JSON file of {name: entry}")
    parser.add_argument("--managed", default="", help="Comma-separated names the broker owns")
    args = parser.parse_args()

    staged_path = Path(args.staged)
    servers = json.loads(staged_path.read_text("utf-8")) if staged_path.exists() else {}
    managed = {name for name in args.managed.split(",") if name}
    # Anything we're writing is by definition managed, even if the caller's
    # list drifted from the payload.
    managed |= set(servers)

    config_path = Path(os.environ.get("HERMES_HOME", "/opt/data")) / "config.yaml"

    yaml = YAML()
    yaml.preserve_quotes = True
    document = None
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            document = yaml.load(handle)
    if document is None:
        document = {}

    existing = document.get("mcp_servers")
    if not isinstance(existing, dict):
        existing = {}

    # Drop managed names first so a disabled/removed campus tool actually
    # disappears, then add back what the student currently has enabled.
    for name in list(existing):
        if name in managed:
            del existing[name]
    for name, entry in servers.items():
        existing[name] = entry

    if existing:
        document["mcp_servers"] = existing
    elif "mcp_servers" in document:
        del document["mcp_servers"]

    # Write via a temp file in the same directory so a crash mid-write can't
    # leave Hermes with a truncated config it would refuse to start on.
    temp_path = config_path.with_suffix(".yaml.devrimo-tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        yaml.dump(document, handle)
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, config_path)

    # The staged file holds the student's METU password; it has served its
    # purpose the moment the merge lands.
    staged_path.unlink(missing_ok=True)

    print(f"applied {len(servers)} campus mcp server(s): {', '.join(sorted(servers)) or '(none)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
