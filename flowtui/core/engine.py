"""Orchestrator — coordinates AI tool invocations for plan/code/review commands."""

import re
import time
import warnings
from dataclasses import dataclass, field
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
from flowtui.core.git_ops import MergeResult


@dataclass
class PhaseResult:
    """Result of a single phase in task execution."""

    phase: str  # "impl" | "impl_1" | "impl_2" | "review" | "verify_ac"
    status: str  # "pass" | "fail" | "skip"
    output: str = ""  # Last 2000 chars of phase output
    duration_sec: float = 0.0


@dataclass
class TaskResult:
    """Result of running a task with retry logic."""

    task_id: str
    status: str  # "done" | "blocked"
    retry_count: int = 0
    phases: list[PhaseResult] = field(default_factory=list)
    branch: str = ""
    diff_stat: str = ""
    total_duration_sec: float = 0.0

    def report_table(self) -> str:
        """Return formatted table string for display in TUI."""
        lines = [
            f"Task {self.task_id}: {self.status.upper()} (retries: {self.retry_count})"
        ]
        lines.append(f"Branch: {self.branch} | Duration: {self.total_duration_sec:.1f}s")
        lines.append(f"Diff: {self.diff_stat}")
        lines.append("")
        lines.append(f"{'Phase':<15} {'Status':<10} {'Duration':>10}")
        lines.append("-" * 37)
        for p in self.phases:
            lines.append(
                f"{p.phase:<15} {p.status:<10} {p.duration_sec:>9.1f}s"
            )
        return "\n".join(lines)


