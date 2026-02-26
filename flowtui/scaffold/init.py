"""Project scaffolding — initialize new FlowTUI projects."""
from __future__ import annotations

from pathlib import Path
from jinja2 import Environment, FileSystemLoader


class AlreadyInitializedError(Exception):
    """Raised when project is already initialized and force=False."""

    pass


def scaffold_project(
    root: Path,
    force: bool = False,
    project_name: str | None = None,
    stack: str | None = None,
) -> None:
    """Initialize FlowTUI project structure.

    Creates .flowtui/, PM/, and docs/ directories with configuration files.

    Args:
        root: Project root directory
        force: If True, overwrite existing .flowtui/
        project_name: Name of the project (default: root directory name)
        stack: Technology stack (default: "Python")

    Raises:
        AlreadyInitializedError: If .flowtui/ exists and force=False
    """
    root = Path(root)
    flowtui_dir = root / ".flowtui"

    # Check if already initialized
    if flowtui_dir.exists() and not force:
        raise AlreadyInitializedError(
            f".flowtui/ already exists in {root}. Use --force to reinitialize."
        )

    # Set defaults
    if project_name is None:
        project_name = root.name
    if stack is None:
        stack = "Python"

    # Create directories
    flowtui_dir.mkdir(parents=True, exist_ok=True)
    (root / "PM").mkdir(exist_ok=True)
    (root / "PM" / "tasks").mkdir(exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "context").mkdir(exist_ok=True)
    (root / "docs" / "plans").mkdir(exist_ok=True)
    (root / "docs" / "test-scenarios").mkdir(exist_ok=True)

    # Load Jinja2 templates
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)))

    # Render and write config.toml
    config_template = env.get_template("config.toml.j2")
    config_content = config_template.render(
        project_name=project_name,
        project_stack=stack,
    )
    (flowtui_dir / "config.toml").write_text(config_content, encoding="utf-8")

    # Render and write routing.toml
    routing_template = env.get_template("routing.toml.j2")
    routing_content = routing_template.render()
    (flowtui_dir / "routing.toml").write_text(routing_content, encoding="utf-8")

    # Render and write CLAUDE.md
    claude_template = env.get_template("CLAUDE.md.j2")
    claude_content = claude_template.render(
        project_name=project_name,
        stack=stack,
    )
    (root / "CLAUDE.md").write_text(claude_content, encoding="utf-8")

    # Render and write AGENTS.md
    agents_template = env.get_template("AGENTS.md.j2")
    agents_content = agents_template.render(
        project_name=project_name,
        stack=stack,
    )
    (root / "AGENTS.md").write_text(agents_content, encoding="utf-8")
