# FlowTUI — Terminal Development Orchestrator

## PRD v1.0 (po walidacji Codex CLI)

---

## Problem

Solo developer prowadzący wiele projektów (Drop, DocFlow, MailMind) korzysta z Claude Code Max ($200/mies) i regularnie wyczerpuje limity. Brak narzędzia, które:

- Centralizuje zarządzanie taskami i kontekstem projektu w terminalu
- Pozwala delegować pracę do wielu AI CLI (Claude Code, Codex CLI, Gemini CLI) z jednego interfejsu
- Minimalizuje zużycie tokenu droższych modeli przez inteligentny routing
- Utrzymuje kontekst między narzędziami przez filesystem (shared memory)
- Śledzi zużycie limitów i koszty w czasie

## Użytkownik docelowy

Doświadczony developer (senior+), pracujący solo lub w małym zespole, korzystający z wielu AI CLI tools na subskrypcjach (nie API). Preferuje terminal nad GUI. Prowadzi 2-5 projektów równolegle.

## Cele

1. **Redukcja kosztów**: Spadek zużycia Claude Code o 60-80% przez delegację kodowania do Codex/Gemini
2. **Zachowanie jakości**: Opus do planowania/architektury, Codex do implementacji, Gemini do review/docs
3. **Zero context loss**: Cały kontekst żyje w plikach — żadne narzędzie nie jest single point of failure
4. **Terminal-native**: TUI z panelami, nie kolejna webapp
5. **Widoczność kosztów**: Estymacja zużycia limitów per narzędzie od dnia 1

## Non-goals

- Zastępowanie IDE/edytora kodu
- Budowanie własnego LLM routera/proxy
- Obsługa API poszczególnych modeli (używamy CLI na subskrypcjach)
- Współpraca wieloosobowa (v1 = solo)
- Self-modifying workflow (→ backlog, patrz `docs/flowtui/self-modifying-workflow.md`)

## Walidacja Codex CLI (2026-02-26)

Test na izolowanym sandbox Dart (5 tasków, porównanie Codex vs CC):

| # | Task | Codex | CC | Wnioski |
|---|------|-------|----|---------|
| 1 | Trivial (nowy plik utility) | ✅ 23 testów, 60s | ✅ 32 testów, 30s | Codex lepiej respektuje AGENTS.md |
| 2 | Simple (modyfikacja modelu) | ✅ 35 testów, 50s | ✅ 21 testów, 30s | Codex wzorował się na wskazanym pliku |
| 3 | Medium (nowy serwis) | ✅ 22 testów, 90s | ✅ 30 testów, 30s | Codex defensywne helpery |
| 4 | Refactor (istniejący kod) | ✅ 16 testów, 221s | ✅ 16 testów, 60s | Codex elegancki generic helper |
| 5 | Hard (multi-file feature) | ✅ 5 plików, 21 testów, 120s | ⚠ 4 pliki, 33 testów, 60s | Codex naprawił bug w update() którego CC nie złapał |

**Wynik: 5/5 ✅, 0 retries. FlowTUI ma sens.**

Kluczowe obserwacje:
1. Codex lepiej respektuje AGENTS.md niż CC (angielskie nazwy testów vs polskie)
2. Codex lepszy cross-file reasoning (Task 5: proaktywnie naprawił implikacje zmian)
3. CC pisze więcej testów/edge cases, ale narusza konwencje
4. Codex wolniejszy (60-221s vs 30-60s CC) — xhigh reasoning effort, akceptowalny trade-off
5. Plus ($20) wystarczył na 5 tasków, weekly limit 76% remaining

**Zużycie limitu Plus:** 5 tasków = 24% weekly. W pipeline FlowTUI 1 task = ~3 wywołania Codex → **~7 tasków/tyg na Plus**. Wystarczy na 1 projekt. Upgrade do Pro ($200) gdy 3 projekty równolegle.

## Budżet (start)

| Narzędzie | Plan | Koszt | Upgrade gdy |
|-----------|------|-------|------------|
| CC | Max 5x | $100 | — (orkiestrator, potrzebny) |
| Codex | Plus | $20 | Pro ($200) gdy >1 projekt aktywny |
| Gemini | Free | $0 | AI Pro ($20) gdy >30 review/dzień |
| Perplexity | Pro | $20 | — |
| **Total** | | **$140/mies** | Max $340 po upgradach |

---

## Architektura

### Zasada nadrzędna

**Repo jest pamięcią współdzieloną.** FlowTUI nie przechowuje stanu — czyta i pisze do struktury plików w repo. Każde AI CLI czyta tę samą strukturę.

### Struktura projektu (konwencja)

```
project/
├── .flowtui/
│   ├── config.toml          # konfiguracja projektu
│   ├── routing.toml          # reguły routingu AI
│   ├── analytics.jsonl       # log wywołań AI (append-only)
│   ├── versions.jsonl        # historia wersji CLI tools
│   └── last_update.json      # timestamp ostatniego auto-update
├── CLAUDE.md                  # kontekst dla Claude Code
├── AGENTS.md                  # kontekst dla Codex CLI
├── docs/
│   ├── architecture.md
│   ├── sprints/sprint-XXX.md
│   ├── tasks/TASK-XXX.md
│   ├── research/
│   └── design/mockups/
└── src/
```

### Konfiguracja (.flowtui/config.toml)

