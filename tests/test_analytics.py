"""Tests for analytics storage and limit tracking."""
import tempfile
from pathlib import Path
from datetime import datetime, date, timedelta
from threading import Thread
import time

import pytest

from flowtui.analytics.storage import AnalyticsStorage
from flowtui.analytics.limits import LimitTracker


class TestAnalyticsStorage:
    """Test AnalyticsStorage append-only log."""

    def test_storage_append_and_read(self):
        """Append a record and read it back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")

            record = {"tool": "claude", "action": "plan", "duration_sec": 1.5}
            storage.append(record)

            records = storage.read_all()
            assert len(records) == 1
            assert records[0]["tool"] == "claude"
            assert records[0]["action"] == "plan"
            assert records[0]["duration_sec"] == 1.5

    def test_storage_append_adds_timestamp(self):
        """Append automatically adds timestamp if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")

            record = {"tool": "claude", "action": "code"}
            storage.append(record)

            records = storage.read_all()
            assert len(records) == 1
            assert "timestamp" in records[0]

    def test_storage_read_today_filters_old(self):
        """read_today returns only today's records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")

            # Append today's record
            today = datetime.now()
            storage.append({
                "timestamp": today.isoformat(),
                "tool": "claude",
                "action": "today",
            })

            # Manually append yesterday's record (bypassing timestamp auto-add)
            yesterday = today - timedelta(days=1)
            with open(storage.filepath, "a", encoding="utf-8") as f:
                f.write('{"timestamp": "' + yesterday.isoformat() + '", "tool": "claude", "action": "yesterday"}\n')

            today_records = storage.read_today()
            # Should have 1 today's record
            assert len(today_records) == 1
            assert today_records[0].get("action") == "today"

    def test_storage_read_all_empty(self):
        """read_all returns empty list for new file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")
            records = storage.read_all()
            assert records == []

    def test_storage_read_today_empty(self):
        """read_today returns empty list for empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")
            records = storage.read_today()
            assert records == []

    def test_storage_multiple_appends(self):
        """Append multiple records in order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")

            for i in range(5):
                storage.append({"tool": "claude", "action": f"action{i}"})

            records = storage.read_all()
            assert len(records) == 5
            assert records[0]["action"] == "action0"
            assert records[4]["action"] == "action4"

    def test_storage_thread_safe(self):
        """Concurrent appends are thread-safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")

            def append_records(thread_id):
                for i in range(10):
                    storage.append({
                        "thread": thread_id,
                        "iteration": i,
                    })

            threads = [Thread(target=append_records, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            records = storage.read_all()
            # Should have 30 records (3 threads × 10 each)
            assert len(records) == 30

    def test_storage_handles_malformed_json(self):
        """Malformed JSON lines are skipped gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "analytics.jsonl"
            filepath.write_text('{"valid": "record"}\ninvalid json line\n{"another": "valid"}')

            storage = AnalyticsStorage(filepath)
            records = storage.read_all()
            # Should skip the invalid line and read the 2 valid ones
            assert len(records) == 2


class TestLimitTracker:
    """Test API call limit tracking."""

    def test_limit_tracker_within_budget(self):
        """is_within_budget returns True when under limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")
            tracker = LimitTracker(storage, {"claude": 10})

            # Record 3 calls
            for _ in range(3):
                tracker.record_call("claude", "plan")

            assert tracker.is_within_budget("claude") is True

    def test_limit_tracker_over_budget(self):
        """is_within_budget returns False when at or over limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")
            tracker = LimitTracker(storage, {"claude": 5})

            # Record 5 calls (at limit)
            for _ in range(5):
                tracker.record_call("claude", "plan")

            assert tracker.is_within_budget("claude") is False

    def test_limit_tracker_today_usage(self):
        """today_usage counts today's calls only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")
            tracker = LimitTracker(storage, {"claude": 20})

            # Record 7 calls
            for _ in range(7):
                tracker.record_call("claude", "code")

            assert tracker.today_usage("claude") == 7

    def test_limit_tracker_record_call(self):
        """record_call stores tool, action, and duration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")
            tracker = LimitTracker(storage, {"claude": 10})

            tracker.record_call("claude", "review", 2.5)

            records = storage.read_all()
            assert len(records) == 1
            assert records[0]["tool"] == "claude"
            assert records[0]["action"] == "review"
            assert records[0]["duration_sec"] == 2.5

    def test_limit_tracker_no_budget_configured(self):
        """is_within_budget returns True if no budget set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")
            tracker = LimitTracker(storage, {})  # No claude budget

            # Record many calls
            for _ in range(100):
                tracker.record_call("claude", "plan")

            # Should still be within budget (unlimited)
            assert tracker.is_within_budget("claude") is True

    def test_limit_tracker_multiple_tools(self):
        """Track limits for multiple tools independently."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")
            tracker = LimitTracker(storage, {"claude": 5, "gemini": 10})

            # Record calls
            for _ in range(3):
                tracker.record_call("claude", "plan")
            for _ in range(8):
                tracker.record_call("gemini", "plan")

            assert tracker.today_usage("claude") == 3
            assert tracker.today_usage("gemini") == 8
            assert tracker.is_within_budget("claude") is True
            assert tracker.is_within_budget("gemini") is True

    def test_limit_tracker_separate_tools_separate_budgets(self):
        """One tool hitting budget doesn't affect another."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = AnalyticsStorage(Path(tmpdir) / "analytics.jsonl")
            tracker = LimitTracker(storage, {"claude": 2, "gemini": 10})

            # Max out claude
            for _ in range(2):
                tracker.record_call("claude", "plan")

            # gemini should still be within budget
            for _ in range(5):
                tracker.record_call("gemini", "plan")

            assert tracker.is_within_budget("claude") is False
            assert tracker.is_within_budget("gemini") is True
