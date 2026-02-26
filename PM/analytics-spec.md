# FlowTUI — Analytics & Cost Optimization (Spec)

Wyciągnięte z PRD. Implementacja: M4 (Context & Analytics).

---

## Cel

FlowTUI jest jedynym punktem który widzi wszystkie wywołania AI. Zbiera metryki, buduje historię, umożliwia porównania i optymalizację kosztów w czasie.

## Zbieranie danych

Każde wywołanie AI logowane do `.flowtui/analytics.jsonl` (append-only):

```json
{
  "id": "inv-20260226-143012-001",
  "timestamp": "2026-02-26T14:30:12Z",
  "tool": "codex",
  "model": "gpt-5-codex",
  "action": "code",
  "task_id": "TASK-001",
  "project": "docflow",
  "sprint": "sprint-003",
  
  "input": {
    "prompt_chars": 2400,
    "prompt_tokens_est": 600,
    "context_files": ["AGENTS.md", "docs/tasks/TASK-001.md"],
    "context_chars": 3200,
    "context_tokens_est": 800,
    "total_tokens_est": 1400
  },
  
  "output": {
    "response_chars": 4800,
    "response_tokens_est": 1200,
    "files_created": ["src/services/pdf_service.dart"],
    "files_modified": ["src/models/document.dart"],
    "lines_added": 87,
    "lines_removed": 12
  },
  
  "quality": {
    "exit_code": 0,
    "tests_run": true,
    "tests_passed": true,
    "review_result": "ok",
    "retry_count": 0
  },
  
  "timing": {
    "duration_sec": 45,
    "wait_for_human_sec": 0
  }
}
```

## Metryki per narzędzie (CLI parsery)

```python
async def collect_metrics(tool: str, process, start_time: float) -> dict:
    duration = time.time() - start_time
    
    # Git diff — co agent zmienił
    diff_stat = await bash("git diff --stat HEAD")
    lines = parse_diff_stat(diff_stat)

    # Codex — /status jeśli dostępny
    if tool == "codex":
        status = await bash("codex exec --full-auto '/status'")
    
    # Testy — czy przeszły
    test_result = await run_project_tests()
    
    return {
        "duration_sec": duration,
        "lines_added": lines["added"],
        "lines_removed": lines["removed"],
        "files_changed": lines["files"],
        "tests_passed": test_result.passed,
        "exit_code": process.returncode,
    }
```

## Dashboardy w TUI

### Panel STATS (real-time, zawsze widoczny)

```
DZIŚ                    TEN TYDZIEŃ
CC:     ██░░░░  5 sesji    CC:     ████░░  23 sesji
Codex:  ████░░ 12 sesji    Codex:  ██████ 67 sesji  
Gemini: █░░░░░  3 sesji    Gemini: ███░░░ 18 sesji

Tokeny (est.):  input 45k | output 28k | total 73k
Efektywność:    82% tasków DONE bez retry
```

### Komenda: `stats` (podsumowanie)

```
═══ FlowTUI Analytics — DocFlow ═══

OKRES: ostatnie 7 dni (2026-02-19 → 2026-02-26)

WYWOŁANIA
  Claude Code:     23 sesji  │ ~34k tokenów input  │ $est. 12.40
  Codex CLI:       67 sesji  │ ~89k tokenów input  │ $est. 31.20
  Gemini CLI:      18 sesji  │ ~22k tokenów input  │ $est. 2.10
  TOTAL:          108 sesji  │ ~145k tokenów       │ $est. 45.70

EFEKTYWNOŚĆ
  Taski ukończone:           14/18 (78%)
  Retry rate (Codex):        12% (8/67 wymagało ponowienia)
  Review critical (Gemini):  2/18 (11%)
  Avg czas/task:             8.2 min
  Avg wywołania/task:        6.1 (1 CC + 3.8 Codex + 1.3 Gemini)

KOSZT vs SAMODZIELNY CC
  Estymowany koszt (subskrypcje):     $340/mies
  Estymowany koszt API equivalent:    $182/mies
  CC-only equivalent (gdybyś wszystko robił w CC): ~$520/mies API
  Oszczędność vs CC-only:            35%

TRENDY
  Codex retry rate:  ↓ 18% → 12% (poprawa po optymalizacji promptów)
  CC zużycie:        ↓ 31 → 23 sesji/tyg (skuteczna delegacja)
  Avg czas/task:     ↓ 12.1 → 8.2 min
```

### Komenda: `stats compare` (porównanie okresów)

