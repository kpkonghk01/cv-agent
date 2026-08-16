"""No-op Notifier — the v1 default. A Slack adapter slots in here later."""

from __future__ import annotations


class NullNotifier:
    def notify(self, message: str) -> None:
        return None