```toml
[project]
name = "DocFlow"
stack = "Flutter, Docker, PostgreSQL"
description = "B2B document workflow system for Polish SMEs"

[tools]
planner = "claude"
coder = "codex"
reviewer = "gemini"

[tools.claude]
command = "claude"
flags = "--dangerously-skip-permissions -p"
planning_prompt = """
Jesteś architektem projektu {project.name}.
Stack: {project.stack}
Czytaj docs/architecture.md po kontekst.
Zapisuj taski w docs/tasks/ w formacie TASK-XXX.md.
NIGDY nie implementuj kodu — tylko planuj i specyfikuj.
"""

[tools.codex]
command = "codex"
flags = "exec --full-auto"
coding_prompt = """
Implementuj task opisany w {task_file}.
Czytaj AGENTS.md po konwencje.
Po zakończeniu oznacz ## Status: DONE w pliku taska.
Uruchom testy przed oznaczeniem.
"""

[tools.gemini]
command = "gemini"
flags = "--yolo --sandbox=false"
review_prompt = """
Zrób code review zmian: {diff}
Sprawdź: edge cases, error handling, naming, testy.
Format: lista problemów z severity (critical/warning/info).
"""

[startup]
auto_update = true
update_timeout = 60
skip_if_recent = 3600           # skip update jeśli ostatni <1h temu

[limits]
# Kalibrowane na Plus ($20). Na Pro → podwyż 5x.
claude_daily_budget = 15        # max sesji dziennie (Max 5x)
codex_daily_budget = 5          # Plus: ~20/tyg = ~3-4/dzień bezpiecznie
gemini_daily_budget = 30        # Free: 1000 req/dzień
```

### Routing (kto co robi)

```toml
# .flowtui/routing.toml
[rules]
plan = "claude"
code = "codex"
test = "codex"
review = "gemini"
deep_review = "claude"       # logika, architektura — tylko complex taski
docs = "gemini"
design = "gemini"
debug_simple = "codex"
debug_complex = "claude"
```

---

## Format taska (TASK-XXX.md)

```markdown
# TASK-001: [Tytuł]

## Meta
- Sprint: sprint-001
- Priority: high | medium | low
- Assigned: codex | claude | gemini
- Status: DRAFT | TODO | IN_PROGRESS | IN_REVIEW | DONE | BLOCKED
- Created: 2026-02-26
- Updated: 2026-02-26

## Kontekst
Krótki opis dlaczego ten task istnieje.

## Wymagania
- [ ] Wymaganie 1
- [ ] Wymaganie 2

## Pliki do modyfikacji
- `src/services/pdf_service.dart` (nowy)
- `src/models/document.dart` (edycja)

## Ograniczenia
- Użyj biblioteki `pdf` 3.x (nie `printing`)
- Polskie znaki UTF-8

## Kryteria akceptacji
1. Unit testy przechodzą
2. Polskie znaki renderują się poprawnie

## Log
<!-- AI dopisuje automatycznie -->
```

---

## Interface (TUI)

### Technologia

- **Python 3.11+**
- **Textual** — async TUI framework (Rich pod spodem)
- **subprocess** — wywoływanie CLI tools
- **watchdog** — obserwowanie zmian w docs/tasks/

### Layout

```
┌─ FlowTUI ── DocFlow ── Sprint S03 ─────────────────────────┐
│                                                              │
│  TASKS                      │  LIMITS                        │
│  ✅ TASK-001 PDF service    │  CC:     ██░░░░ 5/15 dziś      │
│  🔄 TASK-002 Print engine   │  Codex:  ████░░ 23/50 dziś     │
│  ⬜ TASK-003 Unit tests     │  Gemini: █░░░░░ 3/30 dziś      │
│  ⬜ TASK-004 i18n support   │                                │
│                              │  SPRINT                        │
│                              │  Done: 1/4  Blocked: 0         │
│                              │  Retry rate: 0%                 │
│                              │                                │
├──────────────────────────────┴────────────────────────────────┤
│ TERMINAL                                                      │
│ [codex] TASK-002: 2 pliki, +87 -12                           │
│ [gemini] Review TASK-002: OK, 1 suggestion (info)            │
│ [system] ✅ TASK-002 → DONE                                  │
│                                                               │
│ > _                                                          │
└──────────────────────────────────────────────────────────────┘
```

### Panele

| Panel | Zawartość | Odświeżanie |
|-------|-----------|-------------|
| TASKS | Lista tasków z bieżącego sprintu, status | Watchdog na docs/tasks/ |
| LIMITS | Zużycie dziś / budget per narzędzie | Po każdym wywołaniu |
| SPRINT | Done/total, blocked, retry rate | Po każdym tasku |
| TERMINAL | Live progress + task reports (tabelki) + prompt | Real-time |

**Zasada: TERMINAL jest jedynym kanałem komunikacji z userem.** Tabelki task reportów i sprint summary pojawiają się tu. User nie jest pytany o nic poza `plan --approve/--reject`.

### Komendy

```
# Planowanie (→ pipeline: Codex + CC + Gemini)
plan "opis feature'a"              # pipeline → draft → stress → validate → fix → POKAŻ PLAN
plan --approve                      # zatwierdź ostatni plan (taski → TODO)
plan --reject "powód"               # odrzuć → taski usunięte
plan sprint                         # CC planuje następny sprint

# Implementacja (→ Codex CLI)  
code TASK-001                       # Codex implementuje task
code next                           # Codex bierze następny TODO

# Review (→ Gemini CLI)
review TASK-001                     # Gemini reviewuje zmiany

# Workflow — autonomiczny, bez pytań
run TASK-001                        # pełny cykl: code → testy → review → verify → report
run sprint                          # cały sprint autonomicznie (circuit breaker na 3 faile)
run "opis feature'a"                # end-to-end: plan → approve prompt → sprint → merge → summary
merge                               # merge wszystkich DONE branchy do develop
merge TASK-001                      # merge konkretnego taska

# Zarządzanie
status                              # podsumowanie sprintu + limity (tabelka)
limits                              # szczegóły zużycia limitów
update                              # force update narzędzi CLI
init                                # scaffold nowy projekt FlowTUI
switch docflow                      # przełącz projekt

# Bezpośredni dostęp
claude "pytanie"
codex "pytanie"
gemini "pytanie"
```

---

## Startup

Przy każdym uruchomieniu FlowTUI:

1. **Auto-update CLI** (parallel, max 60s per tool, skip jeśli <1h od ostatniego)
2. **Weryfikacja wymaganych narzędzi** w PATH (claude, codex wymagane; gemini opcjonalny)
3. **Logowanie wersji** do `.flowtui/versions.jsonl`
4. **Załadowanie projektu** z CWD lub `--project`

