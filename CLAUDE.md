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
├── core/            # engine.py, invoker.py, prompt_builder.py, task_manager.py,
│                    # git_ops.py (GitOps), complexity.py, test_runner.py (TestRunner),
│                    # context_writer.py (write_sprint_context),
│                    # claude_md_updater.py (ClaudeMdUpdater — async CC calls)
├── planning/        # pipeline.py, prompts.py, parser.py
├── analytics/       # collector.py (AnalyticsCollector), storage.py, limits.py,
│                    # stats.py (StatsCalculator, export_csv/json)
├── tui/             # screens.py, widgets/ (task_panel [watchdog + debounce],
│                    #   limits_panel, sprint_panel, terminal_panel), styles.tcss
├── scaffold/        # init.py, templates/
└── startup/         # updater.py, checker.py
tests/               # conftest.py (fixtures), mock_cli.py (MockCLI)
docs/
  context/sprint.md  # dynamiczny stan sprintu (~200 tok, pisany przed chat i po tasku)
  plans/
  test-scenarios/
PM/
  tasks/             # PM/tasks/M{N}.md
  milestones.md
  roadmap.md
.flowtui/
  config.toml, routing.toml, analytics.jsonl, versions.jsonl, last_update.json
  exports/           # CSV/JSON z `stats --export`
```

## Konwencje
- Kod i komentarze: angielski
- Testy: pytest + pytest-asyncio
- Async: asyncio native (Textual event loop)
- Git: `flowtui/TASK-XXX` branches, merge --no-ff do develop
- Brak hardcoded secrets

## Kluczowe wzorce
- **GitOps** — async operacje git (create_branch, checkpoint, rollback, diff_stat, merge_to), branch isolation per task: `flowtui/TASK-XXX`
- **TestRunner** — auto-detect framework (pytest/npm/flutter), uruchamiany po każdym task'u
- **AnalyticsCollector** — zbiera TaskMetrics (duration, model calls, retries), persystuje do analytics.jsonl po każdym run_task
- **Circuit breaker** — 3 consecutive faile w sprincie → stop (graceful degradation)
- **Watchdog (TaskPanel)** — obserwuje docs/tasks/ z debounce 0.5s, reload UI na zmianę
- **ClaudeMdUpdater** — async CC call via invoker, atomic write (filelock) do CLAUDE.md
- **CLIInvoker** jako Protocol (duck typing, MockCLI w testach)
- `pre_hash = git rev-parse HEAD` przed invocation (rollback target)
- `app.suspend()` dla `chat [model]` — CC interactive w pełnym terminalu
- `docs/context/sprint.md` — mały plik (~200 tok) z aktualnym stanem, pisany przed `chat` i aktualizowany po każdym tasku

## Uruchomienie
```bash
pip install -e ".[dev]"
flowtui                           # TUI w katalogu projektu
flowtui --project PATH            # wskaż projekt
flowtui init                      # scaffold nowego projektu
flowtui execute "komenda"         # headless (bez TUI), używany w CI

# W TUI: komendy
plan "opis"                       # planning pipeline z CC
code TASK-XXX                     # implementacja taska
review TASK-XXX                   # code review
run TASK-XXX                      # full cycle (impl→review→verify AC→report)
run sprint                        # sekwencyjnie TODO, circuit breaker na 3 faile
merge [TASK-XXX]                  # merge done branche do develop
chat [model]                      # interaktywna sesja CC (suspend → full terminal)
stats / stats --export csv|json   # dashboard zużycia + retry rate
```

## GitHub
Repozytorium: https://github.com/slizgac-akacja6p/FlowTUI
Branch strategy: main ← test ← develop ← feature/m{N}-opis
