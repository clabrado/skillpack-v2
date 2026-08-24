from __future__ import annotations

import threading
from collections import deque

CLIENT_QUEUE_CAP = 1000


class _Client:
    """Per-subscriber bounded queue. Producers never block; overflow drops oldest."""

    def __init__(self, cid: int):
        self.id = cid
        self.q: deque = deque()
        self.cond = threading.Condition()
        self.dropped = 0
        self.closed = False

    def offer(self, frame: dict) -> None:
        with self.cond:
            if self.closed:
                return
            if len(self.q) >= CLIENT_QUEUE_CAP:
                self.q.popleft()
                self.dropped += 1
            self.q.append(frame)
            self.cond.notify()

    def pop(self, timeout: float) -> dict | None:
        with self.cond:
            if not self.q:
                self.cond.wait(timeout)
            if self.q:
                return self.q.popleft()
            return None

    def close(self) -> None:
        with self.cond:
            self.closed = True
            self.cond.notify()


class EventBus:
    """
    Non-blocking pub/sub.

    publish() only appends to per-client deques — it is safe to call from the
    PTY pump thread: a slow or dead SSE consumer can never stall the terminal.
    Each consumer drains its own queue on its own (HTTP handler) thread, so all
    socket writes for one client happen on exactly one thread.
    """

    def __init__(self, capacity: int = 5000):
        self.capacity = capacity
        self.frames: deque = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._clients: list[_Client] = []
        self._next_id = 1
        self.unknown_jsonl = 0

    def publish(self, frame: dict) -> None:
        with self._lock:
            self.frames.append(frame)
            clients = list(self._clients)
        for c in clients:
            c.offer(frame)

    def subscribe(self) -> _Client:
        with self._lock:
            c = _Client(self._next_id)
            self._next_id += 1
            self._clients.append(c)
            return c

    def unsubscribe(self, client: _Client) -> None:
        client.close()
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)

    def replay(self, n: int) -> list:
        if not n or n <= 0:
            return []
        with self._lock:
            items = list(self.frames)
        return items[-n:]

    def total_dropped(self) -> int:
        with self._lock:
            return sum(c.dropped for c in self._clients)

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)