```
┌─ FlowTUI v0.1 ── startup ──────────────────────────┐
│ 🔄 Aktualizacja narzędzi...                        │
│   claude  1.0.34 → 1.0.35  ✅ updated              │
│   codex   0.36.0            ✅ up to date           │
│   gemini  ⚠ not installed (optional, skipping)      │
│ Gotowe w 3.1s. Ładuję projekt: docflow...           │
└──────────────────────────────────────────────────────┘
```

Szczegóły: → `docs/flowtui/bypass-permissions.md` (konfiguracja trybu autonomicznego)

---

## `flowtui init` — scaffold nowego projektu

```bash
> flowtui init
```

Tworzy:
```
.flowtui/
├── config.toml        # z interaktywnym pytaniem o project name, stack, tools
└── routing.toml       # domyślny routing (plan=claude, code=codex, review=gemini)
CLAUDE.md              # template z docs/flowtui/context-management.md
AGENTS.md              # template: konwencje, stack, rola
docs/
├── architecture.md    # pusty placeholder
├── sprints/
└── tasks/
```

Init wykrywa istniejący projekt (czy jest `.flowtui/`) i odmawia nadpisania. `--force` wymusza.

---

## Planning pipeline — trójfazowy stress test

Planowanie to najważniejszy etap. Zły plan = zmarnowana implementacja. Trzy narzędzia, trzy perspektywy:

| | Codex | CC Opus | Gemini Pro |
|--|-------|---------|------------|
| Siła | Zna kod, widzi repo | Krytyczne myślenie, architektura | 1M context, widzi WSZYSTKO naraz |
| Rola | Planuje Z kodu | Kwestionuje, szuka dziur | Waliduje spójność z repo |
| Pytanie | "CO i GDZIE?" | "CO JEST ŹLE?" | "CZY PASUJE DO RESZTY?" |

### Flow

```
             ┌──────────── ITERACJA 1 ────────────┐
             │                                     │
  Codex ──→  │  CC stress ──┐                      │
  draft      │              ├→ Codex fix ──→ OK? ──┤──→ DONE
             │  Gemini val ─┘       (parallel)     │
             │                                     │
             └─────── blocking? ──────────────────┘
                         │ yes
                         ▼
             ┌──────── ITERACJA 2 ────────────┐
             │  CC re-review (500 tok)         │
             │  → resolved? → DONE             │
             │  → still blocking? → ESKALACJA  │
             └─────────────────────────────────┘
                         │
                         ▼
              User decyduje → plan ponownie
```

### Fazy

**FAZA 1 — DRAFT (Codex):** Czyta opis + istniejący kod → generuje draft TASK-XXX.md. Tytuł, kontekst, pliki do modyfikacji, zależności. Nie implementuje.

**FAZA 2 — STRESS TEST (CC + Gemini parallel):**
- CC: stress test architektoniczny — brakujące taski, zależności, ryzyko, brakujące decyzje, scope
- Gemini: walidacja z kodem — konflikty z istniejącym kodem, łamanie konwencji, brakujące testy, broken interfaces, brakujące migracje callerów. Gemini dostaje draft + issues CC + CAŁY relevant kod (pliki z tasków + reverse deps + testy, typowo 20-80k tok — łyka bez problemu).

**FAZA 3 — FIX (Codex):** Czyta draft + issues CC + issues Gemini → poprawia taski.

**FAZA 4 — RE-REVIEW (CC, warunkowa):** Tylko jeśli CC zgłosił BLOCKING issues. Ultra krótka sesja (~500 tok) — sprawdza czy fixy adresują blocking problems.

### Severity issues

```python
@dataclass
class StressIssue:
    severity: str   # "blocking" | "important" | "suggestion"
    description: str
    category: str   # "missing_decision" | "missing_task" | "dependency" |
                    #  "risk" | "scope" | "conflict"
```

- **BLOCKING**: plan nie może być realizowany bez rozwiązania (brak decyzji arch, fundamentalny konflikt)
- **IMPORTANT**: plan zadziała ale będzie miał problemy (brak testów, edge case, ryzyko)
- **SUGGESTION**: nice-to-have

### Complexity routing — nie każdy plan wymaga pełnego pipeline

```python
async def plan_feature(description: str, force_level: str = None):
    complexity = force_level or estimate_complexity(description)

    if complexity == "trivial":
        await codex_draft(description)
    elif complexity == "simple":
        await codex_draft(description)
        await gemini_validate()
        await codex_fix()
    else:
        # complex → pełny pipeline
        await codex_draft(description)
        stress_issues, validation_issues = await asyncio.gather(
            cc_stress_test(),
            gemini_validate(),
        )
        blocking = [i for i in stress_issues if i.severity == "blocking"]

        if stress_issues or validation_issues:
            await codex_fix(stress_issues, validation_issues)

        if blocking:
            re_review = await cc_re_review(blocking)
            still_blocking = [i for i in re_review if i.severity == "blocking"]
            if still_blocking:
                show_blocking_escalation(still_blocking)
                return  # user musi zdecydować
    
    # CHECKPOINT: pokaż plan userowi jako tabelkę
    draft_tasks = load_draft_tasks()
    show_plan_table(draft_tasks, complexity)
    # Taski mają status DRAFT — nie TODO. User musi zatwierdzić.

def show_plan_table(tasks: list[Task], complexity: str):
    """Plan jako tabelka — jedyny checkpoint przed implementacją."""
    
    log(f"""
═══ Plan ({complexity}) ═══

| #  | Task       | Opis                    | Pliki | Assigned | Zależności |
|----|------------|-------------------------|-------|----------|-----------|""")
    
    for i, t in enumerate(tasks, 1):
        log(f"| {i:2d} | {t.id:10s} | {t.title:23s} | {len(t.files):5d} | {t.assigned:8s} | {t.deps or '—':9s} |")
    
    log(f"""
Stress test: {complexity_label(complexity)}
Issues: {issues_summary}

→ `plan --approve` aby zatwierdzić i rozpocząć sprint
→ `plan --reject "powód"` aby odrzucić
""")
```

