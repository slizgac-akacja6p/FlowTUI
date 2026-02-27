# TASK-001: CC Orchestrator Parallelism

## Meta
- Sprint: backlog
- Priority: medium
- Assigned: unassigned
- Status: TODO
- Created: 2026-02-27
- Updated: 2026-02-27

## Kontekst
FlowTUI currently runs AI CLI calls sequentially. Planning pipeline and sprint runs
could benefit from parallel execution (stress_tester + validator in parallel).

## Wymagania
- Add parallel invocation support to CLIInvoker / engine
- Implement asyncio.gather() based parallel runner for planning pipeline
- Maintain existing sequential fallback
- Add tests for parallel execution paths

## Pliki do modyfikacji
- flowtui/core/engine.py
- flowtui/core/invoker.py
- flowtui/planning/pipeline.py

## Ograniczenia
- Do not break existing sequential execution
- Maintain MockCLI compatibility in tests
- No new external dependencies

## Kryteria akceptacji
- Planning pipeline runs stress_tester + validator in parallel (asyncio.gather)
- Sequential fallback works when parallel=False in config
- Tests pass (385+)

## Log
- 2026-02-27: Task created from M5 backlog (T5.6)
