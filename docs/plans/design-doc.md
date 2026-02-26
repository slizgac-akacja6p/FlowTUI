# FlowTUI — Design Document

## Architektura modułów

```
flowtui/
├── __init__.py, __main__.py
├── app.py              — FlowTUIApp (Textual App, layout, dispatch_command)
├── cli.py              — Click CLI wrapper
├── config/
│   ├── schema.py       — pydantic models (frozen)
│   └── loader.py       — tomllib + pydantic validation
├── core/
│   ├── engine.py       — Orchestrator (Facade: plan/run/code/review/merge)
│   ├── invoker.py      — CLIInvoker Protocol + SubprocessInvoker (streaming)
│   ├── prompt_builder.py
│   ├── task_manager.py — CRUD na TASK-XXX.md (regex parsing)
│   ├── git_ops.py      — asyncio subprocess git
│   ├── complexity.py   — keyword-based routing
│   ├── test_runner.py  — auto-detect pytest/npm/pubspec
│   └── context_writer.py — docs/context/sprint.md writer
├── planning/
│   ├── pipeline.py     — plan_feature() v1: 1 CC call
│   ├── prompts.py      — prompt templates
│   └── parser.py       — parse stdout → TaskDraft (fallback)
├── analytics/
│   ├── collector.py    — TaskMetrics po każdym run_task
│   ├── storage.py      — analytics.jsonl (filelock, append-only)
│   ├── limits.py       — LimitTracker + is_tool_available()
│   └── stats.py        — obliczenia dashboardu
├── tui/
│   ├── screens.py      — MainScreen
│   ├── widgets/        — TaskPanel, LimitsPanel, SprintPanel, TerminalPanel
│   └── styles.tcss
├── scaffold/
│   ├── init.py
│   └── templates/      — Jinja2 templates
└── startup/
    ├── checker.py
    └── updater.py
```

## Kluczowe decyzje techniczne

| Decyzja | Uzasadnienie |
|---------|-------------|
| CLIInvoker jako Protocol | Duck typing, MockCLI w testach bez dziedziczenia |
| pre_hash rollback | CC może sam commitować — nie ufamy HEAD~1 |
| app.suspend() dla chat | Natywny Textual API, pełne CC doświadczenie, zero complexity |
| filelock + JSONL | Thread-safe, crash-safe, grepowalny, bez migracji schema |
| docs/context/sprint.md | ~200 tokenów kontekstu dla CC w chat mode, bez dużego CLAUDE.md |
| tomllib + pydantic | stdlib 3.11+ + czytelne błędy walidacji, immutable config |

## Scope v1 vs v2

| Feature | v1 | v2 |
|---------|----|----|
| AI tools | CC only | + Codex + Gemini |
| Planning pipeline | 1 CC call | 3-fazowy stress test |
| Multi-project | CWD-based | switch/projects commands |
| Routing | Wszystko → CC | Per-action routing |

## Graceful degradation (v1)

`is_tool_available(tool)` = `today_usage[tool] < budgets[tool]`

Fallback chain v1:
- CC niedostępny → skip + warning w raporcie
- Format: `⚠ DEGRADED: CC limit (14/15) → [operation]: SKIPPED`

## Ryzyko #1: CC -p file creation (SPIKE w M2)

CC w print mode (`-p`) może nie tworzyć plików. Jeśli tak:
- FlowTUI parsuje stdout CC i sam tworzy TASK-XXX.md
- planning/parser.py zawiera fallback parser

## Zależności między milestones

M1 → M2 → M3 (krytyczna ścieżka)
M4 częściowo równolegle z M3 (analytics storage z M1)
M5 po M4

## Mockupy

- M1: /Users/maciejgajda/mockups/flowtui/m1-main-idle.png
- M2: /Users/maciejgajda/mockups/flowtui/m2-plan-streaming.png
- M3: /Users/maciejgajda/mockups/flowtui/m3-task-report.png
- M4: /Users/maciejgajda/mockups/flowtui/m4-degraded-mode.png
