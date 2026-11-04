"""Encrypted document vault. Raw images are encrypted at rest (Fernet / AES-128-CBC + HMAC)
and deleted as soon as they are no longer needed; only extracted fields and a hash remain."""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet

from ..config import VAR_DIR

RETENTION_DAYS_REVIEW = 7  # raw images kept only while a human review is pending


def _dir() -> Path:
    d = Path(os.getenv("UDYAM_VAULT_DIR", VAR_DIR / "vault"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key() -> bytes:
    env = os.getenv("UDYAM_VAULT_KEY")
    if env:
        return env.encode()
    kf = _dir() / ".key"
    if not kf.exists():
        kf.write_bytes(Fernet.generate_key())
        kf.chmod(0o600)
    return kf.read_bytes()


def put(case_id: str, doc_id: str, data: bytes) -> str:
    folder = _dir() / case_id
    folder.mkdir(exist_ok=True)
    ref = f"{case_id}/{doc_id}.bin"
    (_dir() / ref).write_bytes(Fernet(_key()).encrypt(data))
    return ref


def get(ref: str) -> bytes | None:
    p = _dir() / ref
    return Fernet(_key()).decrypt(p.read_bytes()) if p.exists() else None


def delete(ref: str | None) -> None:
    if ref:
        p = _dir() / ref
        if p.exists():
            p.unlink()