`plan --approve` zmienia status tasków z DRAFT → TODO. Dopiero wtedy `run sprint` je widzi.

```python
async def approve_plan():
    drafts = load_tasks_by_status("DRAFT")
    for task in drafts:
        update_task_status(task.path, "TODO", "user")
    log(f"[system] ✅ {len(drafts)} tasków zatwierdzonych → TODO")

async def reject_plan(reason: str):
    drafts = load_tasks_by_status("DRAFT")
    for task in drafts:
        os.remove(task.path)
    log(f"[system] ❌ Plan odrzucony: {reason}. {len(drafts)} tasków usunięte.")
```

Komendy:
```
plan "fix typo w README"                    → trivial: Codex solo
plan "dodaj pole email do formularza"       → simple:  Codex → Gemini → Codex
plan "eksport PDF z watermarkami i i18n"     → complex: Codex → CC+Gemini → Codex (+ iter 2)
plan --simple "..."                          → force simple
plan --complex "..."                         → force complex
```

### Heurystyka złożoności

```python
def estimate_complexity(description: str) -> str:
    desc = description.lower()
    complex_kw = ["architektura", "nowy moduł", "migracja", "integracja",
                  "security", "auth", "database schema", "api design"]
    trivial_kw = ["fix", "typo", "zmień tekst", "rename", "bump version"]
    simple_kw = ["dodaj pole", "refactor", "popraw", "aktualizuj", "test"]

    if any(k in desc for k in complex_kw):
        return "complex"
    if any(k in desc for k in trivial_kw):
        return "trivial"
    if any(k in desc for k in simple_kw):
        return "simple"
    return "complex"  # default bezpieczny
```

### Gemini validation context — superpower 1M

```python
def build_gemini_validation_context(draft_tasks: list[Task]) -> str:
    """Wszystkie relevantne pliki — Gemini łyka do 500k tok."""
    context_parts = []

    for task in draft_tasks:
        for filepath in task.files_to_modify:
            if os.path.exists(filepath):
                context_parts.append(f"### {filepath}\n```\n{read_file(filepath)}\n```")

    # Reverse deps — kto importuje modyfikowane pliki
    for filepath in all_mentioned_files:
        for imp in find_files_importing(filepath)[:5]:
            context_parts.append(f"### {imp} (imports {filepath})\n```\n{read_file(imp)}\n```")

    # Istniejące testy
    for filepath in all_mentioned_files:
        test_file = to_test_path(filepath)
        if os.path.exists(test_file):
            context_parts.append(f"### {test_file}\n```\n{read_file(test_file)}\n```")

    return "\n\n".join(context_parts)
```

### Eskalacja do usera

Blocking issues po iteracji 2 to zazwyczaj **decyzje** wymagające człowieka:

```
⛔ Nierozwiązane blocking issues:
  ❌ Brak decyzji: watermark rasterowy vs wektorowy
    → Rasterowy: prostsze, gorsza jakość przy skalowaniu
    → Wektorowy: wymaga cairo/skia, lepsza jakość
  ❌ PrintService legacy — migrować czy wrapper?
    → Migracja: 2 tyg, clean code
    → Wrapper: 2 dni, dług techniczny

Podejmij decyzję: plan "eksport PDF" --context "watermark wektorowy, wrapper na PrintService"
```

FlowTUI nie udaje że AI podejmie decyzję architektoniczną za developera.

### Koszty per scenariusz

| Scenariusz | CC tok | Codex | Gemini | Czas |
|-----------|--------|-------|--------|------|
| Trivial (Codex solo) | 0 | 1 | 0 | ~1 min |
| Simple (skip CC) | 0 | 2 | 1 | ~2 min |
| Complex, clean plan | ~1.3k | 1 | 1 | ~2 min |
| Complex, important issues | ~1.3k | 2 | 1 | ~3 min |
| Complex, blocking → fixed | ~2k | 2 | 1 | ~4 min |
| Complex, blocking → eskalacja | ~2k | 2 | 1 | ~4 min + user |

Worst case complex: 2k tok CC vs 5k+ gdy CC planuje od zera. 2.5x oszczędność, lepszy wynik.

### Prompty

Szczegółowe prompty per fazę: → `docs/flowtui/planning-prompts.md`

---

## Kluczowe mechanizmy

### 1. Context injection

Przed każdym wywołaniem AI, FlowTUI buduje prompt z kontekstem:

```python
def build_prompt(tool: str, task: Task, action: str) -> str:
    config = load_config()
    template = config.tools[tool][f"{action}_prompt"]
    context = {
        "project": config.project,
        "task_file": task.filepath,
        "task_content": task.read(),
        "architecture": read_file("docs/architecture.md"),
        "diff": git_diff() if action == "review" else "",
        "related_files": task.get_related_files_content(),
    }
    return template.format(**context)
```

Szczegóły briefingów i token budgets: → `docs/flowtui/context-management.md`

### 2. CLI output parsing

**Najkruchszy element orkiestracji.** Format outputu CLI zmienia się między wersjami.

Strategia: **nie parsuj struktury outputu — parsuj efekty w repo.**

