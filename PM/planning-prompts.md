# FlowTUI — Planning Pipeline Prompts

Prompty per fazę pipeline'u planowania. Referencja z PRD v2.

---

## FAZA 1: Draft (Codex)

```python
DRAFT_PROMPT = """Przeczytaj opis feature'a i istniejący kod.
Zaplanuj implementację jako listę tasków w docs/tasks/TASK-XXX.md.

Dla każdego taska podaj:
- Tytuł
- Kontekst (dlaczego ten task, jak wpasowuje się w feature)
- Pliki do modyfikacji (istniejące) i pliki do stworzenia (nowe)
- Zależności od innych tasków
- Priority: high/medium/low
- Assigned: codex (domyślnie)

NIE implementuj — tylko planuj.
NIE podejmuj decyzji architektonicznych jeśli nie są oczywiste — oznacz je jako pytanie.

Feature: {description}"""
```

## FAZA 2a: Stress test (CC Opus)

```python
STRESS_TEST_PROMPT = """Jesteś krytykiem technicznym. Znajdź problemy w planie implementacji.

Plan:
{draft_tasks}

Architektura projektu:
{architecture}

Sprawdź:
1. BRAKUJĄCE TASKI — co jest potrzebne ale niezaplanowane?
2. ZALEŻNOŚCI — czy kolejność tasków ma sens? Czy są cykliczne zależności?
3. RYZYKO — co może się wysypać? (edge cases, wydajność, integracja, bezpieczeństwo)
4. DECYZJE — jakie decyzje architektoniczne nie zostały podjęte?
5. SCOPE — czy któryś task jest za duży i wymaga rozbicia?
6. KRYTERIA — czy acceptance criteria są automatycznie testowalne?
   Flaguj: "otwiera się poprawnie", "wygląda dobrze", "responsywny", "płynnie".
   Zamień na: exit codes, rozmiary plików, grep patterns, HTTP status codes.

Dla każdego problemu oznacz severity:
- [BLOCKING] plan nie może być realizowany bez rozwiązania (brak decyzji arch, fundamentalny konflikt)
- [IMPORTANT] plan zadziała ale będzie miał problemy (brak testów, edge case, ryzyko)
- [SUGGESTION] nice-to-have, nie blokuje

Maks 10 problemów. Nie proponuj rozwiązań — tylko problemy.

Format:
[BLOCKING] category: opis problemu
[IMPORTANT] category: opis problemu
[SUGGESTION] category: opis problemu

Kategorie: missing_decision | missing_task | dependency | risk | scope | conflict"""
```

## FAZA 2b: Validate (Gemini)

```python
VALIDATE_PROMPT = """Sprawdź plan implementacji pod kątem spójności z istniejącym kodem.

Plan (draft):
{draft_tasks}

Problemy z review architektonicznego:
{stress_issues}

Istniejący kod:
{existing_code}

Sprawdź:
1. KONFLIKTY — czy plan nadpisuje/duplikuje coś co już istnieje?
   (np. plan mówi "stwórz PdfService" ale PdfService już jest w src/legacy/)
2. KONWENCJE — czy nowy kod trzyma się wzorców z repo?
   (nazewnictwo, struktura plików, pattern state management)
3. TESTY — czy plan pokrywa regresje na istniejący kod?
   (modyfikowane pliki mają testy — czy plan aktualizuje te testy?)
4. INTERFEJSY — czy sygnatury się zgadzają z callerami?
   (pliki które importują modyfikowane pliki — czy będą działać po zmianach?)
5. MIGRACJA — czy zmiana wymaga update'u istniejących callerów?

Maks 10 problemów.
Format: [severity] plik:kontekst — opis problemu

Severity: BLOCKING | IMPORTANT | SUGGESTION"""
```

## FAZA 3: Fix (Codex)

