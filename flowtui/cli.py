"""FlowTUI CLI entry point."""
import click


@click.group(invoke_without_command=True)
@click.option("--project", default=None, help="Path to project root")
@click.pass_context
def main(ctx: click.Context, project: str | None) -> None:
    """FlowTUI — Terminal Development Orchestrator."""
    if ctx.invoked_subcommand is None:
        from pathlib import Path
        from flowtui.app import FlowTUIApp
        app = FlowTUIApp()
        app.run()


@main.command()
def init() -> None:
    """Scaffold a new FlowTUI project."""
    click.echo("flowtui init — not yet implemented")


@main.command()
@click.argument("command")
def exec(command: str) -> None:
    """Run a command headlessly (without TUI)."""
    click.echo(f"flowtui exec '{command}' — not yet implemented")
