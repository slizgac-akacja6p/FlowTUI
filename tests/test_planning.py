"""Tests for planning module — parser and pipeline."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from flowtui.core.invoker import MockCLI, InvokeResult
from flowtui.core.task_manager import TaskManager, Task
from flowtui.planning.parser import (
    TaskDraft,
    ParseError,
    parse_draft_tasks,
    drafts_to_tasks,
)
from flowtui.planning.pipeline import plan_feature, plan_feature_streaming
from flowtui.config.schema import FlowTUIConfig


# ── Test parse_draft_tasks ──────────────────────────────────────────────────

class TestParserBasic:
    """Test basic parsing of task blocks."""

    def test_parse_single_task(self):
        """Parse single TASK block."""
        output = """
## TASK: TASK-001
### Title
Login Feature
### Sprint
sprint-1
### Priority
high
### Context
Users need authentication
### Requirements
- JWT tokens
### Files to modify
- src/auth.py
### Constraints
- No breaking changes
### Acceptance criteria
- [ ] Login works
---
"""
        drafts = parse_draft_tasks(output)
        assert len(drafts) == 1
        assert drafts[0].id == "TASK-001"
        assert drafts[0].title == "Login Feature"
        assert drafts[0].sprint == "sprint-1"
        assert drafts[0].priority == "high"

    def test_parse_multiple_tasks(self):
        """Parse multiple TASK blocks."""
        output = """
## TASK: TASK-001
### Title
Task One
### Sprint
sprint-1
### Priority
high
### Context
First task
### Requirements
- Requirement 1
### Files to modify
- file1.py
### Constraints
- None
### Acceptance criteria
- [ ] Done
---
## TASK: TASK-002
### Title
Task Two
### Sprint
sprint-1
### Priority
medium
### Context
Second task
### Requirements
- Requirement 2
### Files to modify
- file2.py
### Constraints
- None
### Acceptance criteria
- [ ] Done
---
"""
        drafts = parse_draft_tasks(output)
        assert len(drafts) == 2
        assert drafts[0].id == "TASK-001"
        assert drafts[1].id == "TASK-002"

    def test_parse_empty_output(self):
        """Parse empty output returns empty list."""
        output = "No tasks here"
        drafts = parse_draft_tasks(output)
        assert drafts == []

    def test_parse_no_tasks_in_output(self):
        """Parse output without TASK: blocks returns empty list."""
        output = "Some regular output without task blocks"
        drafts = parse_draft_tasks(output)
        assert drafts == []


class TestParserSections:
    """Test extraction of individual sections."""

    def test_parse_with_list_items(self):
        """Parse section with multiple list items."""
        output = """
## TASK: TASK-001
### Title
Multi Item
### Sprint
current
### Priority
medium
### Context
Test context
### Requirements
- Requirement A
- Requirement B
- Requirement C
### Files to modify
- src/file1.py
- src/file2.py
### Constraints
- Constraint 1
- Constraint 2
### Acceptance criteria
- [ ] Criterion A
- [ ] Criterion B
---
"""
        drafts = parse_draft_tasks(output)
        assert len(drafts) == 1
        assert len(drafts[0].requirements) == 3
        assert "Requirement A" in drafts[0].requirements[0]
        assert len(drafts[0].files_to_modify) == 2
        assert "src/file1.py" in drafts[0].files_to_modify
        assert len(drafts[0].acceptance_criteria) == 2

    def test_parse_empty_sections(self):
        """Parse task with empty sections uses defaults."""
        output = """
## TASK: TASK-001
### Title
Minimal
### Sprint
### Priority
### Context
### Requirements
### Files to modify
### Constraints
### Acceptance criteria
---
"""
        drafts = parse_draft_tasks(output)
        assert len(drafts) == 1
        assert drafts[0].sprint == "current"
        assert drafts[0].priority == "medium"
        assert drafts[0].context == ""
        assert drafts[0].requirements == []
        assert drafts[0].files_to_modify == []
        assert drafts[0].acceptance_criteria == []

    def test_parse_checkbox_syntax(self):
        """Parse checkbox syntax with and without spaces."""
        output = """
