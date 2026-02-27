# FlowTUI — Context Management & Token Budget (Spec)

Wyciągnięte z PRD. Implementacja: M4 (Context & Analytics).

---

## Problem

Claude Code ma limit kontekstu (~200k tokenów). Przy długiej sesji kontekst się zapełnia i CC zaczyna "zapominać". W orkiestracji CC musi pamiętać plan, architekturę, status tasków.

## Strategia: Krótkie sesje + stan w plikach

CC nigdy nie utrzymuje kontekstu między sesjami. Cały stan żyje w repo:

```
SESSION START → CC czyta pliki → wykonuje akcję → zapisuje wynik → SESSION END
```

Każda komenda FlowTUI = osobna, krótka sesja CC.

## Mechanizm context briefing

```python
def build_cc_briefing(action: str, task_id: str = None) -> str:
    briefing_parts = []
    
    # 1. ZAWSZE: rola + stack (200 tok)
    briefing_parts.append(f"""
Jesteś architektem projektu {config.project.name}.
Stack: {config.project.stack}
Twoja rola: TYLKO planowanie i specyfikacja. NIGDY nie implementuj kodu.
""")
    
    # 2. ZAWSZE: architektura (skondensowana)
    arch = read_file("docs/architecture.md")
    briefing_parts.append(f"## Architektura\n{arch}")
    
    # 3. KONTEKSTOWE: zależy od akcji
    if action == "plan_feature":
        sprint = get_current_sprint()
        briefing_parts.append(f"## Bieżący sprint\n{sprint.summary()}")
        briefing_parts.append(f"## Istniejące taski\n{sprint.task_list()}")
        
    elif action == "plan_sprint":
        milestone = get_current_milestone()
        done_tasks = get_tasks_by_status("DONE")
        briefing_parts.append(f"## Milestone\n{milestone.summary()}")
        briefing_parts.append(f"## Ukończone\n{format_task_list(done_tasks)}")
        briefing_parts.append(f"## Backlog\n{read_file('docs/backlog.md')}")
        
    elif action == "debug_complex":
        task = load_task(task_id)
        briefing_parts.append(f"## Task\n{task.read()}")
        for f in task.related_files:
            briefing_parts.append(f"## {f}\n{read_file(f)}")
    
    elif action == "review_workflow":
        briefing_parts.append(f"## Metryki\n{read_file('.flowtui/metrics.md')}")
        briefing_parts.append(f"## Config\n{read_file('.flowtui/config.toml')}")
    
    return "\n---\n".join(briefing_parts)
```

## Rozmiary kontekstu per akcja

| Akcja | Briefing | Odpowiedź CC | Total | % kontekstu Opus |
|-------|----------|-------------|-------|-----------------|
| plan feature | ~3k tok | ~2k | ~5k | ~2.5% |
| plan sprint | ~5k | ~5k | ~10k | ~5% |
| debug complex | ~15k (pliki) | ~3k | ~18k | ~9% |
| architecture | ~8k | ~5k | ~13k | ~6.5% |
| review workflow | ~4k | ~3k | ~7k | ~3.5% |

Żadna akcja nie powinna przekroczyć 20% kontekstu.

## Sygnał ostrzegawczy: context approaching limit

```python
MAX_BRIEFING_TOKENS = 40_000  # 20% z 200k

def check_briefing_size(briefing: str):
    estimated_tokens = len(briefing) // 4
    if estimated_tokens > MAX_BRIEFING_TOKENS:
        log("[warning] Briefing za duży — kondensuję")
        return condense_briefing(briefing)
    return briefing

def condense_briefing(briefing: str) -> str:
    # 1. Architektura: tylko sekcje relevant do taska
    # 2. Task list: tylko ID + status (bez pełnych opisów)
    # 3. Pliki: tylko sygnatury funkcji, nie pełny kod
    ...
```

## Multi-step planowanie

```python
async def plan_milestone(milestone_desc: str):
    # Sesja 1: High-level breakdown na sprinty
    briefing = build_cc_briefing("plan_milestone")
    prompt = f"{briefing}\n\nRozplanuj milestone na sprinty.\n{milestone_desc}"
    await invoke_ai("claude", prompt)
    
    # Sesja 2-N: Per sprint, rozplanuj na taski
    for sprint_file in glob("docs/sprints/sprint-*.md"):
        briefing = build_cc_briefing("plan_sprint")
        prompt = f"{briefing}\n\nRozplanuj sprint na taski.\nSprint: {read_file(sprint_file)}"
        await invoke_ai("claude", prompt)
```

## Budżety per typ akcji

| Akcja | Max briefing | Strategia |
|-------|-------------|-----------|
| plan feature | 1500 tok | CLAUDE.md + kompaktowa lista tasków + sprint summary |
| plan sprint | 3000 tok | + milestone summary + backlog skrót |
| debug complex | 15000 tok | + pełne pliki źródłowe (wyjątek) |
| architecture | 5000 tok | + pełny architecture.md |
| review workflow | 2000 tok | metryki + config |

## Reguły kondensacji

1. **Task list = kompaktowy format**: `TASK-001|PDF Export|codex|TODO` (20 tok vs 500 tok pełny)
2. **Research = skróty**: `docs/research/topic.md` max 500 tok, pełna wersja w `full/`
3. **CLAUDE.md = max 500 tokenów**: projekt, stack, rola, bieżący sprint
4. **Architektura on-demand**: czytana TYLKO gdy akcja wymaga
5. **Cache reads**: krótkie powtarzalne sesje z tymi samymi plikami = >90% cache (tańsze)

## CLAUDE.md template

```markdown
# CLAUDE.md — nie usuwaj tego pliku

## Projekt: {name}
Stack: {stack}
Target: {description}

## Architektura
Patrz: docs/architecture.md

## Konwencje
- Język kodu: angielski
- Komentarze: polski
- Testy: każdy service ma *_test.dart

## Twoja rola
Jesteś architektem. NIGDY nie implementuj kodu.
Implementację robi Codex (AGENTS.md). Review robi Gemini.

## Bieżący stan
<!-- FlowTUI auto-aktualizuje tę sekcję -->
Aktywny sprint: sprint-XXX
Tasków TODO: N
Tasków DONE: N
Ostatnia zmiana: YYYY-MM-DD HH:MM
```
