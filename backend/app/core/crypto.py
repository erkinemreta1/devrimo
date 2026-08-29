import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import get_settings


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    return Fernet(_derive_fernet_key(settings.secret_encryption_key))


def encrypt_secret(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_secret(ciphertext: bytes) -> str:
    return _fernet().decrypt(ciphertext).decode("utf-8")