## TASK: TASK-001
### Title
Checkboxes
### Sprint
current
### Priority
medium
### Context
Test
### Requirements
Test
### Files to modify
Test
### Constraints
Test
### Acceptance criteria
- [ ] Item with space
- [x] Item checked
- [ ]Item without space
---
"""
        drafts = parse_draft_tasks(output)
        assert len(drafts) == 1
        assert len(drafts[0].acceptance_criteria) == 3
        assert "Item with space" in drafts[0].acceptance_criteria
        assert "Item checked" in drafts[0].acceptance_criteria
        assert "Item without space" in drafts[0].acceptance_criteria

    def test_parse_multiline_context(self):
        """Parse multiline context text."""
        output = """
## TASK: TASK-001
### Title
Multiline Context
### Sprint
current
### Priority
medium
### Context
This is a multiline
context with several
lines of text
### Requirements
- Req
### Files to modify
- file.py
### Constraints
- None
### Acceptance criteria
- [ ] Done
---
"""
        drafts = parse_draft_tasks(output)
        assert len(drafts) == 1
        assert "multiline" in drafts[0].context
        assert "several" in drafts[0].context
        assert "lines of text" in drafts[0].context

    def test_parse_task_id_formats(self):
        """Parse various valid task ID formats."""
        output = """
## TASK: TASK-001
### Title
Test
### Sprint
current
### Priority
medium
### Context
Test
### Requirements
- Test
### Files to modify
- file.py
### Constraints
- None
### Acceptance criteria
- [ ] Done
---
## TASK: TASK-999
### Title
Test2
### Sprint
current
### Priority
medium
### Context
Test
### Requirements
- Test
### Files to modify
- file.py
### Constraints
- None
### Acceptance criteria
- [ ] Done
---
"""
        drafts = parse_draft_tasks(output)
        assert len(drafts) == 2
        assert drafts[0].id == "TASK-001"
        assert drafts[1].id == "TASK-999"


class TestDraftsToTasks:
    """Test conversion from TaskDraft to Task."""

    def test_drafts_to_tasks_status(self):
        """Converted tasks have DRAFT status."""
        drafts = [
            TaskDraft(
                id="TASK-001",
                title="Test",
                sprint="current",
                priority="high",
                context="Context",
                requirements=["Req1"],
                files_to_modify=["file.py"],
                constraints=["Constraint"],
                acceptance_criteria=["Criterion"],
            )
        ]
        tasks = drafts_to_tasks(drafts)
        assert len(tasks) == 1
        assert tasks[0].status == "DRAFT"
        assert tasks[0].id == "TASK-001"
        assert tasks[0].title == "Test"

    def test_drafts_to_tasks_multiple(self):
        """Convert multiple drafts to tasks."""
        drafts = [
            TaskDraft(
                id="TASK-001",
                title="First",
                sprint="current",
                priority="high",
                context="",
                requirements=[],
                files_to_modify=[],
                constraints=[],
                acceptance_criteria=[],
            ),
            TaskDraft(
                id="TASK-002",
                title="Second",
                sprint="current",
                priority="medium",
                context="",
                requirements=[],
                files_to_modify=[],
                constraints=[],
                acceptance_criteria=[],
            ),
        ]
        tasks = drafts_to_tasks(drafts)
        assert len(tasks) == 2
        assert all(t.status == "DRAFT" for t in tasks)


# ── Test planning pipeline ──────────────────────────────────────────────────


@pytest.fixture
def temp_project_dir():
    """Temporary project directory with minimal structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        (path / "docs").mkdir(exist_ok=True)
        (path / "docs" / "tasks").mkdir(exist_ok=True)
        yield path


@pytest.fixture
def mock_config():
    """Mock FlowTUIConfig."""
    # Minimal config for testing
    config = type("MockConfig", (), {
        "project": type("Project", (), {
            "name": "TestProject",
            "stack": "Python 3.11 + Textual",
        })
    })()
    return config


