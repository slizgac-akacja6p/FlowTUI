# FlowTUI — Milestones

## M1: Fundament
Szkielet aplikacji: Python/Textual, `flowtui init`, parsowanie config.toml, 4 panele TUI, limit tracking, logging, startup.
Kryterium sukcesu: `flowtui` uruchamia się z 4 panelami, `status` działa, `flowtui init` tworzy strukturę projektu.
UI: tak. Mockup: `/Users/maciejgajda/mockups/flowtui/m1-main-idle.png`
Status: TODO

## M2: AI Integration
`invoke_and_measure()`, komendy plan/code/review ze streamingiem, planning pipeline v1 (1 CC call), `chat [model]` z `app.suspend()`, `docs/context/sprint.md`, graceful degradation, dry-run. Spike: weryfikacja CC `-p` file creation jako task #1.
Kryterium sukcesu: `plan "X"` → streaming → tabela DRAFT → `plan --approve`. `chat claude` zawiesza TUI i otwiera CC interaktywnie z kontekstem projektu.
UI: tak. Mockup: `/Users/maciejgajda/mockups/flowtui/m2-plan-streaming.png`
Status: TODO

## M3: Automation
Pełny cykl `run TASK-XXX` (impl → review → verify AC → raport), git branch isolation, retry (MAX=2), circuit breaker (3 consecutive fails), `run sprint`, `merge`.
Kryterium sukcesu: `run TASK-001` → raport z tabelą faz. Circuit breaker zatrzymuje sprint po 3 failach.
UI: tak. Mockup: `/Users/maciejgajda/mockups/flowtui/m3-task-report.png`
Status: TODO

## M4: Analytics
Rozszerzone metryki, `stats` dashboard, auto-update CLAUDE.md projektu przez CC.
Kryterium sukcesu: `stats` → dashboard zużycia CC, retry rate, średni czas taska.
UI: tak. Mockup: `/Users/maciejgajda/mockups/flowtui/m4-degraded-mode.png`
Status: TODO

## M5: Polish
Eksport CSV/JSON, edge case error handling, MockCLI, `flowtui exec` headless mode.
Kryterium sukcesu: `--dry-run` działa dla wszystkich komend, `stats --export csv` generuje plik.
UI: nie.
Status: TODO
