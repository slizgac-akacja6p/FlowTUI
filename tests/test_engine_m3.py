"""Tests for Orchestrator engine (M3) — run_task, run_sprint, merge, circuit breaker."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from flowtui.core.engine import (
    Orchestrator,
    TaskResult,
    SprintResult,
    PhaseResult,
)
from flowtui.core.git_ops import DiffStat, MergeResult
from flowtui.core.invoker import MockCLI, InvokeResult
from flowtui.core.task_manager import TaskManager, Task
from flowtui.core.test_runner import TestResult


@pytest.fixture
def temp_project():
    """Temporary project directory with task directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        (project_root / "docs").mkdir()
        (project_root / "docs" / "tasks").mkdir()
        yield project_root


@pytest.fixture
def task_manager(temp_project):
    """TaskManager instance for tests."""
    return TaskManager(temp_project / "docs" / "tasks")


@pytest.fixture
def mock_config():
    """Mock FlowTUIConfig."""
    config = type("MockConfig", (), {
        "project": type("Project", (), {
            "name": "TestProject",
            "stack": "Python 3.11",
        })(),
        "git": type("Git", (), {
            "develop_branch": "develop",
        })(),
    })()
    return config


@pytest.fixture
def mock_invoker_default():
    """Mock CLI invoker that returns success."""
    return MockCLI(responses={"cc": "Implementation successful\n"})


@pytest.fixture
def mock_git_ops_success():
    """Mock GitOps with all operations successful."""
    mock = MagicMock()
    mock.get_head_hash = AsyncMock(return_value="abc1234567890abcdef1234567890abcdef123456")
    mock.create_branch = AsyncMock()
    mock.checkout = AsyncMock()
    mock.checkpoint = AsyncMock(return_value="def4567890abcdef1234567890abcdef12345678")
    mock.rollback = AsyncMock()
    mock.diff_stat = AsyncMock(return_value=DiffStat(
        files_changed=2,
        insertions=15,
        deletions=3,
        raw="2 files changed, 15 insertions(+), 3 deletions(-)"
    ))
    mock.merge_to = AsyncMock(return_value=MergeResult(success=True))
    return mock


@pytest.fixture
def mock_test_runner_pass():
    """Mock TestRunner that passes all tests."""
    mock = MagicMock()
    mock.run_tests = AsyncMock(return_value=TestResult(
        passed=True,
        count=5,
        output="5 passed in 1.23s",
        skipped=False,
        framework="pytest",
        duration_sec=1.23
    ))
    return mock


@pytest.fixture
def mock_test_runner_fail():
    """Mock TestRunner that fails tests."""
    mock = MagicMock()
    mock.run_tests = AsyncMock(return_value=TestResult(
        passed=False,
        count=5,
        output="2 failed, 3 passed in 1.50s",
        skipped=False,
        framework="pytest",
        duration_sec=1.50
    ))
    return mock


def create_test_task(task_id="TASK-001", status="TODO"):
    """Helper to create a test task."""
    return Task(
        id=task_id,
        title=f"Test Task {task_id}",
        sprint="sprint-1",
        priority="high",
        status=status,
        context="Test implementation task",
        requirements=["Req 1", "Req 2"],
        files_to_modify=["src/main.py"],
        acceptance_criteria=["[ ] Tests pass", "[ ] Code review approved"],
    )


