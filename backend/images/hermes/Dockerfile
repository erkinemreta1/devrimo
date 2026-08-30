# The devrimo/hermes image: nousresearch/hermes-agent, seeded with the campus
# persona and the four METU campus MCP servers.
#
# The servers are baked into the image but carry no credentials. Each student's
# container gets its own `mcp_servers` block merged into /opt/data/config.yaml
# at container-create time by app/agents/docker_runtime.py, supplying that
# student's METU credentials as per-server process environment. One image, N
# isolated credential sets, none of them in a layer. See CAMPUS-MCP.md.
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
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.5.11

# --- Stage 1: build one isolated virtualenv per MCP server -----------------
#
# Separate venvs rather than one shared site-packages because the four upstream
# projects don't co-resolve: metu-webmail-mcp needs `fastmcp`, the others pin
# `mcp` directly, and their pydantic/httpx ranges overlap only by luck.
# Isolating them means upgrading one server can never break another.
#
# The interpreter is a uv-managed standalone build installed *under /opt/mcp*
# rather than the builder's own /usr/local python, because the whole tree is
# copied into an unrelated base image in stage 2. Everything the venvs point at
# has to travel with them, at the same absolute path they were built at.
FROM ${UV_IMAGE} AS uv

FROM python:3.11-slim AS mcp-builder

COPY --from=uv /uv /usr/local/bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON_INSTALL_DIR=/opt/mcp/python \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

RUN uv python install 3.11

# Refs are build args so a deployment can pin each server to a reviewed commit.
# The defaults track the upstream default branches; pin them to SHAs before
# this serves real students, or an agent's behaviour changes whenever someone
# pushes.
ARG SAIS_REPO=https://github.com/atesahmet0/metu-sais-mcp.git
ARG SAIS_REF=master
ARG COURSE_INFO_REPO=https://github.com/atesahmet0/metu-course-info-mcp.git
ARG COURSE_INFO_REF=main
ARG WEBMAIL_REPO=https://github.com/atesahmet0/metu-webmail-mcp.git
ARG WEBMAIL_REF=main
ARG ODTUCLASS_REPO=https://github.com/erkinemreta1/metu-odtuclass-mcp.git
ARG ODTUCLASS_REF=main

RUN set -eux; \
    for entry in \
        "sais|${SAIS_REPO}|${SAIS_REF}" \
        "course-info|${COURSE_INFO_REPO}|${COURSE_INFO_REF}" \
        "webmail|${WEBMAIL_REPO}|${WEBMAIL_REF}" \
        "odtuclass|${ODTUCLASS_REPO}|${ODTUCLASS_REF}" \
    ; do \
        slug="${entry%%|*}"; rest="${entry#*|}"; \
        repo="${rest%%|*}"; ref="${rest##*|}"; \
        git clone "${repo}" "/opt/mcp/${slug}"; \
        git -C "/opt/mcp/${slug}" checkout --quiet "${ref}"; \
        rm -rf "/opt/mcp/${slug}/.git"; \
        uv venv --python 3.11 "/opt/mcp/${slug}/.venv"; \
    done

# Installed as a built wheel, not `-e`, so nothing at runtime depends on the
# source tree layout surviving. metu-odtuclass-mcp ships loose modules and a
# requirements.txt rather than an installable package, so it gets its
# dependencies installed and is launched by script path instead — see
# app/campus/catalog.py.
RUN set -eux; \
    for slug in sais course-info webmail; do \
        VIRTUAL_ENV="/opt/mcp/${slug}/.venv" uv pip install "/opt/mcp/${slug}"; \
    done; \
    VIRTUAL_ENV=/opt/mcp/odtuclass/.venv uv pip install -r /opt/mcp/odtuclass/requirements.txt

# --- Stage 2: the agent image ---------------------------------------------
FROM ${HERMES_BASE_IMAGE}

COPY --from=mcp-builder /opt/mcp /opt/mcp

# Import each server with the interpreter that will actually launch it, in the
# image it will actually run in. This is the step that catches a base image
# whose libc the standalone interpreter can't run against — better a failed
# build than four campus tools that silently never start.
RUN set -eux; \
    /opt/mcp/sais/.venv/bin/python -c "import sais_mcp.server"; \
    /opt/mcp/course-info/.venv/bin/python -c "import metu_course_info_mcp.__main__"; \
    /opt/mcp/webmail/.venv/bin/python -c "import metu_webmail_mcp.server"; \
    cd /opt/mcp/odtuclass && /opt/mcp/odtuclass/.venv/bin/python -c "import odtuclass_mcp"

COPY SOUL.md /opt/devrimo/seed/SOUL.md

# Merges the broker's campus servers into Hermes' own config.yaml. Runs with
# Hermes' interpreter (which has ruamel.yaml) — see the script's docstring.
COPY bin/apply-campus-mcp.py /opt/devrimo/bin/apply-campus-mcp.py
