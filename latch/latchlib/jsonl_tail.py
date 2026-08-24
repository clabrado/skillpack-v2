from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable

from .paths import project_jsonl_dir
from .payload_gate import gate_tool_result, gate_tool_use, scrub_text


class JsonlTailer:
    def __init__(self, publish: Callable, sid: str, on_unknown: Callable | None = None):
        self.publish = publish
        self.sid = sid
        self.on_unknown = on_unknown
        self.path: Path | None = None
        self.offset = 0
        self.buf = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.started_at = time.time()
        # tool_use_id -> (tool_name, is_sensitive) — populated when a
        # tool_use frame is built, consulted when the matching tool_result
        # frame arrives later (possibly in a different JSONL line/tick).
        # See latchlib/sensitive.py / ticket #1899 Vector B.
        self.tool_sensitivity: dict[str, tuple[str, bool]] = {}

    def set_path(self, transcript_path: str | None) -> None:
        if not transcript_path:
            return
        p = Path(transcript_path)
        if self.path == p:
            return
        self.path = p
        self.buf = ""
        try:
            self.offset = p.stat().st_size if p.exists() else 0
        except OSError:
            self.offset = 0

    def discover(self, cwd: str, claimed: set[str] | None = None) -> Path | None:
        """
        Pick a transcript for THIS latch session only.

        Multi-session safety:
        - Prefer files modified after this supervisor started.
        - Never take a path already claimed by another live latch session.
        - Prefer the newest unclaimed file among candidates (not global newest,
          which races when many Claudes run in the same cwd).
        """
        d = project_jsonl_dir(cwd)
        if not d.exists():
            return None
        claimed = claimed or set()
        claimed_resolved = set()
        for c in claimed:
            try:
                claimed_resolved.add(str(Path(c).resolve()))
            except Exception:
                claimed_resolved.add(c)

        candidates: list[tuple[float, Path]] = []
        for p in d.glob("*.jsonl"):
            if "subagents" in str(p):
                continue
            try:
                rp = str(p.resolve())
            except Exception:
                rp = str(p)
            if rp in claimed_resolved or str(p) in claimed:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            # created/touched around or after our spawn
            if st.st_mtime < self.started_at - 5:
                continue
            candidates.append((st.st_mtime, p))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def start(self, poll_ms: int = 200) -> None:
        if self._thread and self._thread.is_alive():
            return

        def loop():
            while not self._stop.is_set():
                self.tick()
                time.sleep(poll_ms / 1000)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def tick(self) -> None:
        if not self.path:
            return
        try:
            st = self.path.stat()
        except OSError:
            return
        if st.st_size < self.offset:
            self.offset = 0
            self.buf = ""
        if st.st_size == self.offset:
            return
        try:
            with open(self.path, "rb") as f:
                f.seek(self.offset)
                data = f.read()
                self.offset = st.st_size
        except OSError:
            return
        self.buf += data.decode("utf-8", errors="replace")
        parts = self.buf.split("\n")
        self.buf = parts.pop() or ""
        for line in parts:
            if not line.strip():
                continue
            self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            return
        frames = map_record(rec, self.sid, self.tool_sensitivity)
        if not frames:
            if self.on_unknown:
                self.on_unknown()
            return
        for fr in frames:
            self.publish(fr)


def map_record(rec: dict, sid: str, tool_sensitivity: dict | None = None) -> list[dict]:
    ts = int(time.time() * 1000)
    base = {"v": 1, "t": "evt", "ts": ts, "sid": sid}
    typ = rec.get("type")
    if tool_sensitivity is None:
        tool_sensitivity = {}

    if typ in ("assistant", "user"):
        content = (rec.get("message") or {}).get("content", rec.get("content"))
        return content_to_frames(content, typ, base, rec, tool_sensitivity)

    msg = rec.get("message") or {}
    if msg.get("role") in ("assistant", "user"):
        return content_to_frames(msg.get("content"), msg["role"], base, rec, tool_sensitivity)

    return []


def content_to_frames(
    content, role: str, base: dict, rec: dict, tool_sensitivity: dict | None = None
) -> list[dict]:
    if tool_sensitivity is None:
        tool_sensitivity = {}
    frames = []
    if isinstance(content, str):
        frames.append(
            {
                **base,
                "kind": "user_text" if role == "user" else "assistant_text",
                "text": scrub_text(content),
                "uuid": rec.get("uuid"),
            }
        )
        return frames
    if not isinstance(content, list):
        return frames

    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            text_parts.append(block["text"])
        elif block.get("type") == "tool_use":
            if text_parts:
                frames.append(
                    {
                        **base,
                        "kind": "assistant_text",
                        "text": scrub_text("".join(text_parts)),
                        "uuid": rec.get("uuid"),
                    }
                )
                text_parts = []
            tool_name = block.get("name")
            input_str = json.dumps(block.get("input") or {})[:500]
            sensitive, input_summary = gate_tool_use(tool_name, input_str)
            tool_use_id = block.get("id")
            if tool_use_id:
                tool_sensitivity[tool_use_id] = (tool_name, sensitive)
            frames.append(
                {
                    **base,
                    "kind": "tool_use",
                    "tool": tool_name,
                    "input_summary": input_summary,
                    "tool_use_id": tool_use_id,
                    "uuid": rec.get("uuid"),
                }
            )
        elif block.get("type") == "tool_result":
            raw = block.get("content")
            if not isinstance(raw, str):
                raw = json.dumps(raw or "")
            ok = not block.get("is_error")
            tool_use_id = block.get("tool_use_id")
            _tool_name, sensitive = tool_sensitivity.get(tool_use_id, (None, False))
            preview = gate_tool_result(sensitive, ok, raw)
            frames.append(
                {
                    **base,
                    "kind": "tool_result",
                    "ok": ok,
                    "preview": preview,
                    "tool_use_id": tool_use_id,
                    "uuid": rec.get("uuid"),
                }
            )
    if text_parts:
        frames.append(
            {
                **base,
                "kind": "user_text" if role == "user" else "assistant_text",
                "text": scrub_text("".join(text_parts)),
                "uuid": rec.get("uuid"),
            }
        )
    return frames
