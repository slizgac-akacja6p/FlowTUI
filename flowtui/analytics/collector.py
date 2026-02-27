"""Analytics collector — aggregates metrics after task execution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from flowtui.analytics.storage import AnalyticsStorage
from flowtui.core.engine import TaskResult


@dataclass
class TaskMetrics:
    """Aggregated metrics from a single task run."""

    task_id: str
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    tests_passed: bool | None = None  # None if no test framework
    tests_count: int = 0
    duration_sec: float = 0.0
    retry_count: int = 0
    status: str = ""  # "done" | "blocked"


class AnalyticsCollector:
    """Collects and persists task execution metrics."""

    def __init__(self, project_root: Path) -> None:
        """Initialize collector with storage path.

        Args:
            project_root: Project root directory containing .flowtui/
        """
        analytics_path = Path(project_root) / ".flowtui" / "analytics.jsonl"
        self.storage = AnalyticsStorage(analytics_path)

    def collect_task_metrics(self, task_result: TaskResult) -> TaskMetrics:
        """Extract metrics from TaskResult and persist to analytics.jsonl.

        Called after each run_task() to record structured metrics for later
        analysis (cost tracking, burndown charts, performance trends).

        Args:
            task_result: TaskResult object from Orchestrator.run_task()

        Returns:
            TaskMetrics dataclass with extracted values.
        """
        # Parse diff_stat string
        files_changed, lines_added, lines_removed = _parse_diff_stat(
            task_result.diff_stat
        )

        # Find verify_ac phase result for test info
        tests_passed = None
        tests_count = 0
        for phase in task_result.phases:
            if phase.phase == "verify_ac":
                tests_passed = phase.status == "pass"
                # More precise: match "N passed" but not "N passed, M failed"
                match = re.search(r"(\d+)\s+passed(?!\s*,?\s*\d+\s+failed)", phase.output)
                if match:
                    tests_count = int(match.group(1))
                break

        metrics = TaskMetrics(
            task_id=task_result.task_id,
            files_changed=files_changed,
            lines_added=lines_added,
            lines_removed=lines_removed,
            tests_passed=tests_passed,
            tests_count=tests_count,
            duration_sec=task_result.total_duration_sec,
            retry_count=task_result.retry_count,
            status=task_result.status,
        )

        # Persist to analytics.jsonl
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": "flowtui",
            "action": "run_task",
            "task_id": metrics.task_id,
            "duration_sec": metrics.duration_sec,
            "status": metrics.status,
            "retry_count": metrics.retry_count,
            "files_changed": metrics.files_changed,
            "lines_added": metrics.lines_added,
            "lines_removed": metrics.lines_removed,
            "tests_passed": metrics.tests_passed,
            "tests_count": metrics.tests_count,
        }
        self.storage.append(record)

        return metrics


def _parse_diff_stat(diff_stat_raw: str) -> tuple[int, int, int]:
    """Parse git diff --stat output summary line.

    Example: "3 files changed, 42 insertions(+), 7 deletions(-)"

    Args:
        diff_stat_raw: Raw output from git diff --stat command.

    Returns:
        Tuple of (files_changed, insertions, deletions).
    """
    if not diff_stat_raw:
        return 0, 0, 0

    files = 0
    insertions = 0
    deletions = 0

    match = re.search(r"(\d+)\s+files?\s+changed", diff_stat_raw)
    if match:
        files = int(match.group(1))

    match = re.search(r"(\d+)\s+insertions?\(\+\)", diff_stat_raw)
    if match:
        insertions = int(match.group(1))

    match = re.search(r"(\d+)\s+deletions?\(-\)", diff_stat_raw)
    if match:
        deletions = int(match.group(1))

    return files, insertions, deletions