```python
@dataclass
class InvocationResult:
    tool: str
    exit_code: int
    stdout: str
    stderr: str
    duration_sec: float
    # Parsowane z repo, nie z outputu:
    files_changed: list[str]
    lines_added: int
    lines_removed: int
    tests_passed: bool | None

async def invoke_and_measure(tool: str, prompt: str) -> InvocationResult:
    """Wywołuje CLI i mierzy efekty przez git, nie przez parsowanie outputu."""
    
    start = time.time()
    
    # Snapshot przed
    await bash("git add -A && git stash --include-untracked")
    pre_hash = await bash("git rev-parse HEAD")
    await bash("git stash pop")
    
    # Wywołanie
    cmd = TOOL_COMMANDS[tool] + [prompt]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=project_root,
    )
    
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        return InvocationResult(tool=tool, exit_code=-1, stdout="", 
                                stderr="TIMEOUT", duration_sec=300,
                                files_changed=[], lines_added=0, lines_removed=0,
                                tests_passed=None)
    
    # Mierz efekty z git diff (niezależne od formatu CLI)
    diff_stat = await bash("git diff --stat HEAD")
    files, added, removed = parse_diff_stat(diff_stat)
    
    # Uruchom testy
    tests = await run_project_tests()
    
    return InvocationResult(
        tool=tool,
        exit_code=proc.returncode,
        stdout=stdout.decode(),
        stderr=stderr.decode(),
        duration_sec=time.time() - start,
        files_changed=files,
        lines_added=added,
        lines_removed=removed,
        tests_passed=tests.passed if tests else None,
    )
```

**Dlaczego git diff a nie parsowanie stdout:**
- Git diff jest stabilny — nie zmienia się z wersją CLI
- Działa identycznie dla claude, codex, gemini
- Mierzy faktyczny efekt, nie deklarowany

**Jedyny stdout parsing**: sprawdzanie exit_code i szukanie keywords w stderr (error, failed, timeout). Nie polegamy na strukturze.

### 3. Status tracking

```python
def update_task_status(task_path: str, new_status: str, agent: str):
    content = read_file(task_path)
    content = re.sub(r"Status: \w+", f"Status: {new_status}", content)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    log_entry = f"- [{timestamp}] {agent}: Status → {new_status}"
    content = append_to_section(content, "## Log", log_entry)
    write_file(task_path, content)
```

### 4. Pełny cykl (run) z error recovery i eskalacją

Eskalacja wzorowana na tiered model: Codex (impl) → Gemini (review) → CC (deep review, selektywny). Analogia: haiku → sonnet → opus.

**verify jest wbudowany w run** — user nie musi go uruchamiać osobno. Model A: nikt nie pamięta ręcznie weryfikować.

**Deep review (CC) jest selektywny** — nie na każdym complex tasku, a tylko gdy:
- Gemini review znalazł warnings (ale nie critical)
- Task dotyka security/auth/payment
- Task modyfikuje >5 plików (szeroki blast radius)

Bez tego CC deep review na 50% tasków podwaja zużycie CC — sprzeczne z celem.

```python
MAX_RETRY = 2

def needs_deep_review(task: Task, review: ReviewResult) -> bool:
    """Selektywny deep review — nie na każdym complex tasku."""
    if review.has_warnings:
        return True  # Gemini nie jest pewny → CC weryfikuje
    security_keywords = ["auth", "security", "payment", "token", "password", "encryption"]
    if any(k in task.title.lower() or k in task.context.lower() for k in security_keywords):
        return True
    if len(task.files_to_modify) > 5:
        return True  # szeroki blast radius
    return False

async def run_task(task_id: str) -> TaskResult:
    task = load_task(task_id)
    branch = f"flowtui/{task_id}"
    
    # Git isolation
    await bash(f"git checkout -b {branch}")
    await checkpoint(f"start-{task_id}")
    update_task_status(task.path, "IN_PROGRESS", "system")
    
    # 0. Walidacja kryteriów akceptacji
    untestable = flag_untestable_criteria(task)
    
    # 1. Implementacja z retry
    retry = 0
    while retry <= MAX_RETRY:
        result = await invoke_and_measure("codex", build_prompt("codex", task, "coding"))
        
        if result.exit_code != 0:
            retry += 1
            if retry > MAX_RETRY:
                return finish_task(task, "BLOCKED", "codex exit error", result)
            await bash("git reset --hard HEAD~1")
            continue
        
        if result.tests_passed is False:
            fix_prompt = f"Testy failują. Napraw.\n{result.stderr}"
            result = await invoke_and_measure("codex", fix_prompt)
            retry += 1
            continue
        
        break
    
    if retry > MAX_RETRY:
        return finish_task(task, "BLOCKED", f"failed after {MAX_RETRY} retries", result)
    
    # 2. Summary (Gemini — opis zmian dla usera)
    summary = await generate_change_summary(result)
    
    # 3. Review (Gemini)
    review_result = await invoke_and_measure("gemini", build_prompt("gemini", task, "review"))
    review_parsed = parse_review(review_result.stdout)
    
    # 4. Deep review (CC) — SELEKTYWNY
    deep_review = None
    if needs_deep_review(task, review_parsed):
        deep_review = await invoke_and_measure("claude", build_prompt("claude", task, "deep_review"))
    
    # 5. Critical issues → Codex fix + re-review
    if review_parsed.has_critical or (deep_review and "critical" in deep_review.stdout.lower()):
        await invoke_and_measure("codex", f"Napraw critical issues:\n{review_parsed.critical_issues}")
        review_result = await invoke_and_measure("gemini", build_prompt("gemini", task, "review"))
        review_parsed = parse_review(review_result.stdout)
    
    if review_parsed.has_critical:
        return finish_task(task, "BLOCKED", "critical issues after fix", result, summary, review_parsed)
    
    # 6. Verify (wbudowany — acceptance criteria)
    criteria_results = await check_acceptance_criteria(task)
    
    # 7. Report (tabelka)
    return finish_task(task, "DONE", None, result, summary, review_parsed, deep_review, 
                       criteria_results, untestable)
```

### 5. Human-readable output — tabelki, nie surowe diffy

User nie czyta kodu. Każdy krok prezentowany jako tabela. **Cisza poza checkpointami** — TERMINAL pokazuje live progress, ale user nie jest pytany o nic.

**Po każdym tasku — task report:**

