# The devrimo/hermes image: nousresearch/hermes-agent, seeded with the
# campus persona and (once real campus MCP servers exist) their config.
#
# Deliberately does NOT override ENTRYPOINT/CMD — the base image already
# handles privilege dropping to its unprivileged runtime user (see its own
# docs on `HERMES_UID`/the `hermes` exec shim), and re-implementing that
# here without being able to verify it against a running container is how
# you accidentally undo someone else's security hardening. Seed files are
# copied in at a fixed path and installed into the writable /opt/data
# volume at container-create time instead — see
# app/agents/docker_runtime.py's `_seed_data_sync`.

ARG HERMES_BASE_IMAGE=nousresearch/hermes-agent:latest
FROM ${HERMES_BASE_IMAGE}

COPY SOUL.md /opt/devrimo/seed/SOUL.md
COPY mcp/campus.mcp.json.example /opt/devrimo/seed/campus.mcp.json.example
