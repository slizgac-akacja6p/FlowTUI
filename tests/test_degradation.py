"""Tests for degradation mode and limit tracking."""

import tempfile
from pathlib import Path

import pytest

from flowtui.analytics.limits import (
    DegradedMode,
    LimitTracker,
    select_tool_with_fallback,
)
from flowtui.analytics.storage import AnalyticsStorage


class TestDegradedMode:
    """Test DegradedMode tracking."""

    def test_degraded_mode_initial(self):
        """DegradedMode initializes with inactive state."""
        degraded = DegradedMode()
        assert degraded.active is False
        assert degraded.skipped_operations == []

    def test_degraded_mode_add_skip(self):
        """DegradedMode.add_skip records a skipped operation."""
        degraded = DegradedMode()
        degraded.add_skip("cc", "planning", "budget exceeded")

        assert len(degraded.skipped_operations) == 1
        op = degraded.skipped_operations[0]
        assert op["tool"] == "cc"
        assert op["operation"] == "planning"
        assert op["reason"] == "budget exceeded"

    def test_degraded_mode_add_skip_sets_active(self):
        """DegradedMode.add_skip doesn't auto-set active (done separately)."""
        degraded = DegradedMode()
        degraded.add_skip("cc", "planning", "limit reached")
        # active is NOT automatically set by add_skip
        assert degraded.skipped_operations[0]["tool"] == "cc"

    def test_degraded_mode_multiple_skips(self):
        """DegradedMode can record multiple skips."""
        degraded = DegradedMode()
        degraded.add_skip("cc", "planning", "cc limit reached")
        degraded.add_skip("codex", "implementation", "codex limit reached")

        assert len(degraded.skipped_operations) == 2
        assert degraded.skipped_operations[0]["tool"] == "cc"
        assert degraded.skipped_operations[1]["tool"] == "codex"


class TestDegradedModeWarning:
    """Test DegradedMode warning message generation."""

    def test_warning_message_empty(self):
        """Empty skips → empty warning message."""
        degraded = DegradedMode()
        message = degraded.warning_message()
        assert message == ""

    def test_warning_message_single_skip(self):
        """Single skip generates warning message."""
        degraded = DegradedMode()
        degraded.add_skip("cc", "planning", "limit reached")

        message = degraded.warning_message()
        assert "⚠ DEGRADED MODE:" in message
        assert "cc" in message
        assert "planning" in message
        assert "limit reached" in message

    def test_warning_message_multiple_skips(self):
        """Multiple skips formatted with all details."""
        degraded = DegradedMode()
        degraded.add_skip("cc", "planning", "cc budget exceeded")
        degraded.add_skip("codex", "review", "codex unavailable")

        message = degraded.warning_message()
        assert "⚠ DEGRADED MODE:" in message
        assert "cc" in message and "planning" in message
        assert "codex" in message and "review" in message

    def test_warning_message_format(self):
        """Warning message has correct format."""
        degraded = DegradedMode()
        degraded.add_skip("gemini", "docs", "budget exceeded")

        message = degraded.warning_message()
        lines = message.split("\n")
        assert lines[0] == "⚠ DEGRADED MODE:"
        assert "gemini" in lines[1]