```python
SUMMARY_PROMPT = """Przeczytaj diff i opisz zmiany w 2-3 zdaniach.
Biznesowy opis, nie techniczny. Co zostało dodane/zmienione z perspektywy feature'a.
Wymień nowe klasy/metody po nazwie.

Diff:
{diff}"""

def format_task_report(task, result, summary, review, deep_review, 
                       criteria, untestable) -> str:
    report = f"""
┌─ {task.id}: {task.title} ─────────────────────────────┐

| Etap            | Status | Szczegóły                     |
|-----------------|--------|-------------------------------|
| Implementacja   | {icon(result)} | {result.files_changed_count} plików, +{result.lines_added} -{result.lines_removed} |
| Testy           | {icon(result.tests_passed)} | {result.tests_count} passed |
| Review (Gemini) | {review.icon} | {review.summary_oneliner} |
| Deep review (CC)| {icon(deep_review) if deep_review else '—'} | {deep_review_text(deep_review)} |"""
    
    for c in criteria:
        report += f"\n| AC: {c.name:13s} | {icon(c.passed)} | {c.detail:29s} |"
    
    for u in untestable:
        report += f"\n| AC: {u:13s}  | ⚠      | NIETESTOWALNE                 |"
    
    report += f"""

Zmiany: {summary}
Retry: {result.retry_count} | Czas: {result.duration_sec:.0f}s

└───────────────────────────────────────────────────────┘"""
    return report
```

**Po sprincie — sprint summary:**

```python
NEXT_STEPS_PROMPT = """Na podstawie wyników sprintu, wymień 2-3 następne kroki w 1 zdaniu każdy.
Wyniki: {sprint_results}
Blocked taski: {blocked_details}"""

def show_sprint_summary(sprint, results: list[TaskResult]):
    done = [r for r in results if r.status == "DONE"]
    blocked = [r for r in results if r.status == "BLOCKED"]
    
    # Gemini generuje "następne kroki" (tani)
    next_steps = await invoke_and_measure("gemini", NEXT_STEPS_PROMPT.format(...))
    
    log(f"""
═══ Sprint {sprint.id} — podsumowanie ═══

| Task       | Status  | Retry | Czas | Review          |
|------------|---------|-------|------|-----------------|""")
    
    for r in results:
        log(f"| {r.task_id:10s} | {r.status:7s} | {r.retry:5d} | {r.duration:4.0f}s | {r.review_summary} |")
    
    log(f"""
| Metryka          | Wartość   |
|------------------|-----------|
| Done             | {len(done)}/{len(results)} |
| Blocked          | {len(blocked)}             |
| Retry rate       | {retry_rate:.0%}           |
| Avg czas/task    | {avg_duration:.0f}s        |
| CC sesji         | {cc_sessions}              |
| Codex sesji      | {codex_sessions}           |
| Gemini sesji     | {gemini_sessions}          |

Następne kroki: {next_steps.stdout}
""")
```

### 6. Sprint automation — autonomiczny, bez pytań

**Cisza podczas sprintu.** FlowTUI nie pyta usera między taskami. Circuit breaker jedynym mechanizmem stopu.

```python
async def run_sprint():
    sprint = get_current_sprint()
    todo_tasks = [t for t in sprint.tasks if t.status == "TODO"]
    
    results = []
    consecutive_failures = 0
    
    for task in sorted(todo_tasks, key=lambda t: t.priority_rank):
        result = await run_task(task.id)
        results.append(result)
        
        if result.status == "DONE":
            consecutive_failures = 0
        else:
            consecutive_failures += 1
        
        # Circuit breaker: 3 faile z rzędu → stop, nie pytaj
        if consecutive_failures >= 3:
            log(f"[system] ⛔ 3 kolejne faile — sprint przerwany")
            break
        
        # Ctrl+C → graceful stop (jedyny sposób na ręczne przerwanie)
    
    show_sprint_summary(sprint, results)
```

### 7. `run "feature"` — end-to-end, jedyna komenda

Pełny cykl: plan → approve → sprint → merge → summary. User uruchamia jedną komendę, dostaje dwa checkpointy (plan approval + sprint summary).

```python
async def run_feature(description: str):
    """End-to-end: plan → approve → sprint → merge → summary."""
    
    # 1. Plan
    await plan_feature(description)
    # → wyświetla tabelkę planu, czeka na approve/reject
    # user musi wpisać `plan --approve` — BLOCKING checkpoint
```

Po `plan --approve`:

```python
async def run_approved_sprint():
    """Kontynuacja po approve — sprint → merge → summary."""
    
    # 2. Sprint (autonomiczny)
    await run_sprint()
    
    # 3. Auto-merge DONE branchy
    done_tasks = load_tasks_by_status("DONE")
    merge_results = []
    for task in done_tasks:
        success = await safe_merge_to_develop(task.id)
        merge_results.append((task.id, success))
    
    # 4. Merge report
    log(f"""
| Task       | Merge   |
|------------|---------|""")
    for task_id, success in merge_results:
        log(f"| {task_id:10s} | {'✅' if success else '⚠ conflict'} |")
```

### 8. Merge

```python
async def safe_merge_to_develop(task_id: str) -> bool:
    branch = f"flowtui/{task_id}"
    
    await bash("git checkout develop")
    result = await bash(f"git merge {branch} --no-ff")
    
    if "CONFLICT" in result:
        log(f"[system] ⚠ Merge conflict: {branch}")
        log(f"[system] Konflikty: {await bash('git diff --name-only --diff-filter=U')}")
        await bash("git merge --abort")
        return False
    
    await bash(f"git branch -d {branch}")
    return True
```

FlowTUI NIE rozwiązuje konfliktów automatycznie. Abort + inform.
```

FlowTUI NIE próbuje automatycznie rozwiązywać konfliktów — to wymaga ludzkiej decyzji. Abortuje merge i informuje usera.

### 7. Human-in-the-loop research

```python
async def handle_research_request(query: str):
    log(f"🔍 CC potrzebuje researchu:")
    log(f"   Zapytaj Perplexity: \"{query}\"")
    log(f"   Wklej odpowiedź (Enter → pusta linia → Enter):")
    
    response = await read_multiline_input()
    filename = f"docs/research/{slugify(query)}-{today()}.md"
    write_file(filename, f"# Research: {query}\n\n{response}")
    return filename
