"""Limit tracking — budget enforcement for API tools."""
from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class DegradedMode:
    """Tracks operations skipped due to tool unavailability."""

    active: bool = False
    skipped_operations: list[dict] = field(default_factory=list)

    def add_skip(self, tool: str, operation: str, reason: str) -> None:
        """Record a skipped operation."""
        self.skipped_operations.append({
            "tool": tool,
            "operation": operation,
            "reason": reason,
        })

    def warning_message(self) -> str:
        """Generate a warning message for all skipped operations."""
        if not self.skipped_operations:
            return ""
        lines = ["⚠ DEGRADED MODE:"]
        for op in self.skipped_operations:
            lines.append(f"  {op['tool']} {op['operation']} skipped — {op['reason']}")
        return "\n".join(lines)


def select_tool_with_fallback(
    preferred_tools: list[str],
    tracker: LimitTracker,
    degraded: DegradedMode,
    operation: str,
) -> str | None:
    """Try tools in order, return first available or None.

    Records skipped tools in degraded mode.

    Args:
        preferred_tools: List of tool names to try in order
        tracker: LimitTracker instance for checking budgets
        degraded: DegradedMode instance to record skips
        operation: Description of the operation (for logging)

    Returns:
        First tool within budget, or None if all exhausted.

    Example:
        tool = select_tool_with_fallback(["codex", "cc"], tracker, degraded, "implement")
        if tool is None:
            # all tools exhausted
    """
    for tool in preferred_tools:
        if tracker.is_within_budget(tool):
            return tool
        degraded.active = True
        degraded.add_skip(tool, operation, f"{tool} limit reached")
    return None
