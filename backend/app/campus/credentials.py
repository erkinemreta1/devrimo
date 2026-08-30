"""The plaintext credential bundle, assembled only where it is actually needed.

Everywhere else in the app a student's METU password exists solely as the
Fernet ciphertext in ``campus_credentials.metu_password_enc``. This module is
the one place it is decrypted, and :class:`CampusSecrets` exists so the value
is never carried around inside a dict that might get logged or serialized —
``repr`` is overridden and the model is never a response type.
"""

from dataclasses import dataclass

from app.core.crypto import decrypt_secret
from app.db.models import CampusCredential


@dataclass(frozen=True)
class CampusSecrets:
    metu_username: str
    metu_password: str
    odtuclass_token: str
    locale: str
    odtuclass_base_url: str

    def __repr__(self) -> str:  # pragma: no cover - defensive, not behaviour
        return f"CampusSecrets(metu_username={self.metu_username!r}, ...redacted)"

    def as_template_values(self) -> dict[str, str]:
        return {
            "metu_username": self.metu_username,
            "metu_password": self.metu_password,
            "odtuclass_token": self.odtuclass_token,
            "locale": self.locale,
            "odtuclass_base_url": self.odtuclass_base_url,
        }

    def has(self, kind: str) -> bool:
        """Whether the credential a catalog entry declares in ``requires`` is present."""
        if kind == "metu_password":
            return bool(self.metu_username and self.metu_password)
        if kind == "odtuclass":
            # Either half works: the upstream server accepts a Moodle web
            # service token directly, or logs in with the METU credentials.
            return bool(self.odtuclass_token) or bool(self.metu_username and self.metu_password)
        return False


def secrets_for(credential: CampusCredential | None) -> CampusSecrets | None:
    if credential is None:
        return None
    return CampusSecrets(
        metu_username=credential.metu_username or "",
        metu_password=decrypt_secret(credential.metu_password_enc) if credential.metu_password_enc else "",
        odtuclass_token=decrypt_secret(credential.odtuclass_token_enc) if credential.odtuclass_token_enc else "",
        locale=credential.locale or "tr",
        odtuclass_base_url=credential.odtuclass_base_url or "",
    )
