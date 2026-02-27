"""Auto-update CLAUDE.md based on current repository state."""

from pathlib import Path
from flowtui.core.invoker import CLIInvoker


class ClaudeMdUpdater:
    """Updates CLAUDE.md file by calling Claude with current repo context."""

    def __init__(self, project_root: Path, invoker: CLIInvoker):
        """Initialize updater.

        Args:
            project_root: Root directory of the project
            invoker: CLIInvoker instance for calling Claude
        """
        self.project_root = project_root
        self.invoker = invoker
        self.claude_md_path = project_root / "CLAUDE.md"

    async def update(self, dry_run: bool = False) -> str:
        """Update CLAUDE.md based on current repo state.

        Calls Claude with context about current project structure, modules,
        and key files to refresh outdated sections (structure, commands, patterns).

        Args:
            dry_run: If True, return prompt preview without calling Claude

        Returns:
            Claude's response (updated CLAUDE.md content or description of changes)

        Raises:
            RuntimeError: If Claude call fails
        """
        current_content = ""
        if self.claude_md_path.exists():
            current_content = self.claude_md_path.read_text(encoding="utf-8")

        prompt = self._build_prompt(current_content)

        if dry_run:
            return f"[DRY RUN] Would call Claude with prompt:\n{prompt[:500]}..."

        result = await self.invoker.invoke(
            tool="cc",
            args=["--dangerously-skip-permissions", "-p", prompt],
            cwd=self.project_root,
            timeout=120.0,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Claude call failed: {result.stderr}")

        output = result.stdout.strip()
        if not output:
            raise RuntimeError("CC returned empty output — CLAUDE.md not updated")

        # Atomic write: write to tmp, then rename
        tmp_path = self.claude_md_path.with_suffix(".md.tmp")
        try:
            tmp_path.write_text(output, encoding="utf-8")
            tmp_path.rename(self.claude_md_path)
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to write CLAUDE.md: {e}") from e

        return output

    def _build_prompt(self, current_content: str) -> str:
        """Build prompt for Claude to update CLAUDE.md.

        Provides current content and repo structure scan to help Claude
        identify outdated sections.

        Args:
            current_content: Current CLAUDE.md text

        Returns:
            Prompt for Claude
        """
        files_info = self._scan_repo_structure()

        # Truncate content and add note if needed
        if len(current_content) > 2000:
            content_excerpt = current_content[:2000]
            truncation_note = "\n[NOTE: content truncated to 2000 chars — full file has more sections]"
        else:
            content_excerpt = current_content
            truncation_note = ""

        return (
            "Review and update the CLAUDE.md file for this project.\n\n"
            "Current CLAUDE.md content:\n"
            f"```\n{content_excerpt}{truncation_note}\n```\n\n"
            "Current repository structure (key Python modules):\n"
            f"{files_info}\n\n"
            "Update the following sections if they are factually outdated:\n"
            "1. ## Struktura projektu — verify file/module paths match actual repo\n"
            "2. ## Uruchomienie — verify commands still work\n"
            "3. ## Kluczowe wzorce — add any new patterns discovered\n\n"
            "Keep existing content and Polish text intact. Only update what's outdated.\n"
            "Output the complete updated CLAUDE.md file."
        )

    def _scan_repo_structure(self) -> str:
        """Scan project structure and return compact description.

        Scans flowtui/, tests/, and docs/ directories to provide Claude
        with overview of actual module layout.

        Returns:
            Multi-line string describing repo structure
        """
        lines = []

        # Scan main directories for Python files
        for directory in ["flowtui", "tests", "docs"]:
            dir_path = self.project_root / directory
            if dir_path.exists():
                py_files = sorted(dir_path.rglob("*.py"))
                if py_files:
                    # Limit to first 20 files per directory to keep output compact
                    rel_files = [
                        str(f.relative_to(self.project_root)) for f in py_files[:20]
                    ]
                    files_str = ", ".join(rel_files)
                    lines.append(f"{directory}/: {files_str}")

        return "\n".join(lines) if lines else "No Python files found in project"