class TestRunTaskHappyPath:
    """Test run_task with successful execution."""

    @pytest.mark.asyncio
    async def test_run_task_success(self, temp_project, task_manager, mock_config,
                                   mock_invoker_default, mock_git_ops_success,
                                   mock_test_runner_pass):
        """run_task completes successfully with passing tests."""
        # Setup
        task = create_test_task()
        task_manager.create(task)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
            test_runner=mock_test_runner_pass,
        )

        # Execute
        result = await orchestrator.run_task("TASK-001")

        # Verify
        assert result.task_id == "TASK-001"
        assert result.status == "done"
        assert result.retry_count == 0
        assert len(result.phases) > 0
        assert result.branch == "flowtui/TASK-001"
        assert result.total_duration_sec > 0

    @pytest.mark.asyncio
    async def test_run_task_no_git_ops(self, temp_project, task_manager, mock_config,
                                       mock_invoker_default, mock_test_runner_pass):
        """run_task succeeds without GitOps (git_ops=None)."""
        task = create_test_task()
        task_manager.create(task)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=None,
            test_runner=mock_test_runner_pass,
        )

        result = await orchestrator.run_task("TASK-001")

        assert result.status == "done"
        assert result.branch == "flowtui/TASK-001"
        # Without git_ops, diff_stat should be empty
        assert result.diff_stat == ""

    @pytest.mark.asyncio
    async def test_run_task_no_test_runner(self, temp_project, task_manager, mock_config,
                                          mock_invoker_default, mock_git_ops_success):
        """run_task succeeds without TestRunner (test_runner=None)."""
        task = create_test_task()
        task_manager.create(task)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
            test_runner=None,
        )

        result = await orchestrator.run_task("TASK-001")

        assert result.status == "done"
        # Without test_runner, impl_passed should be True (no tests to fail)

    @pytest.mark.asyncio
    async def test_run_task_updates_status_progression(self, temp_project, task_manager,
                                                      mock_config, mock_invoker_default,
                                                      mock_git_ops_success, mock_test_runner_pass):
        """run_task updates task status through progression."""
        task = create_test_task()
        task_manager.create(task)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
            test_runner=mock_test_runner_pass,
        )

        # Check initial status
        loaded = task_manager.load("TASK-001")
        assert loaded.status == "TODO"

        # Run task
        result = await orchestrator.run_task("TASK-001")

        # Check final status (should be updated)
        loaded = task_manager.load("TASK-001")
        assert loaded.status == "DONE"

    @pytest.mark.asyncio
    async def test_task_result_has_phases(self, temp_project, task_manager, mock_config,
                                         mock_invoker_default, mock_git_ops_success,
                                         mock_test_runner_pass):
        """TaskResult.phases populated with execution phases."""
        task = create_test_task()
        task_manager.create(task)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
            test_runner=mock_test_runner_pass,
        )

        result = await orchestrator.run_task("TASK-001")

        assert len(result.phases) > 0
        # At minimum should have impl phase
        assert any(p.phase == "impl" or p.phase.startswith("impl_") for p in result.phases)

    @pytest.mark.asyncio
    async def test_task_result_report_table(self, temp_project, task_manager, mock_config,
                                           mock_invoker_default, mock_git_ops_success,
                                           mock_test_runner_pass):
        """TaskResult.report_table() returns formatted string."""
        task = create_test_task()
        task_manager.create(task)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
            test_runner=mock_test_runner_pass,
        )

        result = await orchestrator.run_task("TASK-001")
        report = result.report_table()

        assert isinstance(report, str)
        assert "TASK-001" in report
        assert "done" in report.lower()
        assert "retries: 0" in report