```
═══ Porównanie: ten tydzień vs poprzedni ═══

                        PREV      NOW       ZMIANA
CC sesji/tyg:            31        23       ↓ -26% ✅
Codex sesji/tyg:         54        67       ↑ +24%
Gemini sesji/tyg:        22        18       ↓ -18%
Taski done/tyg:          11        14       ↑ +27% ✅
Retry rate (Codex):      18%       12%      ↓ -6pp ✅
Avg czas/task:           12.1m     8.2m     ↓ -32% ✅
Est. koszt tygodniowy:   $98       $86      ↓ -12% ✅
```

### Komenda: `stats cost` (analiza kosztów)

```
═══ Analiza kosztów — Luty 2026 ═══

SUBSKRYPCJE (stałe)
  CC Max 5x:        $100.00
  Codex Pro:        $200.00
  Gemini AI Pro:     $20.00
  Perplexity Pro:    $20.00
  ──────────────────────────
  TOTAL:            $340.00

ZUŻYCIE vs LIMIT (estymacja)
  CC:     ████░░░░░░  42% limitu    ← masz zapas
  Codex:  ███████░░░  71% limitu    ← pod kontrolą
  Gemini: ██░░░░░░░░  15% limitu    ← mocno niewykorzystany

REKOMENDACJE
  ⚠ Gemini na 15% — rozważ Free tier zamiast AI Pro ($20 oszczędności)
  ⚠ CC na 42% — rozważ Pro ($20) zamiast Max 5x ($100)
  ✅ Codex na 71% — dobrze dobrana rola

POTENCJALNA OSZCZĘDNOŚĆ: $100/mies
  CC Max 5x → Pro:     -$80
  Gemini Pro → Free:   -$20
  Nowy total:          $240/mies
```

### Komenda: `stats tool <narzędzie>` (deep dive)

```
═══ Codex CLI — szczegóły (ostatnie 7 dni) ═══

MODEL USAGE
  gpt-5-codex:        45 sesji (67%)
  gpt-5.1-codex-mini: 22 sesji (33%)

PER ACTION
  code:      48 sesji │ retry 10% │ avg 52s
  test:      12 sesji │ retry 8%  │ avg 28s
  refactor:   7 sesji │ retry 21% │ avg 71s  ← problem!

PER PROJEKT
  DocFlow:   41 sesji │ retry 9%
  Drop:      18 sesji │ retry 17%  ← gorszy na iOS/Flutter
  MailMind:   8 sesji │ retry 12%

RETRY ANALYSIS
  Top przyczyny retry:
  1. Testy nie przechodzą (5x) — głównie state management
  2. Wrong file modified (2x) — AGENTS.md zbyt ogólny
  3. Timeout (1x) — duży plik >500 LOC

CONTEXT SIZE vs SUCCESS
  <1000 tok context:  95% success rate
  1000-3000 tok:      88% success rate
  >3000 tok:          72% success rate  ← za duży kontekst = gorsze wyniki
```

## Estymacja kosztów API equivalent

```python
API_PRICES = {
    "claude": {
        "opus": {"input": 15.0, "output": 75.0, "cache_read": 1.5},
        "sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
    },
    "codex": {
        "gpt-5-codex": {"input": 1.25, "output": 10.0},
        "gpt-5.1-codex-mini": {"input": 1.50, "output": 6.0},
    },
    "gemini": {
        "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
        "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    },
}

def estimate_api_cost(invocations: list[dict]) -> dict:
    total = 0
    per_tool = {}
    for inv in invocations:
        tool = inv["tool"]
        model = inv.get("model", "default")
        prices = API_PRICES[tool][model]
        input_cost = (inv["input"]["total_tokens_est"] / 1_000_000) * prices["input"]
        output_cost = (inv["output"]["response_tokens_est"] / 1_000_000) * prices["output"]
        cost = input_cost + output_cost
        total += cost
        per_tool[tool] = per_tool.get(tool, 0) + cost
    return {"total": total, "per_tool": per_tool}
```

## Eksport danych

```bash
> stats export csv   # → .flowtui/exports/analytics-2026-02.csv
> stats export json  # → .flowtui/exports/analytics-2026-02.json
```

## Auto-alerty

```toml
# .flowtui/config.toml
[alerts]
codex_retry_rate_warn = 0.20
cc_usage_warn = 0.70
cost_monthly_warn = 400
task_duration_warn = 900
gemini_underuse_warn = 0.20
```
