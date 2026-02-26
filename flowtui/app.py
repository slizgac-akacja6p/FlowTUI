"""FlowTUI Textual application — main TUI entrypoint."""
import asyncio
import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Input

from flowtui.tui.widgets import (
    TaskPanel,
    LimitsPanel,
    SprintPanel,
    TerminalPanel,
)


class FlowTUIApp(App):
    """Main FlowTUI TUI application.

    4-panel layout:
    - Task panel (70% width, left)
    - Limits & Sprint panels (30% width, stacked right)
    - Terminal panel (scrollable logs, bottom)
    - Command input (at very bottom)

    Styling via flowtui/tui/styles.tcss.
    """

    CSS_PATH = Path(__file__).parent / "tui/styles.tcss"

    DIRECT_TOOLS = {
        "cc": {"command": "claude", "flags": ["-p", "--allowedTools", "Edit,Bash,Read"]},
        "codex": {"command": "codex", "flags": ["--full-auto", "-q"]},
        "gemini": {"command": "gemini", "flags": ["-p"]},
    }

    SESSION_TOOLS = {
        "cc": ["claude"],        # interactive CC session
        "gemini": ["gemini"],    # interactive Gemini session
    }

    def __init__(self, *args, project_root: Path | None = None, dry_run: bool = False, **kwargs):
        """Initialize FlowTUIApp with project root and dry-run mode.

        Args:
            project_root: Root directory of the project (default: cwd)
            dry_run: If True, preview actions without executing (default: False)
        """
        super().__init__(*args, **kwargs)
        self.project_root = project_root or Path.cwd()
        self.dry_run = dry_run

    async def on_mount(self) -> None:
        """Load project config on startup to populate project name and stack."""
        try:
            from flowtui.config.loader import load_config
            config = load_config(self.project_root)
            self._project_name = config.project.name
            self._stack = config.project.stack
        except Exception:
            # Config may not exist yet (e.g. fresh project before flowtui init)
            self._project_name = self.project_root.name
            self._stack = "unknown"

    def compose(self) -> ComposeResult:
        """Compose main layout with header, panels, and footer."""
        yield Header()

        with Horizontal(id="main-content"):
            yield TaskPanel(id="task-panel")

            with Vertical(id="right-panel"):
                yield LimitsPanel(id="limits-panel")
                yield SprintPanel(id="sprint-panel")

        yield TerminalPanel(id="terminal-panel")
        yield Input(placeholder="Command...", id="cmd-input")

        yield Footer()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input submission.

        Routes to:
        - Orchestrator methods (plan/code/review)
        - _session_invoke if cmd in SESSION_TOOLS and no prompt
        - _direct_invoke if cmd in DIRECT_TOOLS and has prompt
        - Usage hint if valid cmd but wrong args
        """
        raw = event.value.strip()
        event.input.clear()

        if not raw:
            return

        # Parse: "cc <prompt>", "codex <prompt>", "gemini <prompt>", etc.
        parts = raw.split(" ", 1)
        cmd = parts[0].lower()
        prompt = parts[1] if len(parts) > 1 else ""

        terminal = self.query_one("#terminal-panel", TerminalPanel)

        # ─────────────────────────────────────────────────────────────────────
        # Orchestrator commands: plan, code, review
        # ─────────────────────────────────────────────────────────────────────
        if cmd == "plan" and prompt.startswith("--approve"):
            asyncio.create_task(self._approve_plan())
        elif cmd == "plan" and prompt.startswith("--reject"):
            asyncio.create_task(self._reject_plan())
        elif cmd == "plan" and prompt:
            asyncio.create_task(self._run_plan(prompt))
        elif cmd == "code" and prompt:
            asyncio.create_task(self._run_code(prompt))
        elif cmd == "review" and prompt:
            asyncio.create_task(self._run_review(prompt))
        # ─────────────────────────────────────────────────────────────────────
        # Chat command (alias for session invoke)
        # ─────────────────────────────────────────────────────────────────────
        elif cmd == "chat" and (not prompt or prompt in ("claude", "cc")):
            await self._session_invoke("cc")
        # ─────────────────────────────────────────────────────────────────────
        # Status command
        # ─────────────────────────────────────────────────────────────────────
        elif cmd == "status":
            asyncio.create_task(self._show_status())
        # ─────────────────────────────────────────────────────────────────────
        # Direct and session mode for tools
        # ─────────────────────────────────────────────────────────────────────
        elif cmd in self.SESSION_TOOLS and not prompt:
            await self._session_invoke(cmd)
        elif cmd in self.DIRECT_TOOLS and prompt:
            await self._direct_invoke(cmd, prompt)
        elif cmd in self.DIRECT_TOOLS or cmd in self.SESSION_TOOLS:
            # Valid command but incorrect usage
            terminal.write_line(
                f"Usage: {cmd} \"<prompt>\"  (direct) or  {cmd}  (session mode)"
            )
        else:
            terminal.write_line(f"Unknown command: {cmd}")

    async def _run_plan(self, description: str) -> None:
        """Run plan command, stream to TerminalPanel.

        Args:
            description: Feature description to plan.
        """
        terminal = self.query_one("#terminal-panel", TerminalPanel)
        terminal.write_line(f"Planning: {description}")

        if self.dry_run:
            terminal.write_line("--- DRY RUN (no execution) ---")
            terminal.write_line(f"Would plan: {description}")
            terminal.write_line("--- END DRY RUN ---")
            return

        try:
            from flowtui.config.loader import load_config
            from flowtui.core.invoker import SubprocessInvoker
            from flowtui.core.task_manager import TaskManager
            from flowtui.core.engine import Orchestrator

            config = load_config(self.project_root)
            tasks_dir = self.project_root / "docs" / "tasks"
            task_mgr = TaskManager(tasks_dir)
            invoker = SubprocessInvoker()
            orchestrator = Orchestrator(invoker, task_mgr, config, self.project_root)

            async for line in orchestrator.plan(description):
                terminal.write_line(line)

        except Exception as e:
            terminal.write_line(f"[ERROR] {e}")

    async def _run_code(self, task_id: str) -> None:
        """Run code command for a task.

        Args:
            task_id: Task identifier (e.g., "TASK-001").
        """
        terminal = self.query_one("#terminal-panel", TerminalPanel)
        terminal.write_line(f"Coding: {task_id}")

        if self.dry_run:
            terminal.write_line("--- DRY RUN (no execution) ---")
            terminal.write_line(f"Would code: {task_id}")
            terminal.write_line("--- END DRY RUN ---")
            return

        try:
            from flowtui.config.loader import load_config
            from flowtui.core.invoker import SubprocessInvoker
            from flowtui.core.task_manager import TaskManager
            from flowtui.core.engine import Orchestrator

            config = load_config(self.project_root)
            tasks_dir = self.project_root / "docs" / "tasks"
            task_mgr = TaskManager(tasks_dir)
            invoker = SubprocessInvoker()
            orchestrator = Orchestrator(invoker, task_mgr, config, self.project_root)

            async for line in orchestrator.code(task_id):
                terminal.write_line(line)

        except Exception as e:
            terminal.write_line(f"[ERROR] {e}")

    async def _run_review(self, task_id: str) -> None:
        """Run review command for a task.

        Args:
            task_id: Task identifier (e.g., "TASK-001").
        """
        terminal = self.query_one("#terminal-panel", TerminalPanel)
        terminal.write_line(f"Reviewing: {task_id}")

        if self.dry_run:
            terminal.write_line("--- DRY RUN (no execution) ---")
            terminal.write_line(f"Would review: {task_id}")
            terminal.write_line("--- END DRY RUN ---")
            return

        try:
            from flowtui.config.loader import load_config
            from flowtui.core.invoker import SubprocessInvoker
            from flowtui.core.task_manager import TaskManager
            from flowtui.core.engine import Orchestrator

            config = load_config(self.project_root)
            tasks_dir = self.project_root / "docs" / "tasks"
            task_mgr = TaskManager(tasks_dir)
            invoker = SubprocessInvoker()
            orchestrator = Orchestrator(invoker, task_mgr, config, self.project_root)

            async for line in orchestrator.review(task_id):
                terminal.write_line(line)

        except Exception as e:
            terminal.write_line(f"[ERROR] {e}")

    async def _approve_plan(self) -> None:
        """Approve all draft tasks (DRAFT → TODO)."""
        terminal = self.query_one("#terminal-panel", TerminalPanel)
        terminal.write_line("Approving all draft tasks...")

        if self.dry_run:
            terminal.write_line("--- DRY RUN (no execution) ---")
            terminal.write_line("Would approve all DRAFT tasks")
            terminal.write_line("--- END DRY RUN ---")
            return

        try:
            from flowtui.config.loader import load_config
            from flowtui.core.invoker import SubprocessInvoker
            from flowtui.core.task_manager import TaskManager
            from flowtui.core.engine import Orchestrator

            config = load_config(self.project_root)
            tasks_dir = self.project_root / "docs" / "tasks"
            task_mgr = TaskManager(tasks_dir)
            invoker = SubprocessInvoker()
            orchestrator = Orchestrator(invoker, task_mgr, config, self.project_root)

            approved = await orchestrator.approve_plan()
            if approved:
                terminal.write_line(f"Approved {len(approved)} task(s): {', '.join(approved)}")
            else:
                terminal.write_line("No DRAFT tasks to approve")

        except Exception as e:
            terminal.write_line(f"[ERROR] {e}")

    async def _reject_plan(self) -> None:
        """Reject all draft tasks (delete them)."""
        terminal = self.query_one("#terminal-panel", TerminalPanel)
        terminal.write_line("Rejecting all draft tasks...")

        if self.dry_run:
            terminal.write_line("--- DRY RUN (no execution) ---")
            terminal.write_line("Would reject all DRAFT tasks")
            terminal.write_line("--- END DRY RUN ---")
            return

        try:
            from flowtui.config.loader import load_config
            from flowtui.core.invoker import SubprocessInvoker
            from flowtui.core.task_manager import TaskManager
            from flowtui.core.engine import Orchestrator

            config = load_config(self.project_root)
            tasks_dir = self.project_root / "docs" / "tasks"
            task_mgr = TaskManager(tasks_dir)
            invoker = SubprocessInvoker()
            orchestrator = Orchestrator(invoker, task_mgr, config, self.project_root)

            await orchestrator.reject_plan()
            terminal.write_line("All draft tasks rejected")

        except Exception as e:
            terminal.write_line(f"[ERROR] {e}")

    async def _show_status(self) -> None:
        """Display sprint status summary."""
        terminal = self.query_one("#terminal-panel", TerminalPanel)

        try:
            from flowtui.core.task_manager import TaskManager

            tasks_dir = self.project_root / "docs" / "tasks"
            task_mgr = TaskManager(tasks_dir)

            all_tasks = task_mgr.load_all()
            by_status = {}
            for task in all_tasks:
                by_status.setdefault(task.status, []).append(task.id)

            terminal.write_line("=== Sprint Status ===")
            for status in ["DRAFT", "TODO", "IN_PROGRESS", "IN_REVIEW", "DONE", "BLOCKED"]:
                count = len(by_status.get(status, []))
                if count > 0 or status in ("TODO", "IN_PROGRESS"):
                    ids = ", ".join(by_status.get(status, []))
                    terminal.write_line(f"{status}: {count} task(s) {ids}")

            total = len(all_tasks)
            done = len(by_status.get("DONE", []))
            terminal.write_line(f"\nTotal: {done}/{total} done ({100*done//total if total > 0 else 0}%)")

        except Exception as e:
            terminal.write_line(f"[ERROR] {e}")

    async def _direct_invoke(self, tool_key: str, prompt: str) -> None:
        """Run a direct passthrough subprocess call.

        Streams subprocess output line-by-line to terminal, logs to analytics,
        and increments call counter. Errors are logged but do not crash TUI.

        In dry-run mode, preview the action without executing.
        """
        import time
        from flowtui.analytics.storage import AnalyticsStorage

        tool_info = self.DIRECT_TOOLS[tool_key]
        cmd = [tool_info["command"]] + tool_info["flags"] + [prompt]

        terminal = self.query_one("#terminal-panel", TerminalPanel)

        if self.dry_run:
            terminal.write_line("--- DRY RUN (no execution) ---")
            terminal.write_line(f"Tool: {tool_key}")
            terminal.write_line(f"Command: {' '.join(cmd)}")
            terminal.write_line(f"Working dir: {self.project_root}")
            preview_prompt = prompt[:100] + ("..." if len(prompt) > 100 else "")
            terminal.write_line(f"Prompt ({len(prompt)} chars): {preview_prompt}")
            token_estimate = len(prompt.split())
            terminal.write_line(f"Est. tokens: ~{token_estimate}")
            terminal.write_line("--- END DRY RUN ---")
            return

        terminal.write_line(f">>> {tool_key}: {prompt[:60]}...")

        start = time.monotonic()
        exit_code = -1

        try:
            # Strip CLAUDECODE so nested invocations work correctly from TUI
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.project_root,
                env=env,
            )

            # Stream output line by line
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                terminal.write_line(line.decode("utf-8", errors="replace").rstrip())

            await proc.wait()
            exit_code = proc.returncode

        except FileNotFoundError:
            terminal.write_line(f"[ERROR] {tool_info['command']} not found in PATH")
        except Exception as e:
            terminal.write_line(f"[ERROR] {e}")

        wall_time = time.monotonic() - start
        terminal.write_line(f"--- exit {exit_code} ({wall_time:.1f}s) ---")

        # Log to analytics
        try:
            data_dir = self.project_root / ".flowtui"
            if data_dir.exists():
                storage = AnalyticsStorage(data_dir)
                storage.append({
                    "tool": tool_key,
                    "action": "direct",
                    "prompt": prompt[:200],
                    "exit_code": exit_code,
                    "duration_sec": wall_time,
                })
        except Exception:
            pass  # analytics failure must not break UX

        # Update limits counter
        try:
            limits = self.query_one("#limits-panel", LimitsPanel)
            limits.increment_counter()
        except Exception:
            pass

    async def _session_invoke(self, tool_key: str) -> None:
        """Open interactive session via app.suspend().

        Suspends TUI, runs tool in full terminal, writes sprint context beforehand.
        Logs session to analytics and updates limits counter on return.

        In dry-run mode, preview the session command without opening it.

        Args:
            tool_key: Tool identifier (e.g. "cc", "gemini")
        """
        import subprocess
        import time
        from flowtui.analytics.storage import AnalyticsStorage
        from flowtui.core.context_writer import write_sprint_context

        terminal = self.query_one("#terminal-panel", TerminalPanel)

        cmd = self.SESSION_TOOLS[tool_key]

        if self.dry_run:
            terminal.write_line("--- DRY RUN (no execution) ---")
            terminal.write_line(f"Session tool: {tool_key}")
            terminal.write_line(f"Command: {' '.join(cmd)}")
            terminal.write_line(f"Working dir: {self.project_root}")
            terminal.write_line("--- END DRY RUN ---")
            return

        terminal.write_line(f"Opening {tool_key} session... (exit to return to FlowTUI)")

        start = time.monotonic()
        exit_code = -1

        # Write sprint context before suspend (provides project context to tool)
        try:
            write_sprint_context(
                project_root=self.project_root,
                tasks=[],
                limits={},
                project_name=getattr(self, "_project_name", "Unknown"),
                stack=getattr(self, "_stack", "Unknown"),
            )
        except Exception:
            pass  # context write failure must not block session

        # Suspend TUI and run interactive session in full terminal
        with self.suspend():
            try:
                subprocess.run(cmd, cwd=self.project_root)
            except FileNotFoundError:
                pass  # can't display error while suspended, logged after resume
            except Exception:
                pass

        wall_time = time.monotonic() - start
        terminal.write_line(f"--- {tool_key} session ended ({wall_time:.0f}s) ---")

        # Log to analytics
        try:
            data_dir = self.project_root / ".flowtui"
            if data_dir.exists():
                storage = AnalyticsStorage(data_dir)
                storage.append({
                    "tool": tool_key,
                    "action": "session",
                    "prompt": "(interactive session)",
                    "exit_code": exit_code,
                    "duration_sec": wall_time,
                })
        except Exception:
            pass  # analytics failure must not break UX

        # Update limits counter
        try:
            limits = self.query_one("#limits-panel", LimitsPanel)
            limits.increment_counter()
        except Exception:
            pass
