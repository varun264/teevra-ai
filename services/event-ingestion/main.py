"""TEEVRA Event Ingestion - Pub/Sub / Eventarc adapter (local emulator + cloud)."""

from __future__ import annotations

import hashlib
from typing import Optional


def dedup_key(event_type: str, machine_id: str, timestamp: str) -> str:
    return hashlib.sha256(f"{event_type}:{machine_id}:{timestamp}".encode()).hexdigest()


class EventBus:
    """Local in-memory event bus with the same message contracts as Pub/Sub."""

    def __init__(self):
        self.seen: set[str] = set()
        self.subscribers: list = []

    def is_duplicate(self, key: str) -> bool:
        if key in self.seen:
            return True
        self.seen.add(key)
        return False

    def publish(self, topic: str, payload: dict):
        for sub in self.subscribers:
            sub(topic, payload)