class TestPlanningPipelineAsync:
    """Test async planning pipeline."""

    @pytest.mark.asyncio
    async def test_plan_feature_basic(self, temp_project_dir, mock_config):
        """Test basic plan_feature invocation."""
        task_mgr = TaskManager(temp_project_dir / "docs" / "tasks")

        # Create mock CLI with task output
        mock_output = """
## TASK: TASK-001
### Title
Test Task
### Sprint
current
### Priority
high
### Context
Test context
### Requirements
- Requirement
### Files to modify
- src/test.py
### Constraints
- None
### Acceptance criteria
- [ ] Test passes
---
"""
        mock_cli = MockCLI({"cc": mock_output})

        tasks = await plan_feature(
            description="Test planning",
            config=mock_config,
            invoker=mock_cli,
            task_mgr=task_mgr,
            project_root=temp_project_dir,
            num_tasks=1,
            sprint="current",
        )

        assert len(tasks) == 1
        assert tasks[0].id == "TASK-001"
        assert tasks[0].title == "Test Task"
        assert tasks[0].status == "DRAFT"

        # Verify task file was created
        task_file = temp_project_dir / "docs" / "tasks" / "TASK-001.md"
        assert task_file.exists()

    @pytest.mark.asyncio
    async def test_plan_feature_no_tasks(self, temp_project_dir, mock_config):
        """Test plan_feature with no tasks in output."""
        task_mgr = TaskManager(temp_project_dir / "docs" / "tasks")
        mock_cli = MockCLI({"cc": "No tasks found in this output"})

        tasks = await plan_feature(
            description="Test",
            config=mock_config,
            invoker=mock_cli,
            task_mgr=task_mgr,
            project_root=temp_project_dir,
        )

        assert tasks == []

    @pytest.mark.asyncio
    async def test_plan_feature_timeout(self, temp_project_dir, mock_config):
        """Test plan_feature raises on timeout."""
        task_mgr = TaskManager(temp_project_dir / "docs" / "tasks")

        # Create mock CLI that signals timeout
        class TimeoutCLI:
            async def invoke(self, tool, args, cwd, timeout=300.0):
                return InvokeResult(
                    stdout="",
                    stderr="Timeout",
                    returncode=-1,
                    duration_sec=120.1,
                    timed_out=True,
                )

        with pytest.raises(TimeoutError):
            await plan_feature(
                description="Test",
                config=mock_config,
                invoker=TimeoutCLI(),
                task_mgr=task_mgr,
                project_root=temp_project_dir,
            )

    @pytest.mark.asyncio
    async def test_plan_feature_streaming(self, temp_project_dir, mock_config):
        """Test streaming version of plan_feature."""
        task_mgr = TaskManager(temp_project_dir / "docs" / "tasks")

        mock_output = """
## TASK: TASK-001
### Title
Streamed Task
### Sprint
current
### Priority
medium
### Context
Context
### Requirements
- Req
### Files to modify
- file.py
### Constraints
- None
### Acceptance criteria
- [ ] Done
---
"""
        mock_cli = MockCLI({"cc": mock_output})

        tasks, lines = await plan_feature_streaming(
            description="Stream test",
            config=mock_config,
            invoker=mock_cli,
            task_mgr=task_mgr,
            project_root=temp_project_dir,
        )

        assert len(tasks) == 1
        assert tasks[0].id == "TASK-001"
        assert len(lines) > 0

    @pytest.mark.asyncio
    async def test_plan_feature_multiple_tasks(self, temp_project_dir, mock_config):
        """Test planning with multiple tasks."""
        task_mgr = TaskManager(temp_project_dir / "docs" / "tasks")

        mock_output = """
## TASK: TASK-001
### Title
First
### Sprint
sprint-1
### Priority
high
### Context
First context
### Requirements
- Req1
### Files to modify
- file1.py
### Constraints
- None
### Acceptance criteria
- [ ] Done
---
## TASK: TASK-002
### Title
Second
### Sprint
sprint-1
### Priority
medium
### Context
Second context
### Requirements
- Req2
### Files to modify
- file2.py
### Constraints
- None
### Acceptance criteria
- [ ] Done
---
"""
        mock_cli = MockCLI({"cc": mock_output})

        tasks = await plan_feature(
            description="Multi-task planning",
            config=mock_config,
            invoker=mock_cli,
            task_mgr=task_mgr,
            project_root=temp_project_dir,
            num_tasks=2,
        )

        assert len(tasks) == 2
        assert tasks[0].id == "TASK-001"
        assert tasks[1].id == "TASK-002"

        # Verify both task files were created
        assert (temp_project_dir / "docs" / "tasks" / "TASK-001.md").exists()
        assert (temp_project_dir / "docs" / "tasks" / "TASK-002.md").exists()
