"""Context writer — generates sprint.md with current project state."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime


SPRINT_CONTEXT_TEMPLATE = """# Sprint Context
Generated: {timestamp}

## Project
Name: {project_name}
Stack: {stack}

## Active Tasks
{active_tasks}

## Limits Today
{limits_summary}

## Last completed
{last_completed}
"""


def write_sprint_context(
    project_root: Path,
    tasks: list,
    limits: dict[str, tuple[int, int]],
    project_name: str = "Unknown",
    stack: str = "Unknown",
) -> Path:
    """Write docs/context/sprint.md with current sprint state.

    Args:
        project_root: Root path of the project
        tasks: List of Task-like objects (uses duck typing with getattr)
        limits: Dict mapping tool names to (used, budget) tuples
        project_name: Name of the project
        stack: Stack description (e.g. "Python, Flask, SQLite")

    Returns:
        Path to the written sprint.md file (~20-30 lines, ~200 tokens)
    """
    context_dir = project_root / "docs" / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    output_path = context_dir / "sprint.md"

    # Active tasks (todo + in_progress, max 5)
    active = [
        t for t in tasks
        if getattr(t, "status", "").upper() in ("TODO", "IN_PROGRESS")
    ][:5]
    active_tasks_str = "\n".join(
        f"- [{getattr(t, 'status', '?').upper()}] {getattr(t, 'id', '?')}: {getattr(t, 'title', '?')}"
        for t in active
    ) or "No active tasks."

    # Last completed (max 3, reversed to show newest first)
    done = [
        t for t in tasks
        if getattr(t, "status", "").upper() == "DONE"
    ][-3:]
    last_completed_str = "\n".join(
        f"- {getattr(t, 'id', '?')}: {getattr(t, 'title', '?')}"
        for t in done
    ) or "None yet."

    # Limits summary
    limits_lines = [
        f"- {tool}: {used}/{budget}"
        for tool, (used, budget) in limits.items()
    ]
    limits_summary = "\n".join(limits_lines) or "No limits configured."

    content = SPRINT_CONTEXT_TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        project_name=project_name,
        stack=stack,
        active_tasks=active_tasks_str,
        limits_summary=limits_summary,
        last_completed=last_completed_str,
    )

    output_path.write_text(content, encoding="utf-8")
    return output_path
