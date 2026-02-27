# FlowTUI — Roadmap

## v1.0 (aktualny)
AI CLI orchestrator z Claude Code jako jedynym narzędziem.

### Scope
- Terminal TUI (Python/Textual) z 4 panelami
- Orkiestracja Claude Code (plan/code/review/run)
- Git branch isolation per task
- Graceful degradation przy limicie CC
- `chat claude` — interaktywna sesja CC z kontekstem projektu

### Out of scope v1
- Codex CLI, Gemini CLI (v2)
- Multi-project support (v2)
- 3-fazowy planning pipeline (v2 — wymaga Codex + Gemini)
- Self-modifying workflow (backlog)

## v2.0 (planned)
- Codex CLI + Gemini CLI integration
- Multi-tool routing (plan/code/review per narzędzie)
- 3-fazowy stress test pipeline
- Multi-project support (`switch`, `projects`)
