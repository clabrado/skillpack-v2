from __future__ import annotations

import hmac
import secrets
from .paths import TOKEN_PATH, ensure_latch_home


def ensure_token() -> str:
    ensure_latch_home()
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text().strip()
    token = secrets.token_hex(32)
    TOKEN_PATH.write_text(token + "\n")
    TOKEN_PATH.chmod(0o600)
    return token


def read_token() -> str:
    return ensure_token()


def token_matches(header_val: str | None) -> bool:
    expected = read_token()
    if not header_val:
        return False
    provided = header_val
    if header_val.lower().startswith("bearer "):
        provided = header_val[7:].strip()
    else:
        provided = header_val.strip()
    return hmac.compare_digest(provided, expected)
