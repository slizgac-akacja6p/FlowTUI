# FlowTUI — Bypass Permissions & Autonomous Agents (Spec)

Wyciągnięte z PRD. Konfiguracja wymagana przed M2 (AI Integration).

---

## Zasada

FlowTUI wymaga, aby każdy agent mógł wykonywać bash, edytować pliki i uruchamiać testy bez pytania o pozwolenie. Bez tego orkiestracja się zatrzymuje — FlowTUI nie może kliknąć "y" za użytkownika w subprocess.

## Flagi per narzędzie

### Claude Code

```bash
claude --dangerously-skip-permissions -p "prompt"
```

Config (`~/.claude/settings.json`):
```json
{
  "bypassPermissions": true,
  "skipDangerousModePermissionPrompt": true
}
```

AllowedTools whitelist (`~/.claude.json`):
```json
{
  "permissions": {
    "allow": [
      "Bash(git *)", "Bash(npm *)", "Bash(dart *)", "Bash(flutter *)",
      "Bash(python *)", "Bash(cat *)", "Bash(mkdir *)", "Bash(cp *)",
      "Bash(mv *)", "Read(*)", "Write(*)"
    ],
    "deny": [
      "Bash(rm -rf /)", "Bash(sudo *)", "Bash(curl * | bash)"
    ]
  }
}
```

### Codex CLI

```bash
codex exec --full-auto "prompt"
# lub max:
codex --dangerously-bypass-approvals-and-sandbox "prompt"  # alias: --yolo
```

Config (`~/.codex/config.toml`):
```toml
[defaults]
approval_policy = "never"
sandbox_mode = "workspace-write"   # rekomendacja: nie "danger-full-access"
```

### Gemini CLI

```bash
gemini --yolo "prompt"
# lub: gemini --approval-mode=yolo -y "prompt"
```

Config (`~/.gemini/settings.json`):
```json
{
  "autoAccept": true,
  "tools": {
    "allowed": [
      "run_shell_command(git *)", "run_shell_command(npm test)",
      "run_shell_command(dart *)", "run_shell_command(flutter test *)",
      "write_file", "replace"
    ]
  }
}
```

Gemini `--yolo` domyślnie włącza sandbox (Docker). Bez Dockera: `--sandbox=false`.

## Konfiguracja FlowTUI (invoke_ai)

```python
TOOL_COMMANDS = {
    "claude": ["claude", "--dangerously-skip-permissions", "-p"],
    "codex": ["codex", "exec", "--full-auto"],
    "gemini": ["gemini", "--yolo", "--sandbox=false"],
}
```

## Non-interactive modes

| Narzędzie | Tryb | Flaga |
|-----------|------|-------|
| Claude Code | Print mode | `-p "prompt"` |
| Codex CLI | Exec mode | `exec --full-auto "prompt"` |
| Gemini CLI | Prompt arg | `--yolo "prompt"` |

## Bezpieczeństwo

1. **Git branch isolation**: Każdy task = feature branch. Agent nie pisze do main/develop.
2. **Pre-commit snapshot**: Przed każdym wywołaniem agenta — `git commit` jako checkpoint. KRYTYCZNE dla Codex `--auto-edit`.
3. **Rollback**: `git reset --hard HEAD~1`
4. **Working directory lock**: Agent dostaje `cwd=project_root` — nie widzi nic poza repo.
5. **Timeout**: Agent wisi >5 min → kill.
