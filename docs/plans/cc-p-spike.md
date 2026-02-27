# SPIKE T2.1: CC -p File Creation Test

## Wynik
**CONFIRMED: CC -p CREATES FILES** — gdy `CLAUDECODE` usunięty z env

## Komenda (SPIKE 2 — finalny)
```bash
cd /tmp/flowtui-spike2
env -u CLAUDECODE claude --dangerously-skip-permissions -p "Create a file named result.txt containing only the word 'created'" --allowedTools Write,Edit
```

## Dowód
```
Plik `result.txt` utworzony.
Exit: 0
-rw-r--r--  1 maciejgajda  wheel  7 result.txt
```

`result.txt` powstał z zawartością `created\n` — CC -p wykonał zapis na dysk przez narzędzie Write.

## Poprzedni wynik (SPIKE 1 — INCONCLUSIVE)
```
Error: Claude Code cannot be launched inside another Claude Code session.
Exit code: 1
```
Przyczyną był guard nested sessions (zmienna `CLAUDECODE`), nie brak zdolności tworzenia plików.

## Analiza blokady
CC ustawia zmienną środowiskową `CLAUDECODE` na czas działania sesji. Każda próba uruchomienia
`claude` wewnątrz tej sesji jest odrzucana z exit code 1 przed wykonaniem jakiegokolwiek promptu.

Obejście sugerowane przez CC: `unset CLAUDECODE` przed wywołaniem subprocess.
To jest możliwe w FlowTUI — `subprocess.Popen` z `env={...}` bez klucza `CLAUDECODE`.

## Implikacje dla T2.5 (Planning Pipeline)

CC -p **tworzy pliki**, ale FlowTUI używa `parser.py` jako primary path — parsuje stdout i tworzy
pliki lokalnie. Jest to architektonicznie czystsza opcja (FlowTUI kontroluje format i lokalizację).

Opcja "CC tworzy pliki sam" (przez Write tool w prompcie) to alternatywa — dostępna w środowisku
produkcyjnym (FlowTUI uruchomiony spoza CC). Nie wdrażamy jako default — zbyt duże ryzyko
rozbieżności formatu, lokalizacji, race conditions.

**Decyzja architektoniczna (finalna):**
- `invoker.py` wywołuje `claude -p` przez subprocess z `env` bez `CLAUDECODE`
- `parser.py` parsuje stdout i tworzy pliki — primary path, obowiązkowy
- Możliwość "CC tworzy pliki sam" = nice-to-have, M5

## Następne kroki
- T2.2: implementacja `invoker.py` z `env` bez `CLAUDECODE` + capture stdout
- T2.5: `parser.py` jako obowiązkowy etap pipeline, nie opcjonalny
