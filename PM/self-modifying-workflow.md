# FlowTUI — Samomodyfikujący się workflow (Spec)

Wyciągnięte z PRD. Implementacja: M5 (Optimization & Polish). Premature optimization — buduj dopiero po 2+ tygodniach zbierania metryk.

---

## Koncepcja

Claude Opus nie tylko planuje taski — analizuje i optymalizuje sam workflow FlowTUI. Co tydzień (lub na żądanie) CC dostaje metryki i proponuje zmiany w konfiguracji, routingu, szablonach promptów.

## Zbieranie metryk

FlowTUI loguje każde wywołanie AI:

```python
# .flowtui/metrics.jsonl — append-only log
{
    "timestamp": "2026-02-26T14:30:00",
    "tool": "codex",
    "action": "code",
    "task": "TASK-001",
    "duration_sec": 45,
    "files_changed": 3,
    "lines_added": 87,
    "lines_removed": 12,
    "tests_passed": true,
    "review_result": "ok",
    "retry_count": 0,
    "estimated_cost_units": 2
}
```

## Raport tygodniowy (auto-generowany)

```python
def generate_weekly_report() -> str:
    metrics = load_metrics(last_n_days=7)
    report = {
        "tasks_completed": count(metrics, status="DONE"),
        "tasks_failed": count(metrics, retry_count__gt=2),
        "avg_time_per_task": avg(metrics, "duration_sec"),
        "tool_usage": {
            "claude": count(metrics, tool="claude"),
            "codex": count(metrics, tool="codex"),
            "gemini": count(metrics, tool="gemini"),
        },
        "codex_retry_rate": ratio(metrics, tool="codex", retry_count__gt=0),
        "gemini_critical_reviews": count(metrics, tool="gemini", review_result="critical"),
        "estimated_cc_usage_pct": estimate_cc_limit_usage(metrics),
    }
    write_file(".flowtui/metrics.md", format_report(report))
    return report
```

## Komenda: `optimize`

Wywołuje CC Opus z briefingiem:

```python
async def optimize_workflow():
    briefing = build_cc_briefing("review_workflow")
    prompt = f"""{briefing}

Jesteś meta-architektem FlowTUI. Przeanalizuj metryki z ostatniego tygodnia
i zaproponuj konkretne zmiany w workflow.

Możesz modyfikować:
1. .flowtui/routing.toml — kto co robi
2. .flowtui/config.toml — prompty dla narzędzi
3. docs/tasks/ — szablony tasków
4. CLAUDE.md / AGENTS.md — instrukcje dla AI

Format odpowiedzi:
## Analiza
[co działa, co nie]

## Proponowane zmiany
### Zmiana 1: [opis]
Plik: [ścieżka]
Przed: [fragment]
Po: [fragment]
Uzasadnienie: [dlaczego]

## Metryki do monitorowania
[co śledzić w następnym tygodniu]

Zapisz w docs/workflow-optimization-YYYY-MM-DD.md.
NIE aplikuj zmian bezpośrednio — user musi zatwierdzić.
"""
    output = await invoke_ai("claude", prompt)
```

## Komenda: `apply optimization`

```python
async def apply_optimization():
    opt_file = get_latest_optimization()
    changes = parse_proposed_changes(opt_file)
    for change in changes:
        log(f"Zmiana: {change.description}")
        log(f"Diff:\n{change.diff}")
        if await confirm(f"Zastosować? [y/n]"):
            apply_change(change)
```

## Przykłady optymalizacji

### Codex wysoki retry rate na Flutter
→ Wzbogać coding_prompt o konwencje projektu (Riverpod wzorzec, przykładowy plik)

### CC zużywa za dużo na proste planowanie
→ Route plan_simple do Codex, plan_complex do Claude

### Gemini review nie łapie błędów
→ Wzmocnij review_prompt o error handling checklist

## Cykl

```
Tydzień 1: Bazowy workflow → zbieraj metryki
Tydzień 2: optimize → propozycje → apply
Tydzień 3: Zmodyfikowany workflow → metryki → porównanie
```

## Guardrails

- Opus NIGDY nie aplikuje zmian sam — zawsze propozycja + user approval
- Max 3-5 zmian per optymalizację
- Rollback via git diff na config files
- Opus widzi metryki before/after
