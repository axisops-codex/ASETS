"""Encryption for the few fields that must not be readable in a dump.

HMRC access and refresh tokens let anyone holding them file a tax return
in the user's name, and a National Insurance number is high-value
personal data. Both are encrypted in the application so that a database
backup, a replica, or a support query never exposes them.

The key lives in Secret Manager and is injected as TOKEN_ENCRYPTION_KEY.
"""
from __future__ import annotations

import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class EncryptionUnavailable(RuntimeError):
    pass


_cipher: Optional[Fernet] = None


def _get_cipher() -> Fernet:
    global _cipher
    if _cipher is not None:
        return _cipher
    key = os.environ.get("TOKEN_ENCRYPTION_KEY", "").strip()
    if not key:
        raise EncryptionUnavailable(
            "TOKEN_ENCRYPTION_KEY is not set — HMRC features are disabled")
    try:
        _cipher = Fernet(key.encode())
    except Exception as e:
        raise EncryptionUnavailable(f"TOKEN_ENCRYPTION_KEY is not a valid Fernet key: {e}")
    return _cipher


def available() -> bool:
    try:
        _get_cipher()
        return True
    except EncryptionUnavailable:
        return False


def encrypt(plaintext: str) -> bytes:
    return _get_cipher().encrypt(plaintext.encode())


def decrypt(ciphertext: bytes) -> str:
    try:
        return _get_cipher().decrypt(bytes(ciphertext)).decode()
    except InvalidToken:
        # Almost always a rotated key against old rows. Callers turn this
        # into "reconnect to HMRC" rather than a 500.
        raise EncryptionUnavailable("stored value cannot be decrypted with the current key")


def encrypt_optional(plaintext: Optional[str]) -> Optional[bytes]:
    return encrypt(plaintext) if plaintext else None


def decrypt_optional(ciphertext: Optional[bytes]) -> Optional[str]:
    return decrypt(ciphertext) if ciphertext else None


def generate_key() -> str:
    """Used by scripts/gen_secrets.py."""
    return Fernet.generate_key().decode()
