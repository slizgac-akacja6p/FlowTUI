"""Parse CC stdout output into Task objects."""

import re
from dataclasses import dataclass, field
from flowtui.core.task_manager import Task


@dataclass
class TaskDraft:
    """Parsed task from CC stdout before saving to file."""

    id: str
    title: str
    sprint: str = "current"
    priority: str = "medium"
    context: str = ""
    requirements: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)


class ParseError(Exception):
    """Raised when CC output cannot be parsed into TaskDraft objects."""

    pass


def _get_section(body: str, name: str) -> str:
    """Extract text content from a ### Section heading within a task body."""
    m = re.search(
        rf"### {name}\s*\n(.*?)(?=### |\Z)", body, re.DOTALL | re.IGNORECASE
    )
    return m.group(1).strip() if m else ""


def _get_list_section(body: str, name: str) -> list[str]:
    """Extract list items from a ### Section heading within a task body."""
    content = _get_section(body, name)
    raw_lines = [l.strip() for l in content.splitlines() if l.strip()]
    result = []
    for line in raw_lines:
        # Skip horizontal-rule separators
        if line == "---":
            continue
        # Remove checkbox syntax "- [ ]" or "- [x]" (with or without trailing space)
        if line.startswith("- [") and "]" in line:
            idx = line.index("]") + 1
            item = line[idx:].lstrip()
            if item:
                result.append(item)
        # Remove plain list marker "- "
        elif line.startswith("- "):
            result.append(line[2:])
        # Keep plain text; skip section headings
        elif not line.startswith("#"):
            result.append(line)
    return result


def parse_draft_tasks(stdout: str) -> list[TaskDraft]:
    """Parse CC stdout output into TaskDraft list.

    Expects tasks in format:
    ## TASK: TASK-001
    ### Title
    [title text]
    ### Sprint
    [sprint]
    ### Priority
    [priority]
    ### Context
    [context text]
    ### Requirements
    [requirements text]
    ### Files to modify
    - [file path]
    ### Constraints
    [constraints text]
    ### Acceptance criteria
    - [ ] [criterion]
    ---

    Args:
        stdout: CC command output containing task definitions.

    Returns:
        List of TaskDraft objects parsed from the output.

    Raises:
        ParseError: If output contains malformed task blocks.
    """
    tasks = []

    # \Z anchors at the true end of string, avoiding multi-line $ ambiguity
    task_pattern = re.compile(
        r"## TASK:\s*(\S+)\s*\n(.*?)(?=## TASK:|\Z)", re.DOTALL
    )

    for match in task_pattern.finditer(stdout):
        task_id = match.group(1).strip()
        body = match.group(2)

        try:
            draft = TaskDraft(
                id=task_id,
                title=_get_section(body, "Title"),
                sprint=_get_section(body, "Sprint") or "current",
                priority=_get_section(body, "Priority") or "medium",
                context=_get_section(body, "Context"),
                requirements=_get_list_section(body, "Requirements"),
                files_to_modify=_get_list_section(body, "Files to modify"),
                constraints=_get_list_section(body, "Constraints"),
                acceptance_criteria=_get_list_section(body, "Acceptance criteria"),
            )
            tasks.append(draft)
        except Exception as e:
            raise ParseError(f"Failed to parse task block {task_id}: {e}") from e

    return tasks


def drafts_to_tasks(drafts: list[TaskDraft]) -> list[Task]:
    """Convert TaskDraft list to Task objects with DRAFT status.

    Args:
        drafts: List of TaskDraft objects from CC output.

    Returns:
        List of Task objects ready to be saved by TaskManager.
    """
    return [
        Task(
            id=d.id,
            title=d.title,
            sprint=d.sprint,
            priority=d.priority,
            status="DRAFT",
            context=d.context,
            requirements=d.requirements,
            files_to_modify=d.files_to_modify,
            constraints=d.constraints,
            acceptance_criteria=d.acceptance_criteria,
        )
        for d in drafts
    ]
