"""Notifier port. A run fires exactly one notification with its summary at the end."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    def notify(self, message: str) -> None: ...