@dataclass
class SprintResult:
    """Result of running a full sprint with multiple tasks and circuit breaker."""

    completed: int = 0  # number of tasks with "done" status
    blocked: int = 0  # number of tasks with "blocked" status
    total_attempted: int = 0  # total number of attempted tasks
    circuit_breaker: bool = False  # True if sprint halted due to circuit breaker
    task_results: list[TaskResult] = field(default_factory=list)
    total_duration_sec: float = 0.0

    def summary_table(self) -> str:
        """Return formatted summary table for TUI display."""
        lines = [
            f"Sprint Summary: {self.completed}/{self.total_attempted} completed",
        ]
        if self.circuit_breaker:
            lines.append("⚠ CIRCUIT BREAKER: Sprint halted after 3 consecutive failures")
        lines.append("")
        lines.append(f"{'Task':<15} {'Status':<10} {'Retries':<10} {'Duration':>10}")
        lines.append("-" * 47)
        for r in self.task_results:
            lines.append(
                f"{r.task_id:<15} {r.status:<10} {r.retry_count:<10} {r.total_duration_sec:>9.1f}s"
            )
        lines.append("")
        lines.append(f"Total: {self.total_duration_sec:.1f}s")
        return "\n".join(lines)


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
        git_ops=None,
        test_runner=None,
    ):
        """Initialize Orchestrator with dependencies.

        Args:
            invoker: CLI invoker (SubprocessInvoker or MockCLI for tests).
            task_mgr: TaskManager for task persistence.
            config: FlowTUI configuration.
            project_root: Project root directory.
            git_ops: Optional GitOps instance for branch management (T3.1).
            test_runner: Optional TestRunner instance for test execution (T3.2).
        """
        self.invoker = invoker
        self.task_mgr = task_mgr
        self.config = config
        self.project_root = project_root
        self.git_ops = git_ops
        self.test_runner = test_runner

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

    async def run_task(self, task_id: str) -> TaskResult:
        """Execute a task with implementation, review, and verification phases.

        Manages git branches, runs tests, and persists task status throughout.
        Implements retry logic (max 2 retries) with rollback on implementation failure.

        Phase flow:
        1. Git setup (create branch, get pre_hash)
        2. Implementation (invoke CC with task context, streaming)
        3. Tests (if test_runner available)
        4. Review (invoke CC review, collect output)
        5. Verify AC (run tests again to confirm acceptance criteria)
        6. Checkpoint (git commit on success)
        7. Context (write sprint.md)

        Args:
            task_id: Task identifier (e.g., "TASK-001").

        Returns:
            TaskResult with status ("done" or "blocked"), phases, retry count, timing.
        """
        MAX_RETRY = 2
        start_time = time.time()
        branch_name = f"flowtui/{task_id}"

        # 1. Git setup
        pre_hash = None
        if self.git_ops:
            try:
                pre_hash = await self.git_ops.get_head_hash()
                await self.git_ops.create_branch(branch_name)
            except Exception as e:
                warnings.warn(f"Git setup failed: {e}")

        # 2. Update status → IN_PROGRESS
        try:
            self.task_mgr.update_status(task_id, "IN_PROGRESS")
        except Exception:
            pass

        # Load task for context
        try:
            task = self.task_mgr.load(task_id)
        except TaskNotFoundError:
            return TaskResult(
                task_id=task_id,
                status="blocked",
                phases=[PhaseResult(phase="load", status="fail", output="Task not found")],
                branch=branch_name,
                total_duration_sec=time.time() - start_time,
            )

        phases = []
        retry_count = 0
        final_status = "blocked"
        diff_str = ""
        impl_passed = False
        impl_text = ""

        # 3+4. Impl + tests with retry
        for attempt in range(MAX_RETRY + 1):  # 0, 1, 2
            t0 = time.time()
            impl_output = []
            prompt = self._build_impl_prompt(task)

            try:
                # Invoke CC implementation (streaming)
                async for line in self.invoker.invoke_streaming(
                    tool="cc",
                    args=[
                        "--dangerously-skip-permissions",
                        "-p",
                        prompt,
                    ],
                    cwd=self.project_root,
                    timeout=600.0,
                ):
                    impl_output.append(line)

                impl_text = "".join(impl_output)

                # Get diff stat (uncommitted changes vs HEAD)
                if self.git_ops:
                    try:
                        ds = await self.git_ops.diff_stat()
                        diff_str = ds.raw
                    except Exception:
                        diff_str = "(diff failed)"

                # Run tests
                test_result = None
                if self.test_runner:
                    try:
                        test_result = await self.test_runner.run_tests()
                    except Exception as e:
                        test_result = None
                        warnings.warn(f"Test runner failed: {e}")

                # Determine if impl passed (tests passed or skipped)
                impl_passed = test_result is None or test_result.skipped or test_result.passed

                phase_name = f"impl_{attempt}" if attempt > 0 else "impl"
                phases.append(
                    PhaseResult(
                        phase=phase_name,
                        status="pass" if impl_passed else "fail",
                        output=impl_text[-2000:],
                        duration_sec=time.time() - t0,
                    )
                )

                if impl_passed:
                    break

            except (TimeoutError, Exception) as e:
                phase_name = f"impl_{attempt}" if attempt > 0 else "impl"
                phases.append(
                    PhaseResult(
                        phase=phase_name,
                        status="fail",
                        output=f"Error: {str(e)[-500:]}",
                        duration_sec=time.time() - t0,
                    )
                )

            # If impl failed and we have retries left, rollback
            if not impl_passed and attempt < MAX_RETRY:
                retry_count += 1
                if self.git_ops and pre_hash:
                    try:
                        await self.git_ops.rollback(pre_hash)
                    except Exception as e:
                        warnings.warn(f"Rollback failed: {e}")

        # Check if we exhausted retries
        if not impl_passed:
            try:
                self.task_mgr.update_status(task_id, "BLOCKED", "Implementation failed after retries")
            except Exception:
                pass
            try:
                from flowtui.core.context_writer import write_sprint_context
                all_tasks = self.task_mgr.load_all()
                write_sprint_context(
                    self.project_root,
                    all_tasks,
                    {},
                    self.config.project.name if self.config else "Unknown",
                    self.config.project.stack if self.config else "Unknown",
                )
            except Exception:
                pass
            return TaskResult(
                task_id=task_id,
                status="blocked",
                retry_count=retry_count,
                phases=phases,
                branch=branch_name,
                diff_stat=diff_str,
                total_duration_sec=time.time() - start_time,
            )

        # 5. Invoke CC review
        t0 = time.time()
        review_prompt = self._build_review_prompt(task, impl_text)
        review_passed = False

        try:
            review_result = await self.invoker.invoke(
                tool="cc",
                args=[
                    "--dangerously-skip-permissions",
                    "-p",
                    review_prompt,
                ],
                cwd=self.project_root,
                timeout=300.0,
            )
            review_passed = bool(re.search(r"## Review Result:\s*PASS", review_result.stdout, re.IGNORECASE))
            phases.append(
                PhaseResult(
                    phase="review",
                    status="pass" if review_passed else "fail",
                    output=review_result.stdout[-2000:],
                    duration_sec=time.time() - t0,
                )
            )
        except Exception as e:
            phases.append(
                PhaseResult(
                    phase="review",
                    status="fail",
                    output=str(e)[-500:],
                    duration_sec=time.time() - t0,
                )
            )

        # 6. Verify AC — run tests again
        ac_passed = True
        if self.test_runner:
            t0 = time.time()
            try:
                ac_result = await self.test_runner.run_tests()
                ac_passed = ac_result.skipped or ac_result.passed
                phases.append(
                    PhaseResult(
                        phase="verify_ac",
                        status="pass" if ac_passed else "fail",
                        output=ac_result.output[-1000:],
                        duration_sec=time.time() - t0,
                    )
                )
            except Exception as e:
                phases.append(
                    PhaseResult(
                        phase="verify_ac",
                        status="fail",
                        output=str(e)[-500:],
                        duration_sec=time.time() - t0,
                    )
                )
                ac_passed = False

        # 7. Final status (review FAIL doesn't block; AC FAIL does)
        final_status = "done" if ac_passed else "blocked"
        try:
            self.task_mgr.update_status(task_id, final_status.upper())
        except Exception:
            pass

        # 8. Checkpoint on success
        if self.git_ops and final_status == "done":
            try:
                await self.git_ops.checkpoint(f"feat: complete {task_id}")
                # After checkpoint, get diff relative to base to show what branch changed
                if pre_hash:
                    try:
                        ds = await self.git_ops.diff_stat(base=pre_hash)
                        diff_str = ds.raw
                    except Exception:
                        pass  # keep previous diff_str if this fails
            except Exception as e:
                warnings.warn(f"Checkpoint failed: {e}")

        # 9. Write sprint context
        try:
            from flowtui.core.context_writer import write_sprint_context
            all_tasks = self.task_mgr.load_all()
            write_sprint_context(
                self.project_root,
                all_tasks,
                {},
                self.config.project.name if self.config else "Unknown",
                self.config.project.stack if self.config else "Unknown",
            )
        except Exception:
            pass

        return TaskResult(
            task_id=task_id,
            status=final_status,
            retry_count=retry_count,
            phases=phases,
            branch=branch_name,
            diff_stat=diff_str,
            total_duration_sec=time.time() - start_time,
        )

    def _build_impl_prompt(self, task: Task) -> str:
        """Build implementation prompt from task context.

        Args:
            task: Task object with requirements and constraints.

        Returns:
            Prompt string for CC implementation.
        """
        files_str = ", ".join(task.files_to_modify) if task.files_to_modify else "see task file"
        ac_str = "\n".join(f"- {ac}" for ac in task.acceptance_criteria) if task.acceptance_criteria else "see task file"
        req_str = "\n".join(f"- {r}" for r in task.requirements) if task.requirements else "see task file"

        return (
            f"Implement the following task:\n\n"
            f"Task ID: {task.id}\n"
            f"Title: {task.title}\n"
            f"Description:\n{task.context}\n\n"
            f"Files to modify:\n{files_str}\n\n"
            f"Requirements:\n{req_str}\n\n"
            f"Acceptance criteria:\n{ac_str}\n\n"
            f"Implement all required changes and ensure all acceptance criteria are met."
        )

    def _build_review_prompt(self, task: Task, impl_output: str) -> str:
        """Build review prompt from task and implementation.

        Args:
            task: Task object.
            impl_output: Implementation output from CC.

        Returns:
            Prompt string for CC review.
        """
        return (
            f"Review the implementation of task {task.id}: {task.title}\n\n"
            f"Implementation output (last 1000 chars):\n{impl_output[-1000:]}\n\n"
            f"Task acceptance criteria:\n"
            f"{chr(10).join(f'- {ac}' for ac in task.acceptance_criteria) if task.acceptance_criteria else 'See task file'}\n\n"
            f"Check if the implementation meets all acceptance criteria.\n"
            f"Respond with:\n"
            f"## Review Result: PASS\n"
            f"if criteria are met, or\n"
            f"## Review Result: FAIL\n"
            f"followed by explanation of what's missing."
        )

    async def run_sprint(self) -> SprintResult:
        """Run all TODO tasks sequentially by priority with circuit breaker.

        Executes tasks in priority order (lower number = higher priority).
        Implements circuit breaker: stops after 3 consecutive failures.

        Returns:
            SprintResult with completed/blocked counts, task results, and duration.
        """
        start_time = time.time()

        # Get all TODO tasks, sorted by priority
        all_tasks = self.task_mgr.load_all()
        todo_tasks = [t for t in all_tasks if t.status == "TODO"]
        todo_tasks.sort(key=lambda t: getattr(t, "priority", 999))

        consecutive_fails = 0
        CIRCUIT_BREAKER_THRESHOLD = 3
        task_results = []
        completed = 0
        blocked = 0
        circuit_breaker_triggered = False

        for task in todo_tasks:
            result = await self.run_task(task.id)
            task_results.append(result)

            if result.status == "done":
                completed += 1
                consecutive_fails = 0  # reset on success
            else:
                blocked += 1
                consecutive_fails += 1

            # Circuit breaker check
            if consecutive_fails >= CIRCUIT_BREAKER_THRESHOLD:
                circuit_breaker_triggered = True
                break

        return SprintResult(
            completed=completed,
            blocked=blocked,
            total_attempted=len(task_results),
            circuit_breaker=circuit_breaker_triggered,
            task_results=task_results,
            total_duration_sec=time.time() - start_time,
        )

    async def merge(
        self, task_id: str | None = None
    ) -> MergeResult | list[MergeResult]:
        """Merge done task branches to develop branch.

        If task_id is provided: merge that single task's branch.
        If task_id is None: merge all DONE tasks' branches.

        Args:
            task_id: Optional task ID to merge. If None, merges all DONE tasks.

        Returns:
            MergeResult for single task, or list[MergeResult] for all tasks.

        Raises:
            RuntimeError: If GitOps is not configured.
            ValueError: If task_id is provided but task is not in DONE status.
        """
        if not self.git_ops:
            raise RuntimeError("GitOps not configured — cannot merge")

        # Determine target branch (default: "develop")
        target = "develop"
        try:
            if self.config and hasattr(self.config, "git"):
                target = getattr(self.config.git, "develop_branch", "develop")
        except Exception:
            pass

        if task_id is not None:
            # Merge single task
            task = self.task_mgr.load(task_id)
            if task.status != "DONE":
                raise ValueError(
                    f"Task {task_id} is not done (status: {task.status})"
                )
            branch = f"flowtui/{task_id}"
            return await self.git_ops.merge_to(target, branch)
        else:
            # Merge all DONE tasks
            all_tasks = self.task_mgr.load_all()
            done_tasks = [t for t in all_tasks if t.status == "DONE"]
            results = []
            for task in done_tasks:
                branch = f"flowtui/{task.id}"
                try:
                    result = await self.git_ops.merge_to(target, branch)
                    results.append(result)
                    if not result.success:
                        break  # stop on first conflict
                except Exception as e:
                    results.append(MergeResult(success=False, message=str(e)))
                    break
            return results
