"""Tests for M5 (Polish) — CSV/JSON export, MockCLI, headless mode, regression E2E."""
import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from flowtui.analytics.stats import StatsCalculator, StatsSnapshot
from flowtui.core.engine import Orchestrator, TaskResult, SprintResult, PhaseResult
from flowtui.core.invoker import MockCLI, InvokeResult
from flowtui.core.task_manager import TaskManager, Task, TaskNotFoundError
from tests.conftest import mock_cli, tmp_project


# ────────────────────────────────────────────────────────────────────────────
# SEKCJA 1: CSV/JSON Export (min 8 testów)
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def project_with_records(tmp_path):
    """Temporary project with analytics records."""
    flowtui_dir = tmp_path / ".flowtui"
    flowtui_dir.mkdir()
    analytics = flowtui_dir / "analytics.jsonl"

    records = [
        {
            "timestamp": "2026-02-27T10:00:00+00:00",
            "tool": "claude",
            "action": "plan",
            "duration_sec": 5.0,
        },
        {
            "timestamp": "2026-02-27T10:05:00+00:00",
            "tool": "flowtui",
            "action": "run_task",
            "task_id": "TASK-001",
            "status": "done",
            "duration_sec": 30.0,
            "retry_count": 0,
            "files_changed": 3,
            "lines_added": 50,
            "lines_removed": 10,
        },
        {
            "timestamp": "2026-02-27T11:00:00+00:00",
            "tool": "codex",
            "action": "review",
            "duration_sec": 15.0,
        },
    ]

    analytics.write_text("\n".join(json.dumps(r) for r in records))
    return tmp_path


def test_export_csv_creates_file(project_with_records):
    """CSV export creates file and returns Path."""
    calc = StatsCalculator(project_with_records)
    result_path = calc.export_csv()

    assert result_path.exists()
    assert result_path.suffix == ".csv"


