"""Build Claude prompts for planning, coding, and review tasks."""
from pathlib import Path

from flowtui.config.schema import FlowTUIConfig
from flowtui.core.complexity import Complexity, estimate_complexity
from flowtui.core.task_manager import Task
from flowtui.planning.prompts import CODE_TASK, PLAN_DRAFT, REVIEW_TASK


def build_plan_prompt(
    description: str,
    config: FlowTUIConfig,
    project_root: Path,
    num_tasks: int = 3,
    sprint: str = "current",
) -> str:
    """
    Build Claude prompt for planning a feature.

    Args:
        description: Feature description to plan.
        config: FlowTUI configuration.
        project_root: Project root directory path.
        num_tasks: Number of tasks to generate (default 3).
        sprint: Sprint identifier (default "current").

    Returns:
        Formatted prompt string with placeholders filled.
    """
    complexity = estimate_complexity(description)

    # Load architecture summary if exists (optional)
    arch_file = project_root / "docs" / "architecture.md"
    architecture_summary = (
        arch_file.read_text() if arch_file.exists() else "No architecture doc."
    )

    # Truncate if too long to avoid prompt bloat
    if len(architecture_summary) > 2000:
        architecture_summary = architecture_summary[:2000] + "\n[truncated]"

    # Current tasks summary — placeholder for integration with TaskManager
    current_tasks = "No current tasks."

    return PLAN_DRAFT.format(
        project_name=config.project.name,
        stack=config.project.stack,
        architecture_summary=architecture_summary,
        current_tasks=current_tasks,
        description=description,
        sprint=sprint,
        num_tasks=num_tasks,
    )


def build_code_prompt(task: Task, config: FlowTUIConfig) -> str:
    """
    Build Claude prompt for implementing a task.

    Args:
        task: Task dataclass with requirements and context.
        config: FlowTUI configuration.

    Returns:
        Formatted prompt string with task details filled.
    """
    return CODE_TASK.format(
        project_name=config.project.name,
        stack=config.project.stack,
        task_title=task.title,
        task_context=task.context or "No context provided.",
        task_requirements=task.requirements or "See acceptance criteria.",
        files_to_modify=(
            "\n".join(f"- {f}" for f in (task.files_to_modify or []))
            or "Not specified."
        ),
        task_constraints=task.constraints or "None.",
        acceptance_criteria=(
            "\n".join(f"- [ ] {c}" for c in (task.acceptance_criteria or []))
        ),
    )


def build_review_prompt(task: Task, config: FlowTUIConfig) -> str:
    """
    Build Claude prompt for reviewing a task implementation.

    Args:
        task: Task dataclass with acceptance criteria.
        config: FlowTUI configuration.

    Returns:
        Formatted prompt string with review details filled.
    """
    return REVIEW_TASK.format(
        project_name=config.project.name,
        stack=config.project.stack,
        task_title=task.title,
        files_to_modify=(
            "\n".join(f"- {f}" for f in (task.files_to_modify or []))
            or "Not specified."
        ),
        acceptance_criteria=(
            "\n".join(f"- [ ] {c}" for c in (task.acceptance_criteria or []))
        ),
    )