```

---

## Limit tracking (od dnia 1)

Panel LIMITS w TUI — prosty licznik wywołań per narzędzie, per dzień.

```python
@dataclass
class LimitTracker:
    """Prosty tracker: zlicza wywołania, porównuje z budżetem."""
    
    def __init__(self, config):
        self.budgets = {
            "claude": config.limits.claude_daily_budget,
            "codex": config.limits.codex_daily_budget,
            "gemini": config.limits.gemini_daily_budget,
        }
        self._load_today()
    
    def _load_today(self):
        """Zlicza dzisiejsze wywołania z analytics.jsonl."""
        today = date.today().isoformat()
        self.today_usage = {"claude": 0, "codex": 0, "gemini": 0}
        for line in read_jsonl(".flowtui/analytics.jsonl"):
            if line["timestamp"].startswith(today):
                self.today_usage[line["tool"]] += 1
    
    def record(self, tool: str):
        self.today_usage[tool] += 1
    
    def get_display(self) -> str:
        """Formatuje na panel LIMITS."""
        lines = []
        for tool in ["claude", "codex", "gemini"]:
            used = self.today_usage[tool]
            budget = self.budgets[tool]
            pct = used / budget if budget > 0 else 0
            bar = "█" * int(pct * 10) + "░" * (10 - int(pct * 10))
            warn = " ⚠" if pct > 0.8 else ""
            lines.append(f"  {tool:8s} {bar} {used}/{budget}{warn}")
        return "\n".join(lines)
    
    def should_warn(self, tool: str) -> bool:
        return self.today_usage[tool] >= self.budgets[tool] * 0.8
```

Budżety (`claude_daily_budget` itd.) to **user-configured** wartości — FlowTUI nie ma dostępu do realnych API limitów. User kalibruje po pierwszym tygodniu.

Rozbudowane analytics (dashboardy, cost estimation, trendy, eksport): → `docs/flowtui/analytics-spec.md`

---

## Dry-run & testing

### Dry-run mode

```bash
> run TASK-001 --dry-run
```

Wyświetla co FlowTUI *zrobiłby* bez wywoływania AI:

```
[dry-run] Would invoke codex:
  Command: codex exec --full-auto "..."
  Prompt: [2400 chars, ~600 tokens]
  Context files: AGENTS.md, docs/tasks/TASK-001.md
  Working dir: /home/maciek/projects/docflow
  
[dry-run] Then would invoke gemini:
  Command: gemini --yolo "..."
  Prompt: [review of git diff]
```

### Testowanie FlowTUI

```python
# tests/test_orchestrator.py

class MockCLI:
    """Fake CLI subprocess — zwraca predefiniowane outputy."""
    
    def __init__(self, responses: dict[str, str]):
        self.responses = responses  # {"codex": "OK", "gemini": "review ok"}
        self.calls = []
    
    async def invoke(self, tool: str, prompt: str) -> InvocationResult:
        self.calls.append((tool, prompt))
        return InvocationResult(
            tool=tool, exit_code=0,
            stdout=self.responses.get(tool, ""),
            stderr="", duration_sec=1.0,
            files_changed=[], lines_added=10, lines_removed=2,
            tests_passed=True,
        )

async def test_run_task_happy_path():
    mock = MockCLI({"codex": "done", "gemini": "review ok"})
    result = await run_task("TASK-001", cli=mock)
    assert result.status == "DONE"
    assert len(mock.calls) == 2  # codex + gemini

async def test_run_task_retry():
    mock = MockCLI({"codex": "error", "gemini": "review ok"})
    mock.first_call_fails = True  # first codex call fails
    result = await run_task("TASK-001", cli=mock)
    assert len(mock.calls) >= 3  # codex fail + codex retry + gemini