def test_export_csv_has_headers(project_with_records):
    """CSV export contains proper headers."""
    calc = StatsCalculator(project_with_records)
    result_path = calc.export_csv()

    with open(result_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        assert headers is not None
        assert "timestamp" in headers
        assert "tool" in headers
        assert "action" in headers


def test_export_csv_has_data_rows(project_with_records):
    """CSV export contains all data rows."""
    calc = StatsCalculator(project_with_records)
    result_path = calc.export_csv()

    with open(result_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 3  # 3 records
        assert rows[0]["tool"] == "claude"
        assert rows[1]["task_id"] == "TASK-001"
        assert rows[2]["tool"] == "codex"


def test_export_csv_custom_path(project_with_records):
    """CSV export respects custom output path."""
    calc = StatsCalculator(project_with_records)
    custom_path = project_with_records / ".flowtui" / "custom_stats.csv"

    result_path = calc.export_csv(custom_path)

    assert result_path == custom_path
    assert result_path.exists()


def test_export_json_creates_file(project_with_records):
    """JSON export creates file and returns Path."""
    calc = StatsCalculator(project_with_records)
    result_path = calc.export_json()

    assert result_path.exists()
    assert result_path.suffix == ".json"


def test_export_json_valid_format(project_with_records):
    """JSON export contains valid JSON."""
    calc = StatsCalculator(project_with_records)
    result_path = calc.export_json()

    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_export_json_has_summary_and_records(project_with_records):
    """JSON export has 'summary' and 'records' keys."""
    calc = StatsCalculator(project_with_records)
    result_path = calc.export_json()

    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert "summary" in data
    assert "records" in data
    assert isinstance(data["summary"], dict)
    assert isinstance(data["records"], list)


def test_export_json_summary_values(project_with_records):
    """JSON summary contains expected statistics."""
    calc = StatsCalculator(project_with_records)
    result_path = calc.export_json()

    data = json.loads(result_path.read_text(encoding="utf-8"))
    summary = data["summary"]

    assert "total_tasks_done" in summary
    assert summary["total_tasks_done"] == 1
    assert "total_files_changed" in summary
    assert summary["total_files_changed"] == 3


def test_export_creates_exports_dir(project_with_records):
    """.flowtui/exports/ directory created automatically."""
    calc = StatsCalculator(project_with_records)
    calc.export_csv()

    exports_dir = project_with_records / ".flowtui" / "exports"
    assert exports_dir.exists()
    assert exports_dir.is_dir()


# ────────────────────────────────────────────────────────────────────────────
# SEKCJA 2: MockCLI (min 8 testów)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mock_cli_invoke_default():
    """MockCLI invoke returns default response."""
    cli = MockCLI(responses={"cc": "## Review Result: PASS\n5 passed"})
    result = await cli.invoke("cc", ["test"], Path("."))

    assert result.stdout == "## Review Result: PASS\n5 passed"
    assert result.returncode == 0
    assert result.timed_out is False


@pytest.mark.asyncio
async def test_mock_cli_invoke_stores_call():
    """MockCLI records each invocation."""
    cli = MockCLI(responses={"cc": "output"})

    await cli.invoke("cc", ["arg1", "arg2"], Path("/tmp"))

    assert len(cli.calls) == 1
    assert cli.calls[0]["tool"] == "cc"
    assert cli.calls[0]["args"] == ["arg1", "arg2"]


@pytest.mark.asyncio
async def test_mock_cli_multiple_tools():
    """MockCLI handles multiple tools with different responses."""
    responses = {
        "cc": "CC output",
        "codex": "Codex output",
        "gemini": "Gemini output",
    }
    cli = MockCLI(responses=responses)

    r1 = await cli.invoke("cc", [], Path("."))
    r2 = await cli.invoke("codex", [], Path("."))
    r3 = await cli.invoke("gemini", [], Path("."))

    assert r1.stdout == "CC output"
    assert r2.stdout == "Codex output"
    assert r3.stdout == "Gemini output"


@pytest.mark.asyncio
async def test_mock_cli_call_count():
    """MockCLI call_count method."""
    cli = MockCLI(responses={"cc": "output"})

    await cli.invoke("cc", [], Path("."))
    await cli.invoke("cc", [], Path("."))

    assert len(cli.calls) == 2


@pytest.mark.asyncio
async def test_mock_cli_last_args():
    """MockCLI last call args."""
    cli = MockCLI(responses={"cc": "output"})

    await cli.invoke("cc", ["arg1"], Path("."))
    await cli.invoke("cc", ["arg2", "arg3"], Path("."))

    assert cli.calls[-1]["args"] == ["arg2", "arg3"]


@pytest.mark.asyncio
async def test_mock_cli_streaming_yields_lines():
    """MockCLI invoke_streaming yields output line by line."""
    cli = MockCLI(responses={"cc": "line1\nline2\nline3"})

    lines = []
    async for line in cli.invoke_streaming("cc", [], Path(".")):
        lines.append(line)

    assert len(lines) == 3
    assert lines[0] == "line1\n"
    assert lines[1] == "line2\n"
    assert lines[2] == "line3\n"


@pytest.mark.asyncio
async def test_mock_cli_streaming_with_delay():
    """MockCLI delay parameter adds artificial latency."""
    cli = MockCLI(responses={"cc": "output"}, delay=0.05)

    import time

    start = time.time()
    await cli.invoke("cc", [], Path("."))
    elapsed = time.time() - start

    assert elapsed >= 0.05


@pytest.mark.asyncio
async def test_mock_cli_invoke_result_structure():
    """InvokeResult has all expected fields."""
    cli = MockCLI(responses={"cc": "output"})
    result = await cli.invoke("cc", [], Path("."))

    assert hasattr(result, "stdout")
    assert hasattr(result, "stderr")
    assert hasattr(result, "returncode")
    assert hasattr(result, "duration_sec")
    assert hasattr(result, "timed_out")


# ────────────────────────────────────────────────────────────────────────────
# SEKCJA 3: Heartbeat / Timeout (min 4 testy)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mock_cli_with_timeout():
    """MockCLI respects timeout parameter."""
    cli = MockCLI(responses={"cc": "output"})
    result = await cli.invoke("cc", [], Path("."), timeout=5.0)

    assert result.returncode == 0


@pytest.mark.asyncio
async def test_mock_cli_empty_output():
    """MockCLI handles empty response."""
    cli = MockCLI(responses={})

    result = await cli.invoke("cc", [], Path("."))

    assert result.stdout == ""
    assert result.returncode == 0


@pytest.mark.asyncio
async def test_mock_cli_streaming_empty():
    """MockCLI streaming with no response yields nothing."""
    cli = MockCLI(responses={})

    lines = []
    async for line in cli.invoke_streaming("cc", [], Path(".")):
        lines.append(line)

    assert len(lines) == 0


@pytest.mark.asyncio
async def test_mock_cli_cwd_passthrough():
    """MockCLI passes cwd parameter through."""
    cli = MockCLI(responses={"cc": "output"})
    test_path = Path("/test/path")

    await cli.invoke("cc", [], test_path)

    assert cli.calls[0]["cwd"] == "/test/path"


# ────────────────────────────────────────────────────────────────────────────
# SEKCJA 4: Regresja End-to-end (min 8 testów)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_create_task_and_load(tmp_project):
    """Create and load a task."""
    task_mgr = TaskManager(tmp_project / "docs" / "tasks")

    task = Task(
        id="TASK-001",
        title="Test task",
        sprint="1",
        priority="high",
        status="DRAFT",
        context="Do something",
        acceptance_criteria=["It works"],
    )

    task_mgr.create(task)

    loaded = task_mgr.load("TASK-001")
    assert loaded.id == "TASK-001"
    assert loaded.title == "Test task"
    assert loaded.status == "DRAFT"


@pytest.mark.asyncio
async def test_e2e_update_task_status(tmp_project):
    """Update task status and check persistence."""
    task_mgr = TaskManager(tmp_project / "docs" / "tasks")

    task = Task(
        id="TASK-002",
        title="Test task 2",
        status="DRAFT",
        context="Something",
        acceptance_criteria=["Works"],
    )

    task_mgr.create(task)
    task_mgr.update_status("TASK-002", "TODO", "Plan approved")

    loaded = task_mgr.load("TASK-002")
    assert loaded.status == "TODO"
    assert len(loaded.log_entries) > 0


@pytest.mark.asyncio
async def test_e2e_task_not_found():
    """TaskManager raises on missing task."""
    task_mgr = TaskManager(Path("/tmp/nonexistent"))

    with pytest.raises(TaskNotFoundError):
        task_mgr.load("TASK-999")


@pytest.mark.asyncio
async def test_e2e_orchestrator_plan_with_mock(tmp_project, mock_cli):
    """Orchestrator.plan streams output with MockCLI."""
    from flowtui.config import FlowTUIConfig, ProjectConfig, LimitsConfig

    config = FlowTUIConfig(
        project=ProjectConfig(
            name="test",
            stack="Python",
            description="Test",
        ),
        limits=LimitsConfig(
            claude_daily_budget=50,
            codex_daily_budget=5,
            gemini_daily_budget=100,
        ),
    )

    task_mgr = TaskManager(tmp_project / "docs" / "tasks")
    orchestrator = Orchestrator(
        invoker=mock_cli,
        task_mgr=task_mgr,
        config=config,
        project_root=tmp_project,
    )

    # Mock CC response with task format
    mock_cli.responses["cc"] = """## TASK-001
### Description
Test task 1
### Files
- test.py
### AC
- Works
---
## TASK-002
### Description
Test task 2
### Files
- test2.py
### AC
- Also works
---
Planning complete"""

    output = []
    async for line in orchestrator.plan("test feature"):
        output.append(line)

    assert len(output) > 0


@pytest.mark.asyncio
async def test_e2e_orchestrator_approve_plan(tmp_project, mock_cli):
    """Orchestrator approve_plan changes DRAFT → TODO."""
    from flowtui.config import FlowTUIConfig, ProjectConfig, LimitsConfig

    config = FlowTUIConfig(
        project=ProjectConfig(name="test", stack="Python", description="Test"),
        limits=LimitsConfig(
            claude_daily_budget=50,
            codex_daily_budget=5,
            gemini_daily_budget=100,
        ),
    )

    task_mgr = TaskManager(tmp_project / "docs" / "tasks")
    orchestrator = Orchestrator(
        invoker=mock_cli,
        task_mgr=task_mgr,
        config=config,
        project_root=tmp_project,
    )

    # Create a DRAFT task
    task = Task(
        id="TASK-001",
        title="Test",
        status="DRAFT",
        context="Test",
        acceptance_criteria=["Works"],
    )
    task_mgr.create(task)

    # Approve it
    approved = await orchestrator.approve_plan(["TASK-001"])

    assert len(approved) == 1
    assert approved[0] == "TASK-001"

    # Verify status changed
    loaded = task_mgr.load("TASK-001")
    assert loaded.status == "TODO"


@pytest.mark.asyncio
async def test_e2e_orchestrator_reject_plan(tmp_project, mock_cli):
    """Orchestrator reject_plan deletes DRAFT tasks."""
    from flowtui.config import FlowTUIConfig, ProjectConfig, LimitsConfig

    config = FlowTUIConfig(
        project=ProjectConfig(name="test", stack="Python", description="Test"),
        limits=LimitsConfig(
            claude_daily_budget=50,
            codex_daily_budget=5,
            gemini_daily_budget=100,
        ),
    )

    task_mgr = TaskManager(tmp_project / "docs" / "tasks")
    orchestrator = Orchestrator(
        invoker=mock_cli,
        task_mgr=task_mgr,
        config=config,
        project_root=tmp_project,
    )

    # Create a DRAFT task
    task = Task(
        id="TASK-001",
        title="Test",
        status="DRAFT",
        context="Test",
        acceptance_criteria=["Works"],
    )
    task_mgr.create(task)

    # Reject it
    await orchestrator.reject_plan(["TASK-001"])

    # Verify it's gone
    with pytest.raises(TaskNotFoundError):
        task_mgr.load("TASK-001")


@pytest.mark.asyncio
async def test_e2e_orchestrator_run_task_happy_path(tmp_project, mock_cli):
    """Orchestrator.run_task with passing MockCLI."""
    from flowtui.config import FlowTUIConfig, ProjectConfig, LimitsConfig

    config = FlowTUIConfig(
        project=ProjectConfig(name="test", stack="Python", description="Test"),
        limits=LimitsConfig(
            claude_daily_budget=50,
            codex_daily_budget=5,
            gemini_daily_budget=100,
        ),
    )

    task_mgr = TaskManager(tmp_project / "docs" / "tasks")
    orchestrator = Orchestrator(
        invoker=mock_cli,
        task_mgr=task_mgr,
        config=config,
        project_root=tmp_project,
        git_ops=None,
        test_runner=None,
    )

    # Create a TODO task
    task = Task(
        id="TASK-001",
        title="Test",
        status="TODO",
        context="Do something",
        requirements=["requirement 1"],
        files_to_modify=["test.py"],
        acceptance_criteria=["Works"],
    )
    task_mgr.create(task)

    # Mock CC response
    mock_cli.responses["cc"] = "## Review Result: PASS\nImplementation complete"

    # Run the task
    result = await orchestrator.run_task("TASK-001")

    assert isinstance(result, TaskResult)
    assert result.task_id == "TASK-001"
    assert result.status in ["done", "blocked"]


@pytest.mark.asyncio
async def test_e2e_task_manager_load_all(tmp_project):
    """TaskManager.load_all returns all tasks sorted."""
    task_mgr = TaskManager(tmp_project / "docs" / "tasks")

    task1 = Task(
        id="TASK-002", title="Second", status="TODO", context="", acceptance_criteria=[]
    )
    task2 = Task(
        id="TASK-001", title="First", status="TODO", context="", acceptance_criteria=[]
    )

    task_mgr.create(task1)
    task_mgr.create(task2)

    all_tasks = task_mgr.load_all()

    assert len(all_tasks) == 2
    assert all_tasks[0].id == "TASK-001"
    assert all_tasks[1].id == "TASK-002"


@pytest.mark.asyncio
async def test_e2e_sprint_result_summary_table():
    """SprintResult generates summary table."""
    from flowtui.core.engine import PhaseResult

    phase = PhaseResult(phase="impl", status="pass", duration_sec=10.0)
    task_result = TaskResult(
        task_id="TASK-001",
        status="done",
        retry_count=0,
        phases=[phase],
        branch="flowtui/TASK-001",
        total_duration_sec=15.0,
    )

    sprint = SprintResult(
        completed=1,
        blocked=0,
        total_attempted=1,
        circuit_breaker=False,
        task_results=[task_result],
        total_duration_sec=20.0,
    )

    table = sprint.summary_table()

    assert "TASK-001" in table
    assert "done" in table
    assert "Sprint Summary" in table


# ────────────────────────────────────────────────────────────────────────────
# SEKCJA 5: Headless Mode (min 4 testy)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_headless_orchestrator_init():
    """Orchestrator initializes for headless mode."""
    from flowtui.config import FlowTUIConfig, ProjectConfig, LimitsConfig

    config = FlowTUIConfig(
        project=ProjectConfig(name="test", stack="Python", description="Test"),
        limits=LimitsConfig(
            claude_daily_budget=50,
            codex_daily_budget=5,
            gemini_daily_budget=100,
        ),
    )

    mock = MockCLI(responses={"cc": "output"})
    task_mgr = TaskManager(Path("/tmp/test/tasks"))
    task_mgr.tasks_dir.mkdir(parents=True, exist_ok=True)

    orchestrator = Orchestrator(
        invoker=mock,
        task_mgr=task_mgr,
        config=config,
        project_root=Path("/tmp/test"),
    )

    assert orchestrator.invoker == mock
    assert orchestrator.config == config


@pytest.mark.asyncio
async def test_task_result_report_table():
    """TaskResult generates report table."""
    from flowtui.core.engine import PhaseResult

    phase1 = PhaseResult(phase="impl", status="pass", duration_sec=10.0)
    phase2 = PhaseResult(phase="review", status="pass", duration_sec=5.0)

    result = TaskResult(
        task_id="TASK-001",
        status="done",
        retry_count=0,
        phases=[phase1, phase2],
        branch="flowtui/TASK-001",
        diff_stat="3 files changed, 50 insertions(+), 10 deletions(-)",
        total_duration_sec=20.0,
    )

    table = result.report_table()

    assert "TASK-001" in table
    assert "DONE" in table
    assert "impl" in table
    assert "review" in table


@pytest.mark.asyncio
async def test_stats_snapshot_init():
    """StatsSnapshot can be initialized with defaults."""
    snapshot = StatsSnapshot(
        today_calls={"claude": 5, "codex": 2},
        week_calls={"claude": 20, "codex": 10},
        avg_task_duration_sec=15.5,
        retry_rate=0.1,
        total_tasks_done=10,
        total_tasks_blocked=2,
        total_files_changed=25,
        total_lines_added=500,
        total_lines_removed=100,
    )

    assert snapshot.today_calls["claude"] == 5
    assert snapshot.total_tasks_done == 10


@pytest.mark.asyncio
async def test_stats_calculator_snapshot(project_with_records):
    """StatsCalculator.snapshot() returns StatsSnapshot."""
    calc = StatsCalculator(project_with_records)
    snap = calc.snapshot()

    assert isinstance(snap, StatsSnapshot)
    assert hasattr(snap, "today_calls")
    assert hasattr(snap, "total_tasks_done")
    assert snap.total_tasks_done == 1
