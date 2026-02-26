"""FlowTUI CLI entry point."""
from pathlib import Path

import click

from flowtui.app import FlowTUIApp


@click.group(invoke_without_command=True)
@click.option("--project", type=click.Path(exists=False), default=None, help="Path to project root")
@click.pass_context
def main(ctx: click.Context, project: str | None) -> None:
    """FlowTUI — Terminal Development Orchestrator."""
    ctx.ensure_object(dict)
    ctx.obj["project"] = project

    if ctx.invoked_subcommand is None:
        # Default: run TUI
        project_root = Path(project) if project else None
        app = FlowTUIApp(project_root=project_root)
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
