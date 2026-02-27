"""FlowTUI configuration schema."""
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    model_config = {"frozen": True}
    name: str
    stack: str
    description: str = ""


class ToolConfig(BaseModel):
    model_config = {"frozen": True}
    command: str
    flags: str = ""
    planning_prompt: str = ""
    coding_prompt: str = ""
    review_prompt: str = ""
    direct_flags: list[str] = Field(default_factory=list)


class LimitsConfig(BaseModel):
    model_config = {"frozen": True}
    claude_daily_budget: int = 15
    codex_daily_budget: int = 5
    gemini_daily_budget: int = 30


class StartupConfig(BaseModel):
    model_config = {"frozen": True}
    auto_update: bool = True
    update_timeout: int = 60
    skip_if_recent: int = 3600  # seconds


class FlowTUIConfig(BaseModel):
    model_config = {"frozen": True}
    project: ProjectConfig
    tools: dict[str, ToolConfig] = Field(default_factory=dict)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    startup: StartupConfig = Field(default_factory=StartupConfig)