class TestLimitTracker:
    """Test LimitTracker — budget enforcement."""

    @pytest.fixture
    def temp_storage(self):
        """Temporary storage for analytics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "analytics.jsonl"
            storage = AnalyticsStorage(storage_path)
            yield storage

    def test_limit_tracker_initial(self, temp_storage):
        """LimitTracker initializes with budgets."""
        tracker = LimitTracker(temp_storage, {"cc": 50, "codex": 20})
        assert tracker.budgets["cc"] == 50
        assert tracker.budgets["codex"] == 20

    def test_today_usage_empty(self, temp_storage):
        """today_usage returns 0 for no records."""
        tracker = LimitTracker(temp_storage, {"cc": 50})
        assert tracker.today_usage("cc") == 0

    def test_today_usage_counts_tool(self, temp_storage):
        """today_usage counts records for specific tool."""
        temp_storage.append({"tool": "cc", "action": "plan"})
        temp_storage.append({"tool": "cc", "action": "review"})
        temp_storage.append({"tool": "codex", "action": "implement"})

        tracker = LimitTracker(temp_storage, {"cc": 50})
        assert tracker.today_usage("cc") == 2
        assert tracker.today_usage("codex") == 1

    def test_is_within_budget_no_budget(self, temp_storage):
        """is_within_budget returns True when no budget configured."""
        tracker = LimitTracker(temp_storage, {})
        assert tracker.is_within_budget("cc") is True

    def test_is_within_budget_zero_budget(self, temp_storage):
        """is_within_budget with zero budget acts as unlimited."""
        tracker = LimitTracker(temp_storage, {"cc": 0})
        assert tracker.is_within_budget("cc") is True

    def test_is_within_budget_below_limit(self, temp_storage):
        """is_within_budget returns True when usage < budget."""
        temp_storage.append({"tool": "cc", "action": "plan"})
        tracker = LimitTracker(temp_storage, {"cc": 10})
        assert tracker.is_within_budget("cc") is True

    def test_is_within_budget_at_limit(self, temp_storage):
        """is_within_budget returns False when usage == budget."""
        temp_storage.append({"tool": "cc", "action": "plan"})
        temp_storage.append({"tool": "cc", "action": "plan"})
        tracker = LimitTracker(temp_storage, {"cc": 2})
        assert tracker.is_within_budget("cc") is False

    def test_is_within_budget_exceeded(self, temp_storage):
        """is_within_budget returns False when usage > budget."""
        for _ in range(5):
            temp_storage.append({"tool": "cc", "action": "plan"})
        tracker = LimitTracker(temp_storage, {"cc": 3})
        assert tracker.is_within_budget("cc") is False

    def test_record_call(self, temp_storage):
        """record_call stores analytics record."""
        tracker = LimitTracker(temp_storage, {"cc": 50})
        tracker.record_call("cc", "planning", 1.5)

        records = temp_storage.read_today()
        assert len(records) == 1
        assert records[0]["tool"] == "cc"
        assert records[0]["action"] == "planning"
        assert records[0]["duration_sec"] == 1.5


class TestSelectToolWithFallback:
    """Test tool selection with fallback."""

    @pytest.fixture
    def temp_storage(self):
        """Temporary storage for analytics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "analytics.jsonl"
            storage = AnalyticsStorage(storage_path)
            yield storage

    def test_select_first_available(self, temp_storage):
        """Returns first tool within budget."""
        tracker = LimitTracker(temp_storage, {"cc": 50, "codex": 20})
        degraded = DegradedMode()

        tool = select_tool_with_fallback(
            ["cc", "codex"], tracker, degraded, "implement"
        )

        assert tool == "cc"

    def test_select_fallback_when_first_exhausted(self, temp_storage):
        """Returns fallback when first tool exhausted."""
        # Exhaust 'cc' budget
        for _ in range(10):
            temp_storage.append({"tool": "cc", "action": "plan"})

        tracker = LimitTracker(temp_storage, {"cc": 10, "codex": 20})
        degraded = DegradedMode()

        tool = select_tool_with_fallback(
            ["cc", "codex"], tracker, degraded, "implement"
        )

        assert tool == "codex"
        assert degraded.active is True
        assert len(degraded.skipped_operations) == 1

    def test_select_all_exhausted_returns_none(self, temp_storage):
        """Returns None when all tools exhausted."""
        for _ in range(15):
            temp_storage.append({"tool": "cc", "action": "plan"})
        for _ in range(15):
            temp_storage.append({"tool": "codex", "action": "plan"})

        tracker = LimitTracker(temp_storage, {"cc": 10, "codex": 10})
        degraded = DegradedMode()

        tool = select_tool_with_fallback(
            ["cc", "codex"], tracker, degraded, "implement"
        )

        assert tool is None
        assert degraded.active is True
        assert len(degraded.skipped_operations) == 2

    def test_select_sets_degraded_active(self, temp_storage):
        """Fallback selection sets degraded.active=True."""
        for _ in range(10):
            temp_storage.append({"tool": "cc", "action": "plan"})

        tracker = LimitTracker(temp_storage, {"cc": 10})
        degraded = DegradedMode()

        tool = select_tool_with_fallback(["cc"], tracker, degraded, "review")

        assert tool is None
        assert degraded.active is True

    def test_select_single_tool_within_budget(self, temp_storage):
        """Single tool list within budget."""
        tracker = LimitTracker(temp_storage, {"cc": 50})
        degraded = DegradedMode()

        tool = select_tool_with_fallback(["cc"], tracker, degraded, "plan")

        assert tool == "cc"
        assert degraded.active is False

    def test_select_records_skip_in_degraded(self, temp_storage):
        """Records why tool was skipped."""
        for _ in range(10):
            temp_storage.append({"tool": "cc", "action": "plan"})

        tracker = LimitTracker(temp_storage, {"cc": 10})
        degraded = DegradedMode()

        select_tool_with_fallback(["cc"], tracker, degraded, "planning")

        assert len(degraded.skipped_operations) > 0
        assert degraded.skipped_operations[0]["reason"] == "cc limit reached"


class TestIntegration:
    """Integration tests combining tracker and degradation."""

    @pytest.fixture
    def temp_storage(self):
        """Temporary storage for analytics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "analytics.jsonl"
            storage = AnalyticsStorage(storage_path)
            yield storage

    def test_full_workflow(self, temp_storage):
        """Full workflow: record calls, check budget, select fallback."""
        tracker = LimitTracker(temp_storage, {"cc": 3, "codex": 5})
        degraded = DegradedMode()

        # Use up most of CC budget
        for i in range(3):
            tracker.record_call("cc", f"action_{i}", 1.0)

        # Try to select tool
        tool = select_tool_with_fallback(
            ["cc", "codex"], tracker, degraded, "implement"
        )

        assert tool == "codex"  # Falls back to codex
        assert degraded.active is True