```python
FIX_PROMPT = """Popraw plan tasków na podstawie dwóch review.

Review architektoniczny (stress test):
{stress_issues}

Review spójności z kodem (validation):
{validation_issues}

Dla KAŻDEGO zgłoszonego problemu:
- BLOCKING/IMPORTANT: napraw w taskach (zmień pliki, dodaj task, zmień kolejność)
- SUGGESTION: dodaj jako komentarz w relevantnym tasku

Zaktualizuj pliki tasków w docs/tasks/.
Dodaj brakujące taski jeśli potrzebne.
Napraw zależności i kolejność.
Oznacz w ## Log co zostało zmienione i dlaczego.

NIE ignoruj problemów. Jeśli nie wiesz jak rozwiązać BLOCKING problem — 
zostaw go z komentarzem "WYMAGA DECYZJI USERA: [opis]"."""
```

## FAZA 4: Re-review (CC Opus, warunkowa)

```python
RE_REVIEW_PROMPT = """Zgłosiłeś te BLOCKING problemy w planie:
{blocking_issues}

Codex poprawił plan. Aktualne taski:
{updated_tasks_compact}

Czy blocking issues zostały rozwiązane? Dla każdego:
- [RESOLVED] jeśli naprawione
- [STILL_BLOCKING] jeśli nadal problem + dlaczego

Tylko blocking issues. Maks 200 słów."""
```

---

## Parsowanie severity z outputu CC

```python
import re

def parse_stress_issues(output: str) -> list[StressIssue]:
    issues = []
    pattern = r'\[(BLOCKING|IMPORTANT|SUGGESTION)\]\s*(\w+):\s*(.+)'
    
    for match in re.finditer(pattern, output):
        issues.append(StressIssue(
            severity=match.group(1).lower(),
            category=match.group(2).lower(),
            description=match.group(3).strip(),
        ))
    
    # Fallback: jeśli CC nie trzyma się formatu, traktuj cały output jako important
    if not issues and output.strip():
        issues.append(StressIssue(
            severity="important",
            category="unknown",
            description=f"Unparsed review: {output[:500]}",
        ))
    
    return issues
```

## Budowanie kontekstu per faza

```python
def build_plan_context(phase: str, draft_tasks=None, issues=None) -> str:
```

---

## Prompty poza pipeline'em planowania

### Change summary (Gemini — po implementacji)

```python
SUMMARY_PROMPT = """Przeczytaj diff i opisz zmiany w 2-3 zdaniach.
Biznesowy opis, nie techniczny. Co zostało dodane/zmienione z perspektywy feature'a.
Wymień nowe klasy/metody po nazwie.

Diff:
{diff}"""
```

### Deep review (CC — tylko complex taski)

```python
DEEP_REVIEW_PROMPT = """Zrób review logiki implementacji. Nie sprawdzaj stylu ani konwencji — to robi Gemini.

Sprawdź:
1. LOGIKA — czy algorytm/flow jest poprawny? Czy edge cases obsłużone?
2. ARCHITEKTURA — czy implementacja jest spójna z resztą systemu?
3. BEZPIECZEŃSTWO — injection, auth bypass, race conditions?
4. WYDAJNOŚĆ — O(n²) w pętli, brak paginacji, memory leaks?

Diff:
{diff}

Architektura projektu:
{architecture}

Format: lista problemów z severity (critical/warning/info).
Jeśli OK — napisz "OK" i 1 zdanie dlaczego implementacja jest poprawna."""
```
    """Buduje kontekst zależny od fazy pipeline'u."""
    
    if phase == "draft":
        return read_file("AGENTS.md") + "\n" + tree("src/", max_depth=3)
    
    elif phase == "stress_test":
        # CC: draft + architektura. NIE kod (za drogo).
        tasks_compact = format_tasks_compact(draft_tasks)
        arch = read_file("docs/architecture.md")[:2000]
        return f"## Taski\n{tasks_compact}\n\n## Architektura\n{arch}"
    
    elif phase == "validate":
        # Gemini: draft + issues + CAŁY relevant kod (1M context)
        return build_gemini_validation_context(draft_tasks)
    
    elif phase == "fix":
        # Codex: draft + oba zestawy issues
        return format_all_issues(issues)
    
    elif phase == "re_review":
        # CC: tylko blocking + compact updated tasks (~500 tok)
        return format_tasks_compact(draft_tasks)
```