```

`invoke_and_measure()` przyjmuje opcjonalny `cli` parameter — w testach wstrzykiwany mock, w produkcji prawdziwy subprocess.

---

## Multi-project support

```toml
# ~/.flowtui/projects.toml
[projects]
docflow = "~/projects/docflow"
drop = "~/projects/drop"
mailmind = "~/projects/mailmind"
```

```
switch docflow    # zmienia CWD + ładuje config
projects          # lista projektów ze statusem
```

Każdy projekt ma własny `.flowtui/config.toml`, `CLAUDE.md`, `AGENTS.md`. Zero shared state.

---

## Milestones

### M1: Fundament (1 tydzień)
- [ ] Struktura projektu Python + Textual
- [ ] `flowtui init` — scaffold nowego projektu
- [ ] Parsowanie .flowtui/config.toml + routing.toml
- [ ] Parsowanie task files (TASK-XXX.md)
- [ ] Wyświetlanie listy tasków w TUI
- [ ] Panel LIMITS (prosty licznik wywołań/budget)
- [ ] Logging do analytics.jsonl (append-only)
- [ ] Startup: auto-update CLI tools (parallel)
- [ ] Startup: weryfikacja narzędzi w PATH
- [ ] Komenda `status`, `limits`
- [ ] Komenda `update` (manual CLI update)

### M2: AI Integration (1 tydzień)
- [ ] `invoke_and_measure()` — subprocess wrapper z git diff measurement
- [ ] Komendy: `code`, `review`
- [ ] `plan` z complexity routing (trivial/simple/complex)
- [ ] Planning pipeline: Codex draft → CC stress + Gemini validate → Codex fix
- [ ] CC stress test z severity (blocking/important/suggestion)
- [ ] Iteracja 2 (CC re-review) + eskalacja blocking do usera
- [ ] Context injection (build_prompt z szablonów)
- [ ] Gemini validation context builder (reverse deps, testy)
- [ ] Gemini change summary (human-readable opis zmian)
- [ ] Task report tabela po każdym tasku
- [ ] Streaming output do panelu TERMINAL
- [ ] Dry-run mode (`--dry-run`)
- [ ] Timeout (5 min per call)

### M3: Automation (1 tydzień)
- [ ] Komenda `run TASK-XXX` (pełny cykl z verify wbudowanym)
- [ ] Selektywny deep review CC (`needs_deep_review()`)
- [ ] Retry logic (MAX_RETRY=2, rollback na fail)
- [ ] Circuit breaker w `run sprint` (3 consecutive fails → stop, bez pytania usera)
- [ ] Sprint summary z "następne kroki" (Gemini generuje)
- [ ] Komenda `run "feature"` — end-to-end (plan → approve → sprint → merge → summary)
- [ ] `plan --approve` / `plan --reject` (DRAFT → TODO / usunięcie)
- [ ] Plan tabelka jako checkpoint (show_plan_table)
- [ ] Komenda `merge` / `merge TASK-XXX`
- [ ] Untestable acceptance criteria flagging
- [ ] Git branch isolation per task
- [ ] Pre-commit checkpoint
- [ ] Git conflict detection (abort + inform)
- [ ] Auto-update statusu tasków
- [ ] Watchdog na docs/tasks/ (live refresh)

### M4: Context & Analytics (1 tydzień)
- [ ] Context briefing system (`build_cc_briefing`)
- [ ] Auto-update CLAUDE.md "Bieżący stan"
- [ ] Komendy `stats`, `stats compare`, `stats cost`
- [ ] Panel STATS rozszerzony (trendy tygodniowe)
- [ ] Auto-alerty (retry rate, usage, cost thresholds)
- [ ] Multi-project support (`switch`, `projects`)

### M5: Polish (3-5 dni)
- [ ] Eksport analytics CSV/JSON
- [ ] Komenda `stats tool <n>` (deep dive)
- [ ] Human-in-the-loop research flow
- [ ] Error handling edge cases
- [ ] Konfigurowalny layout paneli
- [ ] Mock CLI dla testów

**Backlog (po v1):**
- Self-modifying workflow (`optimize`, `apply optimization`) → `docs/flowtui/self-modifying-workflow.md`
- API cost estimation → `docs/flowtui/analytics-spec.md`
- Komenda `design` (v0 integration)
- Parallel execution (Codex koduje + Gemini reviewuje jednocześnie)

---

## Ryzyka

| Ryzyko | P | I | Mitygacja |
|--------|---|---|-----------|
| Agent w bypass mode usunie/nadpisze pliki | M | H | Git branch isolation + checkpoint + rollback |
| ~~Codex CLI batch mode niższa jakość niż interaktywny~~ | — | — | **ZWALIDOWANE: 5/5 tasków ✅, 0 retries** |
| Codex Plus weekly limit za mały na pipeline | H | M | 5 tasków = 24% weekly. ~7 tasków/tyg w pipeline. Upgrade do Pro gdy >1 projekt aktywny |
| CC Max 5x ($100) za mało limitu na planowanie | M | M | Panel LIMITS monitoruje. CC głównie planning — oszczędzaj na review |
| CLI output format zmiana przy update | M | M | Nie parsujemy stdout — mierzymy efekty z git diff |
| Budowanie TUI opóźnia produkty (Drop, DocFlow) | H | H | M1+M2 w 2 tygodnie albo abandon. Strict scope. |
| Gemini review nie łapie błędów jak Opus | M | L | Opcjonalny `review --deep` przez CC |

## Decyzje do podjęcia przed implementacją

1. ~~**CC Pro ($20) vs Max 5x ($100)?**~~ → **Max 5x ($100)** — orkiestrator, potrzebny headroom.
2. **Codex `--auto-edit` vs `--full-auto`?** — Test oba na 3 taskach w M2.
3. ~~**Gemini free vs AI Pro ($20)?**~~ → **Free tier** (1000 req/dzień) — upgrade gdy >30 review/dzień.
4. ~~**Codex Plus ($20) vs Pro ($200)?**~~ → **Plus ($20)** — zwalidowany, ~7 tasków/tyg w pipeline. Upgrade do Pro gdy >1 projekt aktywny.

## Metryki sukcesu (po 2 tygodniach)

- Claude Code zużycie: **spadek o ≥50%** vs baseline
- Tasków zamkniętych dziennie: **wzrost o ≥30%**
- Context switching (ręczne kopiowanie): **zero**
- Czas od task spec do implementacji: **<15 min** per task

---

## Powiązane dokumenty

| Dokument | Opis | Kiedy potrzebny |
|----------|------|-----------------|
| `docs/flowtui/planning-prompts.md` | Prompty per fazę planning pipeline, parsowanie severity | M2 |
| `docs/flowtui/analytics-spec.md` | Pełna spec dashboardów, cost estimation, eksport, alerty | M4-M5 |
| `docs/flowtui/bypass-permissions.md` | Konfiguracja bypass per tool, flagi, bezpieczeństwo | Przed M2 |
| `docs/flowtui/context-management.md` | CC briefing, token budgets, reguły kondensacji | M4 |
| `docs/flowtui/self-modifying-workflow.md` | Opus jako meta-architekt, `optimize` command | Backlog (po v1) |

---

## Manifest plików — kompletna lista do wrzucenia w projekt

Wszystkie pliki potrzebne do rozpoczęcia implementacji w Claude Code:

```
flowtui/
├── FlowTUI-PRD-v1.md                          # ← TEN PLIK — główna specyfikacja
├── docs/
│   └── flowtui/
│       ├── planning-prompts.md                 # Prompty do pipeline (CC stress test, Gemini validate, Codex draft/fix)
│       ├── analytics-spec.md                   # Dashboardy, cost estimation, eksport (M4+)
│       ├── bypass-permissions.md               # Bypass config per tool (przed M2)
│       ├── context-management.md               # CC briefing system, token budgets (M4)
│       └── self-modifying-workflow.md           # Opus meta-architect (backlog)
```

**Łącznie: 6 plików.**

### Kolejność wrzucania

1. **Przed M1:** `FlowTUI-PRD-v1.md` (core spec)
2. **Przed M2:** `bypass-permissions.md` + `planning-prompts.md`
3. **M4:** `context-management.md` + `analytics-spec.md`
4. **Backlog:** `self-modifying-workflow.md`
