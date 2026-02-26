"""Orchestrator — coordinates AI tool invocations for plan/code/review commands."""

import re
import warnings
from pathlib import Path
from typing import AsyncIterator

from flowtui.config.schema import FlowTUIConfig
from flowtui.core.invoker import CLIInvoker
from flowtui.core.prompt_builder import (
    build_code_prompt,
    build_plan_prompt,
    build_review_prompt,
)
from flowtui.core.task_manager import Task, TaskManager, TaskNotFoundError


class Orchestrator:
    """Coordinates AI tool invocations for plan/code/review commands.

    Provides high-level async generators for planning, coding, and reviewing tasks,
    managing status transitions and persistence via TaskManager.
    """

    def __init__(
        self,
        invoker: CLIInvoker,
        task_mgr: TaskManager,
        config: FlowTUIConfig,
        project_root: Path,
    ):
        """Initialize Orchestrator with dependencies.

        Args:
            invoker: CLI invoker (SubprocessInvoker or MockCLI for tests).
            task_mgr: TaskManager for task persistence.
            config: FlowTUI configuration.
            project_root: Project root directory.
        """
        self.invoker = invoker
        self.task_mgr = task_mgr
        self.config = config
        self.project_root = project_root

    async def plan(
        self,
        description: str,
        num_tasks: int = 3,
    ) -> AsyncIterator[str]:
        """Stream planning output, yield lines, save tasks as DRAFT.

        Invokes CC planning with project context, streams output line by line,
        parses structured task definitions, and persists them to disk as DRAFT tasks.

        Args:
            description: Feature description to plan.
            num_tasks: Number of tasks to generate (default 3).

        Yields:
            Output lines from CC planning pipeline.
            Final line is summary: "Created N draft tasks: TASK-001, TASK-002, ..."
        """
        try:
            from flowtui.planning.parser import parse_draft_tasks, drafts_to_tasks

            prompt = build_plan_prompt(
                description=description,
                config=self.config,
                project_root=self.project_root,
                num_tasks=num_tasks,
            )
            args = [
                "--dangerously-skip-permissions",
                "-p", prompt,
                "--allowedTools", "Read,Write,Edit",
            ]

            lines: list[str] = []
            # Stream directly so the user sees output immediately, not after 120s
            async for line in self.invoker.invoke_streaming(
                tool="cc",
                args=args,
                cwd=self.project_root,
                timeout=120.0,
            ):
                lines.append(line)
                yield line

            # Parse and persist after streaming is complete
            stdout = "\n".join(lines)
            drafts = parse_draft_tasks(stdout)
            tasks = drafts_to_tasks(drafts)

            saved = 0
            for task in tasks:
                try:
                    self.task_mgr.create(task)
                    saved += 1
                except Exception as e:
                    warnings.warn(f"Failed to save task {task.id}: {e}")

            yield f"--- Planning complete: {saved} draft tasks created ---"

        except TimeoutError as e:
            yield f"[ERROR] Planning timeout: {e}"
        except Exception as e:
            yield f"[ERROR] Planning failed: {e}"

    async def code(self, task_id: str) -> AsyncIterator[str]:
        """Stream code implementation for a task.

        Loads task context, builds code prompt, invokes CC with streaming output,
        updates task status to IN_PROGRESS on completion.

        Args:
            task_id: Task identifier (e.g., "TASK-001").

        Yields:
            Output lines from CC code implementation.
            Final line is status: "Coding complete for TASK-XXX"
        """
        try:
            # Load task
            task = self.task_mgr.load(task_id)

            # Build prompt
            prompt = build_code_prompt(task, self.config)

            # Invoke streaming
            args = [
                "--dangerously-skip-permissions",
                "-p",
                prompt,
                "--allowedTools",
                "Read,Write,Edit,Bash",
            ]

            line_count = 0
            async for line in self.invoker.invoke_streaming(
                tool="cc",
                args=args,
                cwd=self.project_root,
                timeout=600.0,
            ):
                yield line.rstrip("\n")
                line_count += 1

            # Update task status to IN_PROGRESS
            self.task_mgr.update_status(
                task_id,
                "IN_PROGRESS",
                f"Coding started (CC streamed {line_count} lines)",
            )

            yield f"\n✓ Coding complete for {task_id}"

        except TaskNotFoundError:
            yield f"[ERROR] Task {task_id} not found"
        except Exception as e:
            yield f"[ERROR] Coding failed for {task_id}: {e}"

    async def review(self, task_id: str) -> AsyncIterator[str]:
        """Stream code review for a task.

        Loads task context, builds review prompt, invokes CC review, parses
        final lines for PASS/FAIL status, and yields completion summary.

        Args:
            task_id: Task identifier (e.g., "TASK-001").

        Yields:
            Output lines from CC code review.
            Final line is: "REVIEW: PASS" or "REVIEW: FAIL [reason]"
        """
        try:
            # Load task
            task = self.task_mgr.load(task_id)

            # Build prompt
            prompt = build_review_prompt(task, self.config)

            # Invoke streaming
            args = [
                "--dangerously-skip-permissions",
                "-p",
                prompt,
                "--allowedTools",
                "Read",
            ]

            lines = []
            async for line in self.invoker.invoke_streaming(
                tool="cc",
                args=args,
                cwd=self.project_root,
                timeout=600.0,
            ):
                cleaned = line.rstrip("\n")
                yield cleaned
                lines.append(cleaned)

            # Use structured marker from prompt template; fall back to INCONCLUSIVE
            # rather than a heuristic that can misfire on words like "not a failure"
            review_text = "\n".join(lines)
            match = re.search(
                r"## Review Result:\s*(PASS|FAIL)", review_text, re.IGNORECASE
            )
            if match:
                verdict = match.group(1).upper()
                if verdict == "PASS":
                    self.task_mgr.update_status(
                        task_id,
                        "IN_REVIEW",
                        "CC review passed",
                    )
                else:
                    self.task_mgr.update_status(
                        task_id,
                        "IN_REVIEW",
                        "CC review flagged issues",
                    )
                yield f"--- REVIEW: {verdict} ---"
            else:
                yield "--- REVIEW: INCONCLUSIVE (no structured verdict found) ---"

        except TaskNotFoundError:
            yield f"[ERROR] Task {task_id} not found"
        except Exception as e:
            yield f"[ERROR] Review failed for {task_id}: {e}"

    async def approve_plan(self, task_ids: list[str] | None = None) -> list[str]:
        """Approve draft tasks (DRAFT → TODO status).

        If task_ids is None, approves all DRAFT tasks.

        Args:
            task_ids: List of task IDs to approve, or None for all DRAFTs.

        Returns:
            List of approved task IDs.
        """
        try:
            if task_ids is None:
                # Find all DRAFT tasks
                all_tasks = self.task_mgr.load_all()
                task_ids = [t.id for t in all_tasks if t.status == "DRAFT"]

            approved = []
            for task_id in task_ids:
                try:
                    self.task_mgr.update_status(task_id, "TODO", "Plan approved")
                    approved.append(task_id)
                except Exception:
                    pass  # skip individual failures

            return approved

        except Exception:
            return []

    async def reject_plan(self, task_ids: list[str] | None = None) -> None:
        """Reject draft tasks (delete them).

        If task_ids is None, deletes all DRAFT tasks.

        Args:
            task_ids: List of task IDs to reject, or None for all DRAFTs.
        """
        try:
            if task_ids is None:
                # Find all DRAFT tasks
                all_tasks = self.task_mgr.load_all()
                task_ids = [t.id for t in all_tasks if t.status == "DRAFT"]

            for task_id in task_ids:
                try:
                    self.task_mgr.delete(task_id)
                except Exception:
                    pass  # skip individual failures

        except Exception:
            pass  # swallow high-level failures
