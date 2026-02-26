"""FlowTUI configuration loader."""
import tomllib
from pathlib import Path

from .schema import FlowTUIConfig


class ConfigNotFoundError(FileNotFoundError):
    """Raised when .flowtui/config.toml is not found."""


def load_config(project_root: Path) -> FlowTUIConfig:
    """Load and validate FlowTUI config from .flowtui/config.toml.

    Raises ConfigNotFoundError if config file doesn't exist.
    Raises pydantic.ValidationError if config is invalid.
    """
    config_path = project_root / ".flowtui" / "config.toml"
    if not config_path.exists():
        raise ConfigNotFoundError(
            f"No .flowtui/config.toml found in {project_root}. "
            "Run 'flowtui init' to create a new project."
        )
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)
    return FlowTUIConfig(**raw)


def find_project_root(start: Path | None = None) -> Path:
    """Walk up directory tree to find .flowtui/config.toml.

    Returns the directory containing .flowtui/, or raises ConfigNotFoundError.
    """
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if (directory / ".flowtui" / "config.toml").exists():
            return directory
    raise ConfigNotFoundError(
        "Could not find .flowtui/config.toml in current directory or any parent. "
        "Run 'flowtui init' to create a new project."
    )