class TestRunTaskRetry:
    """Test retry logic in run_task."""

    @pytest.mark.asyncio
    async def test_run_task_fail_first_retry_success(self, temp_project, task_manager,
                                                    mock_config, mock_git_ops_success):
        """run_task retries on failure and succeeds."""
        task = create_test_task()
        task_manager.create(task)

        # Mock invoker that always succeeds
        invoker = MockCLI(responses={"cc": "Implementation output\n"})

        # Create test runner that fails at first, passes on retries
        call_count = [0]
        async def run_tests_side_effect():
            # First call fails, rest pass
            call_count[0] += 1
            passed = call_count[0] > 1
            return TestResult(
                passed=passed, count=5, output="pass" if passed else "fail",
                skipped=False, framework="pytest", duration_sec=1.0
            )
        mock_test_runner = MagicMock()
        mock_test_runner.run_tests = AsyncMock(side_effect=run_tests_side_effect)

        orchestrator = Orchestrator(
            invoker=invoker,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
            test_runner=mock_test_runner,
        )

        result = await orchestrator.run_task("TASK-001")

        assert result.status == "done"
        assert result.retry_count >= 1  # Had at least one retry
        assert call_count[0] >= 2  # Called test runner multiple times

    @pytest.mark.asyncio
    async def test_run_task_fail_max_retry_blocked(self, temp_project, task_manager,
                                                   mock_config, mock_git_ops_success):
        """run_task exhausts retries and blocks task."""
        task = create_test_task()
        task_manager.create(task)

        invoker = MockCLI(responses={"cc": "Implementation\n"})

        # Always fail
        mock_test_runner = MagicMock()
        mock_test_runner.run_tests = AsyncMock(return_value=TestResult(
            passed=False, count=5, output="5 failed",
            skipped=False, framework="pytest", duration_sec=1.0
        ))

        orchestrator = Orchestrator(
            invoker=invoker,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
            test_runner=mock_test_runner,
        )

        result = await orchestrator.run_task("TASK-001")

        assert result.status == "blocked"
        assert result.retry_count == 2  # MAX_RETRY = 2

    @pytest.mark.asyncio
    async def test_run_task_rollback_on_fail(self, temp_project, task_manager, mock_config,
                                            mock_git_ops_success):
        """run_task calls rollback when tests fail."""
        task = create_test_task()
        task_manager.create(task)

        invoker = MockCLI(responses={"cc": "Output\n"})

        # First test fails, second test passes to exit retry loop
        test_results = [
            TestResult(passed=False, count=5, output="failed",
                      skipped=False, framework="pytest", duration_sec=1.0),
            TestResult(passed=True, count=5, output="passed",
                      skipped=False, framework="pytest", duration_sec=1.0),
        ]
        call_count = [0]
        async def run_tests_side_effect():
            result = test_results[call_count[0]]
            call_count[0] += 1
            return result
        mock_test_runner = MagicMock()
        mock_test_runner.run_tests = AsyncMock(side_effect=run_tests_side_effect)

        orchestrator = Orchestrator(
            invoker=invoker,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
            test_runner=mock_test_runner,
        )

        result = await orchestrator.run_task("TASK-001")

        # Verify rollback was called (at least once for failed attempt)
        assert mock_git_ops_success.rollback.called


class TestCircuitBreaker:
    """Test circuit breaker in run_sprint."""

    @pytest.mark.asyncio
    async def test_run_sprint_circuit_breaker_triggered(self, temp_project, task_manager,
                                                       mock_config, mock_invoker_default,
                                                       mock_git_ops_success):
        """run_sprint stops after 3 consecutive failures."""
        # Create 5 tasks
        for i in range(1, 6):
            task = create_test_task(task_id=f"TASK-{i:03d}", status="TODO")
            task_manager.create(task)

        # Mock test runner that always fails
        mock_test_runner = MagicMock()
        mock_test_runner.run_tests = AsyncMock(return_value=TestResult(
            passed=False, count=0, output="failed",
            skipped=False, framework="pytest", duration_sec=0.5
        ))

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
            test_runner=mock_test_runner,
        )

        result = await orchestrator.run_sprint()

        # Circuit breaker should trigger after 3 consecutive failures
        assert result.circuit_breaker is True
        # Should have stopped before running all 5 tasks
        assert result.total_attempted <= 4
        assert result.blocked >= 3

    @pytest.mark.asyncio
    async def test_run_sprint_reset_on_success(self, temp_project, task_manager, mock_config,
                                              mock_invoker_default, mock_git_ops_success):
        """run_sprint resets failure counter on success."""
        # Create 4 tasks: FAIL, FAIL, SUCCESS, FAIL (3rd fail)
        # This tests that success resets counter, then 3 fails trigger breaker
        for i in range(1, 5):
            task = create_test_task(task_id=f"TASK-{i:03d}", status="TODO")
            task_manager.create(task)

        # Track which task we're on
        task_counter = [0]

        async def run_tests_side_effect():
            task_counter[0] += 1
            # Task 1: fail, Task 2: fail, Task 3: success, Task 4+: fail
            if task_counter[0] <= 2 or task_counter[0] > 3:
                return TestResult(
                    passed=False, count=5, output="fail",
                    skipped=False, framework="pytest", duration_sec=0.5
                )
            else:
                return TestResult(
                    passed=True, count=5, output="pass",
                    skipped=False, framework="pytest", duration_sec=0.5
                )

        mock_test_runner = MagicMock()
        mock_test_runner.run_tests = AsyncMock(side_effect=run_tests_side_effect)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
            test_runner=mock_test_runner,
        )

        result = await orchestrator.run_sprint()

        # Circuit breaker should trigger after task 4 fails (3rd consecutive after reset)
        assert result.circuit_breaker is True
        # At least tasks 1-3 attempted, task 4 will have failed
        assert result.total_attempted >= 3

    @pytest.mark.asyncio
    async def test_run_sprint_empty_tasks(self, temp_project, task_manager, mock_config,
                                         mock_invoker_default, mock_git_ops_success):
        """run_sprint with no TODO tasks returns empty result."""
        # Create tasks but set them to DONE (not TODO)
        for i in range(1, 4):
            task = create_test_task(task_id=f"TASK-{i:03d}", status="DONE")
            task_manager.create(task)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
        )

        result = await orchestrator.run_sprint()

        assert result.completed == 0
        assert result.total_attempted == 0
        assert result.blocked == 0

    @pytest.mark.asyncio
    async def test_sprint_result_summary_table(self, temp_project, task_manager, mock_config,
                                              mock_invoker_default, mock_git_ops_success,
                                              mock_test_runner_pass):
        """SprintResult.summary_table() returns formatted string."""
        # Create 2 tasks
        for i in range(1, 3):
            task = create_test_task(task_id=f"TASK-{i:03d}", status="TODO")
            task_manager.create(task)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
            test_runner=mock_test_runner_pass,
        )

        result = await orchestrator.run_sprint()
        summary = result.summary_table()

        assert isinstance(summary, str)
        assert "Sprint Summary" in summary
        assert "2" in summary  # total_attempted
        assert "2" in summary  # completed


