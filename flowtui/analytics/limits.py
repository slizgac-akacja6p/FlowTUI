"""Limit tracking — budget enforcement for API tools."""
from __future__ import annotations

from datetime import date, datetime
from .storage import AnalyticsStorage
from pathlib import Path


class LimitTracker:
    """Track daily API call limits and enforce budgets."""

    def __init__(self, storage: AnalyticsStorage, budgets: dict[str, int]) -> None:
        """Initialize tracker with storage and daily budgets per tool.

        Args:
            storage: AnalyticsStorage instance for reading records
            budgets: Dict mapping tool names to daily limits (e.g. {"claude": 15})
        """
        self.storage = storage
        self.budgets = budgets

    def today_usage(self, tool: str) -> int:
        """Get today's API call count for a tool."""
        records = self.storage.read_today()
        return sum(
            1 for record in records
            if record.get("tool") == tool
        )

    def is_within_budget(self, tool: str) -> bool:
        """Check if tool is within today's budget.

        Returns True if:
        - No budget configured for tool (no limit)
        - Current usage < budget
        """
        budget = self.budgets.get(tool)
        if budget is None or budget <= 0:
            return True  # No limit configured
        usage = self.today_usage(tool)
        return usage < budget

    def record_call(self, tool: str, action: str, duration_sec: float = 0.0) -> None:
        """Record an API call."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool,
            "action": action,
            "duration_sec": duration_sec,
        }
        self.storage.append(record)
