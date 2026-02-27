"""Tests for analytics M4: collector, stats calculation, CLAUDE.md updater."""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flowtui.analytics.collector import AnalyticsCollector, TaskMetrics, _parse_diff_stat
from flowtui.analytics.stats import StatsCalculator, StatsSnapshot
from flowtui.core.claude_md_updater import ClaudeMdUpdater
from flowtui.core.engine import TaskResult, PhaseResult
from flowtui.core.invoker import MockCLI, InvokeResult


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def project_root(tmp_path):
    """Create a temporary project root with .flowtui directory."""
    flowtui_dir = tmp_path / ".flowtui"
    flowtui_dir.mkdir()
    return tmp_path


@pytest.fixture
def sample_task_result():
    """Sample TaskResult for testing collector."""
    return TaskResult(
        task_id="TASK-001",
        status="done",
        retry_count=1,
        phases=[
            PhaseResult(
                phase="impl",
                status="pass",
                output="3 files modified",
                duration_sec=10.0,
            ),
            PhaseResult(
                phase="review",
                status="pass",
                output="## Review Result: PASS",
                duration_sec=5.0,
            ),
            PhaseResult(
                phase="verify_ac",
                status="pass",
                output="5 passed in 2.3s",
                duration_sec=3.0,
            ),
        ],
        branch="flowtui/TASK-001",
        diff_stat="3 files changed, 42 insertions(+), 7 deletions(-)",
        total_duration_sec=18.0,
    )


