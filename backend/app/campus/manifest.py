"""What the image actually contains: the commit each campus MCP server was built from.

The image build clones four upstream repos into ``campus_mcp_root`` and then
deletes their ``.git`` directories, so a running container has no way to answer
"which version of the SAIS scraper is this?" from the filesystem. The build
writes :data:`MANIFEST_NAME` before discarding ``.git`` to close that gap.

This matters because those repos are pinned by build arg. A pin nobody can
verify from a running container is a pin on paper: the first question when a
campus tool starts returning nonsense is which commit is serving it, and the
answer should not depend on someone having kept the build logs.

Absent manifest is normal, not an error — local development runs the broker
without the campus servers installed at all.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

MANIFEST_NAME = "MANIFEST"


@dataclass(frozen=True)
class BuildRecord:
    """One entry in the build record: a pinned server, or a patch applied to one.

    A pinned server records ``(slug, commit, repo)``. A source patch applied on
    top of a pin records ``(slug + "-patch", content hash, source path)`` — an
    image carrying an undeclared source change would otherwise report a commit
    it does not actually contain, which is exactly the gap this file exists to
    close.
    """

    slug: str
    commit: str
    repo: str


@lru_cache(maxsize=8)
def read_manifest(mcp_root: str) -> tuple[BuildRecord, ...]:
    """Parse the build manifest under ``mcp_root``; empty if there isn't one.

    Cached because the file is baked into the image and cannot change while the
    process lives. Call ``read_manifest.cache_clear()`` in tests that write one.
    """
    path = Path(mcp_root) / MANIFEST_NAME
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        # No manifest, unreadable, or no such root: all mean "this deployment
        # has no campus servers installed", which is a normal local-dev state.
        return ()

    records: list[BuildRecord] = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) != 3:
            # A malformed line is a build bug, but reporting three servers is
            # strictly better than failing the health check over the fourth.
            continue
        slug, commit, repo = parts
        records.append(BuildRecord(slug=slug, commit=commit, repo=repo))
    return tuple(records)


def commits_by_slug(mcp_root: str) -> dict[str, str]:
    """Manifest as a plain ``{slug: commit}`` mapping, for serialising."""
    return {record.slug: record.commit for record in read_manifest(mcp_root)}
