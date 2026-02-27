"""FlowTUI CLI entry point."""
from pathlib import Path

import click

from flowtui.app import FlowTUIApp


@click.group(invoke_without_command=True)
@click.option("--project", type=click.Path(exists=False), default=None, help="Path to project root")
@click.option("--dry-run", is_flag=True, default=False, help="Preview actions without executing")
@click.pass_context
def main(ctx: click.Context, project: str | None, dry_run: bool) -> None:
    """FlowTUI — Terminal Development Orchestrator."""
    ctx.ensure_object(dict)
    ctx.obj["project"] = project
    ctx.obj["dry_run"] = dry_run

    if ctx.invoked_subcommand is None:
        # Default: run TUI
        project_root = Path(project) if project else None
        app = FlowTUIApp(project_root=project_root, dry_run=dry_run)
        app.run()


@main.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Scaffold a new FlowTUI project."""
    from flowtui.scaffold import AlreadyInitializedError, scaffold_project

    root = Path(ctx.obj.get("project") or ".")
    try:
        scaffold_project(root)
        click.echo(f"FlowTUI initialized in {root}")
    except AlreadyInitializedError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@main.command()
@click.argument("command")
@click.pass_context
def execute(ctx: click.Context, command: str) -> None:
    """Execute a command headlessly (without TUI).

    Supports: plan <desc>, run <task_id>, run sprint, merge [task_id], stats.
    """
    import asyncio
    from flowtui.config.loader import load_config, find_project_root
    from flowtui.core.invoker import SubprocessInvoker
    from flowtui.core.engine import Orchestrator
    from flowtui.core.task_manager import TaskManager

    project_path = ctx.obj.get("project") if ctx.obj else None
    project_root = Path(project_path) if project_path else find_project_root()

    try:
        config = load_config(project_root)
    except Exception as e:
        click.echo(f"Warning: failed to load config: {e}", err=True)
        config = None

    invoker = SubprocessInvoker()
    task_manager = TaskManager(project_root / "docs" / "tasks")
    orchestrator = Orchestrator(invoker, task_manager, config, project_root)

    async def run_headless() -> None:
        """Parse and execute headless command."""
        parts = command.strip().split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "plan":
            if not arg:
                click.echo("Error: plan requires a description", err=True)
                raise SystemExit(1)
            async for line in orchestrator.plan(arg):
                click.echo(line)

        elif cmd == "run":
            if arg.lower() == "sprint":
                result = await orchestrator.run_sprint()
                click.echo(result.summary_table())
            elif arg:
                result = await orchestrator.run_task(arg.upper())
                click.echo(result.report_table())
            else:
                click.echo("Error: run requires <task_id> or 'sprint'", err=True)
                raise SystemExit(1)

        elif cmd == "merge":
            if arg:
                result = await orchestrator.merge(arg.upper())
                if isinstance(result, list):
                    for r in result:
                        status = "OK" if r.success else f"CONFLICT: {', '.join(r.conflicts)}"
                        click.echo(status)
                else:
                    status = "OK" if result.success else f"CONFLICT: {', '.join(result.conflicts)}"
                    click.echo(status)
            else:
                # Merge all DONE tasks
                result = await orchestrator.merge()
                if isinstance(result, list):
                    for r in result:
                        status = "OK" if r.success else f"CONFLICT: {', '.join(r.conflicts)}"
                        click.echo(status)
                else:
                    status = "OK" if result.success else f"CONFLICT: {', '.join(result.conflicts)}"
                    click.echo(status)

        elif cmd == "stats":
            from flowtui.analytics.stats import StatsCalculator
            calc = StatsCalculator(project_root)
            snap = calc.snapshot()
            click.echo(calc.format_dashboard(snap))

        else:
            click.echo(f"Error: unknown command '{cmd}'", err=True)
            click.echo("Supported: plan <desc>, run <task_id>, run sprint, merge [task_id], stats", err=True)
            raise SystemExit(1)

    try:
        asyncio.run(run_headless())
    except KeyboardInterrupt:
        click.echo("\nAborted by user", err=True)
        raise SystemExit(130)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