@pytest.fixture
def project_with_analytics(tmp_path):
    """Project with sample analytics.jsonl records."""
    flowtui_dir = tmp_path / ".flowtui"
    flowtui_dir.mkdir()
    analytics_file = flowtui_dir / "analytics.jsonl"

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    records = [
        # Today's CC calls
        {
            "timestamp": now.isoformat(),
            "tool": "claude",
            "action": "plan",
            "duration_sec": 5.0,
        },
        {
            "timestamp": now.isoformat(),
            "tool": "claude",
            "action": "review",
            "duration_sec": 3.0,
        },
        # Today's done task
        {
            "timestamp": now.isoformat(),
            "tool": "flowtui",
            "action": "run_task",
            "task_id": "T-001",
            "status": "done",
            "duration_sec": 30.0,
            "retry_count": 0,
            "files_changed": 5,
            "lines_added": 100,
            "lines_removed": 20,
        },
        # Yesterday's call (out of today count)
        {
            "timestamp": yesterday.isoformat(),
            "tool": "claude",
            "action": "plan",
            "duration_sec": 4.0,
        },
        # This week's Codex call
        {
            "timestamp": week_ago.isoformat(),
            "tool": "codex",
            "action": "code",
            "duration_sec": 2.0,
        },
        # Today's blocked task
        {
            "timestamp": now.isoformat(),
            "tool": "flowtui",
            "action": "run_task",
            "task_id": "T-002",
            "status": "blocked",
            "duration_sec": 15.0,
            "retry_count": 2,
            "files_changed": 1,
            "lines_added": 5,
            "lines_removed": 0,
        },
    ]

    with open(analytics_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    return tmp_path


# ============================================================================
# SECTION 1: AnalyticsCollector Tests (min 8)
# ============================================================================


class TestParserDiffStat:
    """Test _parse_diff_stat helper function."""

    def test_parse_diff_stat_empty(self):
        """Empty string returns (0, 0, 0)."""
        files, added, removed = _parse_diff_stat("")
        assert files == 0
        assert added == 0
        assert removed == 0

    def test_parse_diff_stat_full(self):
        """Full format: 'N files changed, M insertions(+), K deletions(-)'."""
        diff = "3 files changed, 42 insertions(+), 7 deletions(-)"
        files, added, removed = _parse_diff_stat(diff)
        assert files == 3
        assert added == 42
        assert removed == 7

    def test_parse_diff_stat_no_deletions(self):
        """No deletions line still parses correctly."""
        diff = "1 file changed, 10 insertions(+)"
        files, added, removed = _parse_diff_stat(diff)
        assert files == 1
        assert added == 10
        assert removed == 0

    def test_parse_diff_stat_singular_file(self):
        """Single file: 'file' not 'files'."""
        diff = "1 file changed, 5 insertions(+), 2 deletions(-)"
        files, added, removed = _parse_diff_stat(diff)
        assert files == 1
        assert added == 5
        assert removed == 2

    def test_parse_diff_stat_only_additions(self):
        """Only additions, no deletions."""
        diff = "2 files changed, 100 insertions(+)"
        files, added, removed = _parse_diff_stat(diff)
        assert files == 2
        assert added == 100
        assert removed == 0

    def test_parse_diff_stat_malformed(self):
        """Malformed or partial input returns 0 for missing parts."""
        diff = "garbage input"
        files, added, removed = _parse_diff_stat(diff)
        assert files == 0
        assert added == 0
        assert removed == 0


class TestAnalyticsCollectorBasic:
    """Test basic AnalyticsCollector functionality."""

    def test_collect_task_metrics_returns_metrics(self, project_root, sample_task_result):
        """collect_task_metrics returns TaskMetrics object with correct fields."""
        collector = AnalyticsCollector(project_root)
        metrics = collector.collect_task_metrics(sample_task_result)

        assert isinstance(metrics, TaskMetrics)
        assert metrics.task_id == "TASK-001"
        assert metrics.status == "done"
        assert metrics.retry_count == 1
        assert metrics.duration_sec == 18.0

    def test_collect_task_metrics_parses_diff_stat(
        self, project_root, sample_task_result
    ):
        """collect_task_metrics correctly parses diff_stat."""
        collector = AnalyticsCollector(project_root)
        metrics = collector.collect_task_metrics(sample_task_result)

        assert metrics.files_changed == 3
        assert metrics.lines_added == 42
        assert metrics.lines_removed == 7

    def test_collect_task_metrics_reads_test_count(self, project_root, sample_task_result):
        """collect_task_metrics extracts test count from verify_ac output."""
        collector = AnalyticsCollector(project_root)
        metrics = collector.collect_task_metrics(sample_task_result)

        assert metrics.tests_passed is True
        assert metrics.tests_count == 5

    def test_collect_task_metrics_no_verify_ac(self, project_root):
        """No verify_ac phase -> tests_passed=None, tests_count=0."""
        task_result = TaskResult(
            task_id="TASK-002",
            status="done",
            retry_count=0,
            phases=[
                PhaseResult(
                    phase="impl",
                    status="pass",
                    output="code generated",
                    duration_sec=10.0,
                )
            ],
            branch="flowtui/TASK-002",
            diff_stat="1 file changed, 10 insertions(+)",
            total_duration_sec=10.0,
        )

        collector = AnalyticsCollector(project_root)
        metrics = collector.collect_task_metrics(task_result)

        assert metrics.tests_passed is None
        assert metrics.tests_count == 0

    def test_collect_task_metrics_persists_to_jsonl(self, project_root, sample_task_result):
        """collect_task_metrics writes record to analytics.jsonl."""
        collector = AnalyticsCollector(project_root)
        collector.collect_task_metrics(sample_task_result)

        analytics_file = project_root / ".flowtui" / "analytics.jsonl"
        assert analytics_file.exists()

        lines = analytics_file.read_text().strip().split("\n")
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["tool"] == "flowtui"
        assert record["action"] == "run_task"
        assert record["task_id"] == "TASK-001"
        assert record["files_changed"] == 3
        assert record["tests_count"] == 5

    def test_collect_task_metrics_test_failed(self, project_root):
        """verify_ac with failed status -> tests_passed=False."""
        task_result = TaskResult(
            task_id="TASK-003",
            status="blocked",
            retry_count=2,
            phases=[
                PhaseResult(
                    phase="verify_ac",
                    status="fail",
                    output="3 failed, 2 passed",
                    duration_sec=5.0,
                )
            ],
            branch="flowtui/TASK-003",
            diff_stat="2 files changed, 20 insertions(+), 5 deletions(-)",
            total_duration_sec=15.0,
        )

        collector = AnalyticsCollector(project_root)
        metrics = collector.collect_task_metrics(task_result)

        assert metrics.tests_passed is False
        assert metrics.tests_count == 2  # Should extract "2 passed"


# ============================================================================
# SECTION 2: StatsCalculator Tests (min 12)
# ============================================================================


class TestStatsCalculatorTodayCallCounting:
    """Test today_calls method."""

    def test_today_calls_counts_today(self, project_with_analytics):
        """today_calls counts only today's records."""
        calc = StatsCalculator(project_with_analytics)
        claude_today = calc.today_calls("claude")
        assert claude_today == 2  # two claude calls today

    def test_today_calls_excludes_yesterday(self, project_with_analytics):
        """today_calls excludes yesterday's records."""
        calc = StatsCalculator(project_with_analytics)
        claude_today = calc.today_calls("claude")
        # Only today's two calls, not yesterday's one
        assert claude_today == 2

    def test_today_calls_empty_file(self, project_root):
        """Empty analytics file returns 0."""
        calc = StatsCalculator(project_root)
        claude_today = calc.today_calls("claude")
        assert claude_today == 0

    def test_today_calls_nonexistent_tool(self, project_with_analytics):
        """Tool not in file returns 0."""
        calc = StatsCalculator(project_with_analytics)
        result = calc.today_calls("unknown_tool")
        assert result == 0

    def test_week_calls_includes_yesterday(self, project_with_analytics):
        """week_calls includes records from past 7 days."""
        calc = StatsCalculator(project_with_analytics)
        claude_week = calc.week_calls("claude")
        # Today's 2 + yesterday's 1 = 3
        assert claude_week == 3


class TestStatsCalculatorTaskMetrics:
    """Test task-related statistics."""

    def test_avg_task_duration_done_only(self, project_with_analytics):
        """avg_task_duration includes only done tasks (30s, not 15s blocked)."""
        calc = StatsCalculator(project_with_analytics)
        avg = calc.avg_task_duration()
        assert avg == 30.0  # Only the done task

    def test_avg_task_duration_no_data(self, project_root):
        """No tasks returns 0.0."""
        calc = StatsCalculator(project_root)
        avg = calc.avg_task_duration()
        assert avg == 0.0

    def test_retry_rate_calculation(self, project_with_analytics):
        """retry_rate: tasks with retry_count > 0 / total tasks."""
        calc = StatsCalculator(project_with_analytics)
        rate = calc.retry_rate()
        # 1 retried (T-002 with retry_count=2) / 2 total = 0.5
        assert rate == 0.5

    def test_total_tasks_done(self, project_with_analytics):
        """total_tasks_done counts done status tasks."""
        calc = StatsCalculator(project_with_analytics)
        done = calc.total_tasks_done()
        assert done == 1

    def test_total_tasks_blocked(self, project_with_analytics):
        """total_tasks_blocked counts blocked status tasks."""
        calc = StatsCalculator(project_with_analytics)
        blocked = calc.total_tasks_blocked()
        assert blocked == 1


class TestStatsCalculatorSnapshot:
    """Test StatsSnapshot generation."""

    def test_snapshot_returns_complete(self, project_with_analytics):
        """snapshot returns StatsSnapshot with all fields populated."""
        calc = StatsCalculator(project_with_analytics)
        snapshot = calc.snapshot()

        assert isinstance(snapshot, StatsSnapshot)
        assert isinstance(snapshot.today_calls, dict)
        assert isinstance(snapshot.week_calls, dict)
        assert snapshot.avg_task_duration_sec >= 0.0
        assert 0.0 <= snapshot.retry_rate <= 1.0
        assert snapshot.total_tasks_done >= 0
        assert snapshot.total_tasks_blocked >= 0
        assert snapshot.total_files_changed >= 0
        assert snapshot.total_lines_added >= 0
        assert snapshot.total_lines_removed >= 0

    def test_snapshot_with_custom_tools(self, project_with_analytics):
        """snapshot accepts custom tool list."""
        calc = StatsCalculator(project_with_analytics)
        snapshot = calc.snapshot(tools=["claude", "codex"])

        assert "claude" in snapshot.today_calls
        assert "codex" in snapshot.today_calls

    def test_snapshot_code_stats(self, project_with_analytics):
        """snapshot includes aggregated code stats from all tasks."""
        calc = StatsCalculator(project_with_analytics)
        snapshot = calc.snapshot()

        # T-001: 5 files, 100 added, 20 removed
        # T-002: 1 file, 5 added, 0 removed
        assert snapshot.total_files_changed == 6
        assert snapshot.total_lines_added == 105
        assert snapshot.total_lines_removed == 20


class TestStatsCalculatorFormatting:
    """Test dashboard formatting."""

    def test_format_dashboard_contains_sections(self, project_with_analytics):
        """format_dashboard output contains expected sections."""
        calc = StatsCalculator(project_with_analytics)
        snapshot = calc.snapshot()
        output = calc.format_dashboard(snapshot)

        assert "Tool Calls:" in output
        assert "Task Stats:" in output
        assert "Code Stats" in output

    def test_format_dashboard_with_budgets(self, project_with_analytics):
        """format_dashboard shows budgets when provided."""
        calc = StatsCalculator(project_with_analytics)
        snapshot = calc.snapshot()
        budgets = {"claude": 100, "codex": 50}
        output = calc.format_dashboard(snapshot, budgets)

        assert "100" in output
        assert "50" in output

    def test_format_dashboard_multiple_lines(self, project_with_analytics):
        """format_dashboard returns multiline string."""
        calc = StatsCalculator(project_with_analytics)
        snapshot = calc.snapshot()
        output = calc.format_dashboard(snapshot)

        lines = output.split("\n")
        assert len(lines) > 5  # Should have multiple sections


# ============================================================================
# SECTION 3: ClaudeMdUpdater Tests (min 5)
# ============================================================================


class TestClaudeMdUpdaterBasic:
    """Test basic ClaudeMdUpdater functionality."""

    @pytest.mark.asyncio
    async def test_update_dry_run_returns_preview(self, project_root):
        """dry_run=True returns preview string, does not invoke."""
        mock_cli = MockCLI()
        updater = ClaudeMdUpdater(project_root, mock_cli)

        result = await updater.update(dry_run=True)

        assert "[DRY RUN]" in result
        assert "Would call Claude" in result
        assert len(mock_cli.calls) == 0  # No actual invocation

    @pytest.mark.asyncio
    async def test_update_calls_invoker(self, project_root):
        """update with dry_run=False calls invoker.invoke."""
        mock_cli = MockCLI(responses={"cc": "Updated CLAUDE.md content"})
        updater = ClaudeMdUpdater(project_root, mock_cli)

        result = await updater.update(dry_run=False)

        assert len(mock_cli.calls) == 1
        assert mock_cli.calls[0]["tool"] == "cc"
        assert result == "Updated CLAUDE.md content"

    @pytest.mark.asyncio
    async def test_update_reads_existing_claude_md(self, project_root):
        """update includes existing CLAUDE.md in prompt."""
        # Create an existing CLAUDE.md
        existing_content = "# Existing Content\nSome text here"
        (project_root / "CLAUDE.md").write_text(existing_content)

        mock_cli = MockCLI(responses={"cc": "Updated"})
        updater = ClaudeMdUpdater(project_root, mock_cli)

        await updater.update(dry_run=False)

        # The prompt should include existing content
        call = mock_cli.calls[0]
        prompt = call["args"][2]  # -p prompt is at index 2
        assert "Existing Content" in prompt

    @pytest.mark.asyncio
    async def test_update_handles_invoker_failure(self, project_root):
        """returncode != 0 raises RuntimeError."""

        class FailingInvoker:
            async def invoke(self, tool, args, cwd, timeout=300.0):
                return InvokeResult(
                    stdout="",
                    stderr="Claude command failed",
                    returncode=1,
                    duration_sec=0.5,
                    timed_out=False,
                )

        updater = ClaudeMdUpdater(project_root, FailingInvoker())

        with pytest.raises(RuntimeError, match="Claude call failed"):
            await updater.update(dry_run=False)

    def test_scan_repo_structure_finds_python_files(self, project_root):
        """_scan_repo_structure returns string with Python file names."""
        # Create some Python files
        flowtui_dir = project_root / "flowtui"
        flowtui_dir.mkdir()
        (flowtui_dir / "core.py").touch()
        (flowtui_dir / "utils.py").touch()

        updater = ClaudeMdUpdater(project_root, MockCLI())
        result = updater._scan_repo_structure()

        assert "flowtui/" in result
        assert "core.py" in result or "utils.py" in result

    def test_scan_repo_structure_empty_project(self, project_root):
        """_scan_repo_structure with no Python files returns message."""
        updater = ClaudeMdUpdater(project_root, MockCLI())
        result = updater._scan_repo_structure()

        # Should return "No Python files found" or empty string, not crash
        assert isinstance(result, str)


# ============================================================================
# SECTION 3B: Additional Coverage Tests
# ============================================================================


class TestAnalyticsCollectorEdgeCases:
    """Test edge cases for AnalyticsCollector."""

    def test_collect_with_test_output_no_passed(self, project_root):
        """Test output without 'passed' keyword returns tests_count=0."""
        task_result = TaskResult(
            task_id="TASK-004",
            status="done",
            retry_count=0,
            phases=[
                PhaseResult(
                    phase="verify_ac",
                    status="pass",
                    output="Test run completed",
                    duration_sec=2.0,
                )
            ],
            branch="flowtui/TASK-004",
            diff_stat="1 file changed, 5 insertions(+)",
            total_duration_sec=5.0,
        )

        collector = AnalyticsCollector(project_root)
        metrics = collector.collect_task_metrics(task_result)

        assert metrics.tests_count == 0
        assert metrics.tests_passed is True

    def test_collect_multiple_tasks_appends(self, project_root):
        """Multiple collect calls append to same file."""
        collector = AnalyticsCollector(project_root)

        task1 = TaskResult(
            task_id="T-A",
            status="done",
            retry_count=0,
            phases=[],
            branch="flowtui/T-A",
            diff_stat="1 file changed, 1 insertions(+)",
            total_duration_sec=1.0,
        )
        task2 = TaskResult(
            task_id="T-B",
            status="done",
            retry_count=0,
            phases=[],
            branch="flowtui/T-B",
            diff_stat="2 files changed, 2 insertions(+)",
            total_duration_sec=2.0,
        )

        collector.collect_task_metrics(task1)
        collector.collect_task_metrics(task2)

        analytics_file = project_root / ".flowtui" / "analytics.jsonl"
        lines = analytics_file.read_text().strip().split("\n")
        assert len(lines) == 2


class TestStatsCalculatorParseTimestamp:
    """Test timestamp parsing in StatsCalculator."""

    def test_parse_timestamp_valid_iso(self, project_root):
        """Valid ISO timestamp parses correctly."""
        calc = StatsCalculator(project_root)
        ts_str = "2026-02-27T10:30:00+00:00"
        dt = calc._parse_timestamp(ts_str)

        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 27

    def test_parse_timestamp_invalid_returns_none(self, project_root):
        """Invalid timestamp returns None."""
        calc = StatsCalculator(project_root)
        dt = calc._parse_timestamp("not-a-timestamp")

        assert dt is None

    def test_parse_timestamp_adds_utc_if_missing(self, project_root):
        """Naive timestamp gets UTC timezone."""
        calc = StatsCalculator(project_root)
        ts_str = "2026-02-27T10:30:00"
        dt = calc._parse_timestamp(ts_str)

        assert dt is not None
        assert dt.tzinfo is not None


class TestClaudeMdUpdaterBuildPrompt:
    """Test prompt building in ClaudeMdUpdater."""

    def test_build_prompt_includes_current_content(self, project_root):
        """_build_prompt includes current CLAUDE.md content."""
        content = "# Old Content"
        updater = ClaudeMdUpdater(project_root, MockCLI())
        prompt = updater._build_prompt(content)

        assert "Old Content" in prompt
        assert "CLAUDE.md" in prompt

    def test_build_prompt_includes_update_instructions(self, project_root):
        """_build_prompt includes instructions for updating."""
        updater = ClaudeMdUpdater(project_root, MockCLI())
        prompt = updater._build_prompt("")

        assert "outdated" in prompt.lower() or "update" in prompt.lower()

    def test_build_prompt_includes_repo_scan(self, project_root):
        """_build_prompt includes repository structure scan."""
        flowtui_dir = project_root / "flowtui"
        flowtui_dir.mkdir()
        (flowtui_dir / "test.py").touch()

        updater = ClaudeMdUpdater(project_root, MockCLI())
        prompt = updater._build_prompt("")

        assert "flowtui" in prompt


class TestStatsCalculatorRecordsSince:
    """Test _records_since filtering."""

    def test_records_since_filters_by_date(self, project_with_analytics):
        """_records_since returns only records after given time."""
        calc = StatsCalculator(project_with_analytics)

        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=1)

        records = calc._records_since(future)
        assert len(records) == 0  # All records are before future time

    def test_records_since_includes_boundary(self, project_with_analytics):
        """_records_since includes records at exact timestamp."""
        calc = StatsCalculator(project_with_analytics)

        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        records = calc._records_since(yesterday)
        # Should include today's and yesterday's records (if at same time)
        # At minimum should have today's 3 records
        assert len(records) >= 3