class TestMerge:
    """Test merge operations."""

    @pytest.mark.asyncio
    async def test_merge_without_git_ops(self, temp_project, task_manager, mock_config,
                                        mock_invoker_default):
        """merge() raises RuntimeError when git_ops=None."""
        task = create_test_task(status="DONE")
        task_manager.create(task)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=None,
        )

        with pytest.raises(RuntimeError) as exc_info:
            await orchestrator.merge("TASK-001")

        assert "GitOps not configured" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_merge_task_not_done(self, temp_project, task_manager, mock_config,
                                      mock_invoker_default, mock_git_ops_success):
        """merge() raises ValueError if task status != DONE."""
        task = create_test_task(status="TODO")
        task_manager.create(task)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
        )

        with pytest.raises(ValueError) as exc_info:
            await orchestrator.merge("TASK-001")

        assert "not done" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_merge_single_task(self, temp_project, task_manager, mock_config,
                                    mock_invoker_default, mock_git_ops_success):
        """merge() calls git_ops.merge_to() with correct branch name."""
        task = create_test_task(status="DONE")
        task_manager.create(task)

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
        )

        result = await orchestrator.merge("TASK-001")

        # Verify merge_to was called with correct branch name
        mock_git_ops_success.merge_to.assert_called_once()
        call_args = mock_git_ops_success.merge_to.call_args
        assert call_args[0][0] == "develop"  # target
        assert call_args[0][1] == "flowtui/TASK-001"  # source branch

    @pytest.mark.asyncio
    async def test_merge_all_done_tasks(self, temp_project, task_manager, mock_config,
                                       mock_invoker_default, mock_git_ops_success):
        """merge() without task_id merges all DONE tasks."""
        # Create mix of DONE and TODO tasks
        task_manager.create(create_test_task(task_id="TASK-001", status="DONE"))
        task_manager.create(create_test_task(task_id="TASK-002", status="TODO"))
        task_manager.create(create_test_task(task_id="TASK-003", status="DONE"))

        orchestrator = Orchestrator(
            invoker=mock_invoker_default,
            task_mgr=task_manager,
            config=mock_config,
            project_root=temp_project,
            git_ops=mock_git_ops_success,
        )

        results = await orchestrator.merge()  # No task_id

        assert isinstance(results, list)
        assert len(results) == 2  # Only 2 DONE tasks
        # Verify branches merged
        calls = mock_git_ops_success.merge_to.call_args_list
        assert len(calls) == 2
