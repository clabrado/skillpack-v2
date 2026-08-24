from __future__ import annotations

import json
from datetime import datetime, timezone
from .paths import AUDIT_PATH, ensure_latch_home


def append_audit(entry: dict) -> None:
    ensure_latch_home()
    line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **entry})
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    try:
        AUDIT_PATH.chmod(0o600)
    except OSError:
        pass
