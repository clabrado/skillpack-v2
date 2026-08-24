from __future__ import annotations

import shutil
import time
from pathlib import Path

REPO_SKILLS = Path(__file__).resolve().parent.parent / "skills"
CLAUDE_SKILLS = Path.home() / ".claude" / "skills"

# skills bundled in this repo that /steer (and latch generally) depend on
SKILLS = ("steer", "drive")


def install() -> int:
    CLAUDE_SKILLS.mkdir(parents=True, exist_ok=True)
    for name in SKILLS:
        src = REPO_SKILLS / name
        dst = CLAUDE_SKILLS / name
        if not src.is_dir():
            print(f"skip {name}: not found at {src}")
            continue
        if dst.exists() and not dst.is_symlink():
            backup = dst.with_name(f"{name}.bak-latch-{int(time.time() * 1000)}")
            shutil.move(str(dst), str(backup))
            print(f"backup: {backup}")
        elif dst.is_symlink() or dst.exists():
            dst.unlink()
        dst.symlink_to(src)
        print(f"installed skill {name} -> {dst} (symlink to {src})")
    return 0


def uninstall() -> int:
    for name in SKILLS:
        dst = CLAUDE_SKILLS / name
        if dst.is_symlink() and dst.resolve() == (REPO_SKILLS / name).resolve():
            dst.unlink()
            print(f"removed skill {name}")
        else:
            print(f"skip {name}: not a latch-managed symlink")
    return 0
