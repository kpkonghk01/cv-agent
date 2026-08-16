"""Notification hook (seam for Slack etc.; v1 is a no-op) — see AGENT.md."""

from __future__ import annotations

from cv_agent.notify.null import NullNotifier
from cv_agent.notify.ports import Notifier

__all__ = ["Notifier", "NullNotifier"]
