# FlowTUI

Terminal Development Orchestrator — TUI w Pythonie orkiestrujące AI CLI z jednego interfejsu.

## Stack
- Python 3.11+, Textual (async TUI), subprocess, watchdog, pydantic, filelock
- Entry point: `flowtui` (pyproject.toml scripts)
- Brak własnego serwera — wszystko przez pliki w repo

## Struktura projektu
```
flowtui/
├── __init__.py, __main__.py, app.py, cli.py
├── config/          # loader.py, schema.py (pydantic)
├── core/            # engine.py, invoker.py, prompt_builder.py,
│                    # task_manager.py, git_ops.py, complexity.py, test_runner.py
├── planning/        # pipeline.py, prompts.py, parser.py
├── analytics/       # collector.py, storage.py, limits.py, stats.py
├── tui/             # screens.py, widgets/ (task_panel, limits_panel,
│                    #   sprint_panel, terminal_panel), styles.tcss
├── scaffold/        # init.py, templates/
└── startup/         # updater.py, checker.py
tests/
docs/
  context/sprint.md  # dynamiczny stan sprintu (aktualizowany po każdym tasku)
  plans/
  test-scenarios/
PM/
  tasks/             # PM/tasks/M{N}.md
  milestones.md
  roadmap.md
.flowtui/
  config.toml        # konfiguracja projektu
  routing.toml
  analytics.jsonl    # append-only log wywołań
  versions.jsonl
  last_update.json
```

## Konwencje
- Kod i komentarze: angielski
- Testy: pytest + pytest-asyncio
- Async: asyncio native (Textual event loop)
- Git: `flowtui/TASK-XXX` branches, merge --no-ff do develop
- Brak hardcoded secrets

## Kluczowe wzorce
- `CLIInvoker` jako Protocol (duck typing, MockCLI w testach)
- `pre_hash = git rev-parse HEAD` przed invocation (rollback target)
- `app.suspend()` dla `chat [model]` — CC interactive w pełnym terminalu
- `docs/context/sprint.md` — mały plik (~20-30 linii) z aktualnym stanem, aktualizowany po każdym tasku

## Uruchomienie
```bash
pip install -e ".[dev]"
flowtui                    # TUI w katalogu projektu
flowtui --project PATH     # wskaż projekt
flowtui init               # scaffold nowego projektu
flowtui exec "plan 'X'"   # headless (bez TUI)
```

## GitHub
Repozytorium: do uzupełnienia po stworzeniu
Branch strategy: main ← test ← develop ← feature/m{N}-opis
