"""The registry of campus MCP servers that can be attached to a user's agent.

Each entry describes one Model Context Protocol server that is vendored into
the ``devrimo/hermes`` image (see ``images/hermes/``) and launched *inside*
that user's own container over stdio. Running them in-container rather than
as shared HTTP services is deliberate: three of the four upstream servers are
single-tenant and read their credentials from process environment, and the
per-user container is already this system's isolation boundary. One student's
METU password never enters another student's process.

``env_template`` values are rendered by :mod:`app.campus.mcp_config` against a
:class:`~app.campus.credentials.CampusSecrets` bundle. Keys whose value renders
empty are dropped, so a server that needs a credential the student hasn't
supplied simply never appears in the generated config.
"""

from dataclasses import dataclass, field
from typing import Literal

# Credentials a server can require. The onboarding UI asks for the union of
# every requirement across the tools the student chose to enable.
CredentialKind = Literal["metu_password", "odtuclass"]


@dataclass(frozen=True)
class CampusTool:
    id: str
    name_en: str
    name_tr: str
    description_en: str
    description_tr: str
    # What the student is trusting this server with, in their own words. Shown
    # verbatim in onboarding — this is the consent copy, not decoration.
    scope_en: str
    scope_tr: str
    requires: tuple[CredentialKind, ...]
    command: str
    args: tuple[str, ...]
    env_template: dict[str, str] = field(default_factory=dict)
    # Working directory inside the container. Servers that cache session
    # tokens relative to CWD need this to point at the writable data volume.
    cwd: str | None = None
    default_enabled: bool = True


# Every server is installed into its own virtualenv under /opt/mcp by the
# image build, so each one gets an interpreter with only its own dependency
# tree — upstream pins conflict (mcp vs fastmcp, pydantic ranges) and a single
# shared site-packages would make the set unresolvable.
_VENV = "/opt/mcp/{slug}/.venv/bin/python"

CAMPUS_TOOLS: tuple[CampusTool, ...] = (
    CampusTool(
        id="sais",
        name_en="SAIS student portal",
        name_tr="SAIS öğrenci portalı",
        description_en="Transcript, GPA, weekly schedule, and portal announcements",
        description_tr="Transkript, ortalama, haftalık ders programı ve portal duyuruları",
        scope_en="Reads your student record from student.metu.edu.tr. Read-only.",
        scope_tr="student.metu.edu.tr üzerindeki öğrenci kaydını okur. Salt okunur.",
        requires=("metu_password",),
        command=_VENV.format(slug="sais"),
        args=("-m", "sais_mcp.server", "--transport", "stdio"),
        env_template={
            "SAIS_USERNAME": "{metu_username}",
            "SAIS_PASSWORD": "{metu_password}",
            "LOCALE": "{locale}",
        },
        cwd="/opt/data/mcp/sais",
    ),
    CampusTool(
        id="course_info",
        name_en="Course catalog",
        name_tr="Ders kataloğu",
        description_en="Course codes, sections, prerequisites, ECTS, and curriculum categories",
        description_tr="Ders kodları, şubeler, ön koşullar, AKTS ve müfredat kategorileri",
        scope_en="Reads the METU course catalog and your curriculum requirements. Read-only.",
        scope_tr="ODTÜ ders kataloğunu ve müfredat gereksinimlerini okur. Salt okunur.",
        requires=("metu_password",),
        command=_VENV.format(slug="course-info"),
        args=("-m", "metu_course_info_mcp", "--transport", "stdio"),
        env_template={
            "SAIS_USERNAME": "{metu_username}",
            "SAIS_PASSWORD": "{metu_password}",
            "LOCALE": "{locale}",
        },
        cwd="/opt/data/mcp/course-info",
    ),
    CampusTool(
        id="odtuclass",
        name_en="ODTÜClass",
        name_tr="ODTÜClass",
        description_en="Enrolled courses, announcements, syllabi, and upcoming assignment deadlines",
        description_tr="Kayıtlı dersler, duyurular, izlenceler ve yaklaşan ödev teslimleri",
        scope_en="Reads your ODTÜClass courses and deadlines. Read-only.",
        scope_tr="ODTÜClass derslerini ve teslim tarihlerini okur. Salt okunur.",
        requires=("odtuclass",),
        command=_VENV.format(slug="odtuclass"),
        args=("/opt/mcp/odtuclass/odtuclass_mcp.py",),
        env_template={
            "ODTUCLASS_USERNAME": "{metu_username}",
            "ODTUCLASS_PASSWORD": "{metu_password}",
            "ODTUCLASS_TOKEN": "{odtuclass_token}",
            "ODTUCLASS_BASE_URL": "{odtuclass_base_url}",
        },
        # The upstream client caches its Moodle session token under
        # ``os.getcwd()/.odtuclass_cache`` and writes downloads next to it, so
        # its CWD has to be on the writable per-user volume.
        cwd="/opt/data/mcp/odtuclass",
    ),
    CampusTool(
        id="webmail",
        name_en="METU webmail",
        name_tr="ODTÜ webmail",
        description_en="Read, search, and send mail from your @metu.edu.tr account",
        description_tr="@metu.edu.tr hesabında posta okuma, arama ve gönderme",
        scope_en=(
            "Reads your METU mailbox over IMAP and can send mail as you over SMTP. "
            "This is the only campus tool that can act on your behalf."
        ),
        scope_tr=(
            "ODTÜ posta kutunu IMAP ile okur ve senin adına SMTP ile posta gönderebilir. "
            "Senin adına işlem yapabilen tek kampüs aracı budur."
        ),
        requires=("metu_password",),
        command=_VENV.format(slug="webmail"),
        args=("-m", "metu_webmail_mcp", "--transport", "stdio"),
        env_template={
            "METU_USERNAME": "{metu_username}",
            "METU_PASSWORD": "{metu_password}",
            "LOCALE": "{locale}",
        },
        cwd="/opt/data/mcp/webmail",
        # Opt-in: it can send mail as the student, so it should be a decision
        # they make rather than a default they discover afterwards.
        default_enabled=False,
    ),
)

TOOLS_BY_ID: dict[str, CampusTool] = {tool.id: tool for tool in CAMPUS_TOOLS}
TOOL_IDS: frozenset[str] = frozenset(TOOLS_BY_ID)
DEFAULT_ENABLED_TOOL_IDS: tuple[str, ...] = tuple(t.id for t in CAMPUS_TOOLS if t.default_enabled)


def normalize_tool_ids(tool_ids: list[str] | None) -> list[str]:
    """Drop unknown ids and de-duplicate, preserving catalog order.

    Unknown ids are dropped rather than rejected so that removing a tool from
    the catalog doesn't 500 every request from a client that still remembers it.
    """
    if tool_ids is None:
        return list(DEFAULT_ENABLED_TOOL_IDS)
    requested = set(tool_ids)
    return [tool.id for tool in CAMPUS_TOOLS if tool.id in requested]
