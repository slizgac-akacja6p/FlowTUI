"""Planning pipeline — orchestrate CC planning → parsing → task persistence."""

from pathlib import Path

from flowtui.config.schema import FlowTUIConfig
from flowtui.core.invoker import CLIInvoker
from flowtui.core.prompt_builder import build_plan_prompt
from flowtui.core.task_manager import Task, TaskManager
from flowtui.planning.parser import ParseError, parse_draft_tasks, drafts_to_tasks


async def plan_feature(
    description: str,
    config: FlowTUIConfig,
    invoker: CLIInvoker,
    task_mgr: TaskManager,
    project_root: Path,
    num_tasks: int = 3,
    sprint: str = "current",
) -> list[Task]:
    """Run planning pipeline: CC generates plan → parser extracts tasks → TaskManager saves.

    Executes Claude Code in -p (print) mode to generate task definitions,
    parses the structured output, and persists tasks to TASK-XXX.md files.

    Args:
        description: Feature description to plan.
        config: FlowTUI configuration with project metadata.
        invoker: CLI invoker for running CC.
        task_mgr: TaskManager for persisting tasks to disk.
        project_root: Project root directory for context.
        num_tasks: Number of tasks to generate (default 3).
        sprint: Sprint identifier for tasks (default "current").

    Returns:
        List of Task objects with status="DRAFT" that were created.

    Raises:
        TimeoutError: If CC planning exceeds 120 seconds.
        ParseError: If CC output cannot be parsed into tasks.
    """
    # Build prompt with project context
    prompt = build_plan_prompt(
        description=description,
        config=config,
        project_root=project_root,
        num_tasks=num_tasks,
        sprint=sprint,
    )

    # CC flags: -p mode (print) + allowedTools
    # SubprocessInvoker strips CLAUDECODE env var to allow nested invocation
    args = [
        "--dangerously-skip-permissions",
        "-p",
        prompt,
        "--allowedTools",
        "Read,Write,Edit",
    ]

    result = await invoker.invoke(
        tool="cc",
        args=args,
        cwd=project_root,
        timeout=120.0,
    )

    if result.timed_out:
        raise TimeoutError("CC planning timed out after 120s")

    # Parse CC stdout → TaskDraft list
    drafts = parse_draft_tasks(result.stdout)

    if not drafts:
        # No structured tasks found in CC output
        return []

    # Convert to Task objects with DRAFT status
    tasks = drafts_to_tasks(drafts)

    # Persist to task files (docs/tasks/TASK-XXX.md)
    for task in tasks:
        try:
            task_mgr.create(task)
        except Exception:
            # Don't fail pipeline if individual task file write fails
            pass

    return tasks


async def plan_feature_streaming(
    description: str,
    config: FlowTUIConfig,
    invoker: CLIInvoker,
    task_mgr: TaskManager,
    project_root: Path,
    num_tasks: int = 3,
    sprint: str = "current",
) -> tuple[list[Task], list[str]]:
    """Streaming version of planning pipeline — yields lines as they come.

    Useful for TUI display of long-running planning operations.
    Returns both parsed tasks and raw output lines for inspection.

    Args:
        description: Feature description to plan.
        config: FlowTUI configuration with project metadata.
        invoker: CLI invoker for running CC.
        task_mgr: TaskManager for persisting tasks to disk.
        project_root: Project root directory for context.
        num_tasks: Number of tasks to generate (default 3).
        sprint: Sprint identifier for tasks (default "current").

    Returns:
        Tuple of (tasks, output_lines) where tasks have status="DRAFT".

    Raises:
        TimeoutError: If CC planning exceeds 120 seconds.
        ParseError: If CC output cannot be parsed into tasks.
    """
    prompt = build_plan_prompt(
        description=description,
        config=config,
        project_root=project_root,
        num_tasks=num_tasks,
        sprint=sprint,
    )

    args = [
        "--dangerously-skip-permissions",
        "-p",
        prompt,
        "--allowedTools",
        "Read,Write,Edit",
    ]

    lines = []
    async for line in invoker.invoke_streaming(
        tool="cc",
        args=args,
        cwd=project_root,
        timeout=120.0,
    ):
        lines.append(line.rstrip("\n"))

    # Reconstruct stdout from streaming lines
    stdout = "\n".join(lines)

    # Parse and persist
    drafts = parse_draft_tasks(stdout)
    tasks = drafts_to_tasks(drafts)

    for task in tasks:
        try:
            task_mgr.create(task)
        except Exception:
            pass

    return tasks, lines
