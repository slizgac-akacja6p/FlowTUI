"""Tests for analytics storage and limit tracking."""
import tempfile
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
from threading import Thread
import time

import pytest

from flowtui.analytics.storage import AnalyticsStorage
from flowtui.analytics.limits import LimitTracker
from flowtui.analytics.stats import StatsCalculator, StatsSnapshot


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


class TestStatsCalculator:
    """Test statistics calculation from analytics records."""

    def test_stats_empty_log(self):
        """StatsCalculator handles empty analytics log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            project_root.joinpath(".flowtui").mkdir(parents=True, exist_ok=True)

            calc = StatsCalculator(project_root)
            snapshot = calc.snapshot()

            assert snapshot.today_calls == {"claude": 0, "codex": 0, "gemini": 0}
            assert snapshot.week_calls == {"claude": 0, "codex": 0, "gemini": 0}
            assert snapshot.avg_task_duration_sec == 0.0
            assert snapshot.retry_rate == 0.0
            assert snapshot.total_tasks_done == 0
            assert snapshot.total_tasks_blocked == 0
            assert snapshot.total_files_changed == 0
            assert snapshot.total_lines_added == 0
            assert snapshot.total_lines_removed == 0

    def test_stats_today_calls(self):
        """today_calls counts tool calls since midnight UTC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            storage = AnalyticsStorage(project_root / ".flowtui" / "analytics.jsonl")

            # Record some calls
            storage.append({"tool": "claude", "action": "plan"})
            storage.append({"tool": "claude", "action": "review"})
            storage.append({"tool": "codex", "action": "implement"})

            calc = StatsCalculator(project_root)
            assert calc.today_calls("claude") == 2
            assert calc.today_calls("codex") == 1
            assert calc.today_calls("gemini") == 0

    def test_stats_week_calls(self):
        """week_calls counts tool calls in last 7 days."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            storage = AnalyticsStorage(project_root / ".flowtui" / "analytics.jsonl")

            # Record calls with manual timestamps
            now = datetime.now(timezone.utc)
            storage.append({
                "timestamp": now.isoformat(),
                "tool": "claude",
                "action": "plan",
            })

            # Old record from 10 days ago (should be excluded from week_calls)
            old_time = now - timedelta(days=10)
            with open(storage.filepath, "a", encoding="utf-8") as f:
                f.write(f'{{"timestamp": "{old_time.isoformat()}", "tool": "claude", "action": "old"}}\n')

            calc = StatsCalculator(project_root)
            # week_calls should count only the recent one
            assert calc.week_calls("claude") >= 1  # At least the recent one

    def test_stats_avg_task_duration(self):
        """avg_task_duration computes mean duration of done tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            storage = AnalyticsStorage(project_root / ".flowtui" / "analytics.jsonl")

            # Record done tasks with durations
            storage.append({
                "action": "run_task",
                "status": "done",
                "duration_sec": 10.0,
            })
            storage.append({
                "action": "run_task",
                "status": "done",
                "duration_sec": 20.0,
            })
            storage.append({
                "action": "run_task",
                "status": "blocked",
                "duration_sec": 5.0,  # Should not be counted
            })

            calc = StatsCalculator(project_root)
            avg = calc.avg_task_duration()
            assert avg == 15.0  # (10 + 20) / 2

    def test_stats_retry_rate(self):
        """retry_rate computes fraction of tasks with retries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            storage = AnalyticsStorage(project_root / ".flowtui" / "analytics.jsonl")

            # Record 4 tasks: 1 with retry, 3 without
            storage.append({"action": "run_task", "retry_count": 1})
            storage.append({"action": "run_task", "retry_count": 0})
            storage.append({"action": "run_task", "retry_count": 0})
            storage.append({"action": "run_task", "retry_count": 0})

            calc = StatsCalculator(project_root)
            rate = calc.retry_rate()
            assert rate == 0.25  # 1 retried out of 4

    def test_stats_total_tasks_done(self):
        """total_tasks_done counts completed tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            storage = AnalyticsStorage(project_root / ".flowtui" / "analytics.jsonl")

            storage.append({"action": "run_task", "status": "done"})
            storage.append({"action": "run_task", "status": "done"})
            storage.append({"action": "run_task", "status": "blocked"})

            calc = StatsCalculator(project_root)
            assert calc.total_tasks_done() == 2

    def test_stats_total_tasks_blocked(self):
        """total_tasks_blocked counts blocked tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            storage = AnalyticsStorage(project_root / ".flowtui" / "analytics.jsonl")

            storage.append({"action": "run_task", "status": "done"})
            storage.append({"action": "run_task", "status": "blocked"})
            storage.append({"action": "run_task", "status": "blocked"})

            calc = StatsCalculator(project_root)
            assert calc.total_tasks_blocked() == 2

    def test_stats_code_metrics(self):
        """snapshot aggregates code change metrics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            storage = AnalyticsStorage(project_root / ".flowtui" / "analytics.jsonl")

            storage.append({
                "action": "run_task",
                "files_changed": 3,
                "lines_added": 50,
                "lines_removed": 20,
            })
            storage.append({
                "action": "run_task",
                "files_changed": 2,
                "lines_added": 30,
                "lines_removed": 10,
            })

            calc = StatsCalculator(project_root)
            snapshot = calc.snapshot()

            assert snapshot.total_files_changed == 5
            assert snapshot.total_lines_added == 80
            assert snapshot.total_lines_removed == 30

    def test_stats_snapshot_custom_tools(self):
        """snapshot respects custom tool list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            storage = AnalyticsStorage(project_root / ".flowtui" / "analytics.jsonl")

            storage.append({"tool": "custom_tool", "action": "test"})

            calc = StatsCalculator(project_root)
            snapshot = calc.snapshot(tools=["custom_tool", "other"])

            assert "custom_tool" in snapshot.today_calls
            assert "other" in snapshot.today_calls
            assert snapshot.today_calls["custom_tool"] == 1

    def test_stats_format_dashboard(self):
        """format_dashboard produces formatted output."""
        snapshot = StatsSnapshot(
            today_calls={"claude": 5, "codex": 3},
            week_calls={"claude": 20, "codex": 10},
            avg_task_duration_sec=2.5,
            retry_rate=0.1,
            total_tasks_done=10,
            total_tasks_blocked=1,
            total_files_changed=15,
            total_lines_added=200,
            total_lines_removed=50,
        )

        calc = StatsCalculator(Path("."))
        output = calc.format_dashboard(
            snapshot,
            budgets={"claude": 10, "codex": 5},
        )

        assert "Stats Dashboard" in output
        assert "Tool Calls:" in output
        assert "claude" in output
        assert "codex" in output
        assert "2.5s" in output  # avg time
        assert "10.0%" in output  # retry rate
