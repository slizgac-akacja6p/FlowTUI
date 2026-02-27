"""Statistics calculation from analytics.jsonl log."""
from __future__ import annotations

import csv
import json as json_module
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .storage import AnalyticsStorage


@dataclass
class StatsSnapshot:
    """Current stats snapshot for display in TUI dashboard."""

    # Tool call counts
    today_calls: dict[str, int]  # {"claude": N, "codex": M, ...}
    week_calls: dict[str, int]   # {"claude": N, "codex": M, ...}

    # Task stats
    avg_task_duration_sec: float       # 0.0 if no data
    retry_rate: float                  # 0.0 - 1.0 (retries/total)
    total_tasks_done: int
    total_tasks_blocked: int

    # Code stats
    total_files_changed: int
    total_lines_added: int
    total_lines_removed: int


class StatsCalculator:
    """Calculate statistics from analytics.jsonl records."""

    def __init__(self, project_root: Path) -> None:
        """Initialize calculator with project root directory.

        Args:
            project_root: Path to project root (contains .flowtui/analytics.jsonl)
        """
        self.project_root = Path(project_root)
        self.storage = AnalyticsStorage(
            self.project_root / ".flowtui" / "analytics.jsonl"
        )

    def _parse_timestamp(self, ts_str: str) -> datetime | None:
        """Parse ISO timestamp string to datetime with UTC timezone."""
        try:
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None

    def _records_since(self, since: datetime) -> list[dict]:
        """Get all records since a given datetime."""
        all_records = self.storage.read_all()
        result = []
        for record in all_records:
            ts_str = record.get("timestamp")
            ts = self._parse_timestamp(ts_str)
            if ts and ts >= since:
                result.append(record)
        return result

    def today_calls(self, tool: str) -> int:
        """Count calls for tool today (UTC date)."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        records = self._records_since(today_start)
        return sum(1 for r in records if r.get("tool") == tool)

    def week_calls(self, tool: str) -> int:
        """Count calls for tool in last 7 days."""
        week_start = datetime.now(timezone.utc) - timedelta(days=7)
        records = self._records_since(week_start)
        return sum(1 for r in records if r.get("tool") == tool)

    def avg_task_duration(self) -> float:
        """Average duration of completed tasks in seconds. 0.0 if no data."""
        all_records = self.storage.read_all()
        task_records = [
            r
            for r in all_records
            if r.get("action") == "run_task" and r.get("status") == "done"
        ]
        if not task_records:
            return 0.0
        durations = [r.get("duration_sec", 0.0) for r in task_records]
        total = sum(durations)
        return total / len(durations) if durations else 0.0

    def retry_rate(self) -> float:
        """Ratio of retried tasks to total tasks. 0.0 if no data."""
        all_records = self.storage.read_all()
        task_records = [r for r in all_records if r.get("action") == "run_task"]
        if not task_records:
            return 0.0
        retried = sum(1 for r in task_records if r.get("retry_count", 0) > 0)
        return retried / len(task_records)

    def total_tasks_done(self) -> int:
        """Total number of completed tasks ever."""
        all_records = self.storage.read_all()
        return sum(
            1
            for r in all_records
            if r.get("action") == "run_task" and r.get("status") == "done"
        )

    def total_tasks_blocked(self) -> int:
        """Total number of blocked tasks."""
        all_records = self.storage.read_all()
        return sum(
            1
            for r in all_records
            if r.get("action") == "run_task" and r.get("status") == "blocked"
        )

    def snapshot(self, tools: list[str] | None = None) -> StatsSnapshot:
        """Compute full StatsSnapshot for dashboard display.

        Reads analytics.jsonl once and computes all metrics from single pass.

        Args:
            tools: List of tool names to count calls for.
                   Default: ["claude", "codex", "gemini"]

        Returns:
            StatsSnapshot with all metrics populated.
        """
        if tools is None:
            tools = ["claude", "codex", "gemini"]

        # Read once
        all_records = self.storage.read_all()
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)

        # Filter records by time range
        today_records = [r for r in all_records if self._record_after(r, today_start)]
        week_records = [r for r in all_records if self._record_after(r, week_start)]
        task_records = [r for r in all_records if r.get("action") == "run_task"]

        # Compute tool call counts
        today = {t: sum(1 for r in today_records if r.get("tool") == t) for t in tools}
        week = {t: sum(1 for r in week_records if r.get("tool") == t) for t in tools}

        # Compute task metrics
        done_tasks = [r for r in task_records if r.get("status") == "done"]
        avg_dur = (sum(r.get("duration_sec", 0.0) for r in done_tasks) / len(done_tasks)) if done_tasks else 0.0
        retried = sum(1 for r in task_records if r.get("retry_count", 0) > 0)
        retry_rate = (retried / len(task_records)) if task_records else 0.0

        # Compute code metrics
        total_files = sum(r.get("files_changed", 0) for r in task_records)
        total_added = sum(r.get("lines_added", 0) for r in task_records)
        total_removed = sum(r.get("lines_removed", 0) for r in task_records)

        return StatsSnapshot(
            today_calls=today,
            week_calls=week,
            avg_task_duration_sec=avg_dur,
            retry_rate=retry_rate,
            total_tasks_done=sum(1 for r in task_records if r.get("status") == "done"),
            total_tasks_blocked=sum(1 for r in task_records if r.get("status") == "blocked"),
            total_files_changed=total_files,
            total_lines_added=total_added,
            total_lines_removed=total_removed,
        )

    def _record_after(self, record: dict, since: datetime) -> bool:
        """Check if record's timestamp is after `since`.

        Args:
            record: Analytics record dict
            since: Datetime threshold (UTC)

        Returns:
            True if record timestamp >= since, False otherwise
        """
        try:
            ts = datetime.fromisoformat(record.get("timestamp", ""))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts >= since
        except (ValueError, TypeError):
            return False

    def format_dashboard(
        self, snapshot: StatsSnapshot, budgets: dict[str, int] | None = None
    ) -> str:
        """Format StatsSnapshot as dashboard string for TUI display.

        Args:
            snapshot: StatsSnapshot instance to format
            budgets: Optional dict mapping tool names to budget limits

        Returns:
            Formatted multiline string ready for TUI widget display.
        """
        lines = ["=== FlowTUI Stats Dashboard ===", ""]

        # Tool calls
        lines.append("Tool Calls:")
        for tool in sorted(snapshot.today_calls.keys()):
            today = snapshot.today_calls.get(tool, 0)
            week = snapshot.week_calls.get(tool, 0)
            budget = budgets.get(tool, "?") if budgets else "?"
            lines.append(f"  {tool:<10} today: {today:>4}  week: {week:>4}  budget: {budget}")

        lines.append("")
        lines.append("Task Stats:")
        lines.append(f"  Done:     {snapshot.total_tasks_done}")
        lines.append(f"  Blocked:  {snapshot.total_tasks_blocked}")

        avg = snapshot.avg_task_duration_sec
        if avg > 0:
            lines.append(f"  Avg time: {avg:.1f}s")
        else:
            lines.append("  Avg time: N/A")

        retry_pct = snapshot.retry_rate * 100
        lines.append(f"  Retry rate: {retry_pct:.1f}%")

        lines.append("")
        lines.append("Code Stats (all time):")
        lines.append(f"  Files changed: {snapshot.total_files_changed}")
        lines.append(f"  Lines added:   +{snapshot.total_lines_added}")
        lines.append(f"  Lines removed: -{snapshot.total_lines_removed}")

        return "\n".join(lines)

    def _read_records(self) -> list[dict]:
        """Read all records from analytics.jsonl storage.

        Returns:
            List of analytics records (dicts).
        """
        return self.storage.read_all()

    def export_csv(self, output_path: Path | None = None) -> Path:
        """Export all analytics records to CSV.

        Args:
            output_path: Custom output path or None to auto-generate in .flowtui/exports/

        Returns:
            Path to written file.
        """
        if output_path is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            exports_dir = self.project_root / ".flowtui" / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)
            output_path = exports_dir / f"stats_{ts}.csv"

        records = self._read_records()
        if not records:
            # Write header-only CSV
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["timestamp", "tool", "action", "duration_sec"])
                writer.writeheader()
            return output_path

        # Collect all field names (union of all record keys)
        all_keys = []
        seen = set()
        for r in records:
            for k in r.keys():
                if k not in seen:
                    all_keys.append(k)
                    seen.add(k)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            for record in records:
                # Fill missing keys with empty string
                row = {k: record.get(k, "") for k in all_keys}
                writer.writerow(row)

        return output_path

    def export_json(self, output_path: Path | None = None) -> Path:
        """Export analytics records + snapshot summary to JSON.

        Args:
            output_path: Custom output path or None to auto-generate in .flowtui/exports/

        Returns:
            Path to written file.
        """
        if output_path is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            exports_dir = self.project_root / ".flowtui" / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)
            output_path = exports_dir / f"stats_{ts}.json"

        records = self._read_records()
        snap = self.snapshot()

        export_data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "today_calls": snap.today_calls,
                "week_calls": snap.week_calls,
                "avg_task_duration_sec": snap.avg_task_duration_sec,
                "retry_rate": snap.retry_rate,
                "total_tasks_done": snap.total_tasks_done,
                "total_tasks_blocked": snap.total_tasks_blocked,
                "total_files_changed": snap.total_files_changed,
                "total_lines_added": snap.total_lines_added,
                "total_lines_removed": snap.total_lines_removed,
            },
            "records": records,
        }

        tmp_path = output_path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(
                json_module.dumps(export_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.rename(output_path)
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to write export: {e}") from e
        return output_path
