"""Check METU credentials before they are stored and shipped into a container.

Deliberately a single SSO sign-in against ``student.metu.edu.tr`` — the same
call ``sais/connector.py`` makes upstream — rather than a round-trip through
an agent container. Provisioning a container to discover a typo takes tens of
seconds; this takes one request, and the failure lands on the onboarding form
where the student can fix it.

Verification is advisory: if METU's SSO is unreachable we say so and let the
student save anyway rather than blocking onboarding on a third party's uptime.
"""

from dataclasses import dataclass

import httpx

from app.logging import get_logger

logger = get_logger(__name__)

SIGNIN_URL = "https://student.metu.edu.tr/sso/backend/request/user/signin"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    # True when we couldn't reach METU at all, as opposed to being told no.
    unreachable: bool = False
    detail: str | None = None


def normalize_username(raw: str) -> str:
    """``e123456@metu.edu.tr`` and ``E123456`` both mean the same account."""
    username = raw.strip()
    if "@" in username:
        username = username.split("@", 1)[0]
    return username.lower()


async def verify_metu_credentials(username: str, password: str, timeout: float = 20.0) -> VerificationResult:
    payload = {"username": normalize_username(username), "password": password}
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json, text/html, */*"},
        ) as client:
            response = await client.post(SIGNIN_URL, json=payload, headers={"X-Requested-With": "XMLHttpRequest"})
    except httpx.HTTPError as exc:
        # Never log the payload — it carries the password.
        logger.warning("metu_verify_unreachable", error=str(exc))
        return VerificationResult(ok=False, unreachable=True, detail="Could not reach METU sign-in right now.")

    if response.status_code != 200:
        return VerificationResult(ok=False, detail="METU rejected the sign-in. Check your username and password.")

    token = response.headers.get("token") or response.headers.get("Token")
    if not token:
        try:
            body = response.json()
            token = body.get("token") if isinstance(body, dict) else None
        except ValueError:
            token = None

    if not token:
        return VerificationResult(ok=False, detail="METU rejected the sign-in. Check your username and password.")

    return VerificationResult(ok=True)
