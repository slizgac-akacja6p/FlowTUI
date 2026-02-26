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
    """Execute a command headlessly (without TUI)."""
    click.echo(f"flowtui execute '{command}' — not yet implemented")
