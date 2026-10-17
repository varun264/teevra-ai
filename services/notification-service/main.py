"""TEEVRA Notification Service - Firebase Cloud Messaging adapter (mock in local)."""

from __future__ import annotations


class NotificationProvider:
    def send(self, token: str, title: str, body: str, data: dict | None = None) -> dict:
        raise NotImplementedError


class MockNotificationProvider(NotificationProvider):
    """Local demo provider: records notifications, no real push."""

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, token, title, body, data=None) -> dict:
        record = {"token": token, "title": title, "body": body, "data": data or {}, "delivered": True}
        self.sent.append(record)
        return record


PROVIDER = MockNotificationProvider()
