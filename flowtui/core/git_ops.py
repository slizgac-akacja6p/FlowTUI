"""Git operations via asyncio subprocess."""

import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiffStat:
    """Parsed output of git diff --stat."""
    files_changed: int
    insertions: int
    deletions: int
    raw: str  # raw output from git diff --stat


@dataclass
class MergeResult:
    """Result of a merge operation."""
    success: bool
    conflicts: list[str] = field(default_factory=list)  # files with merge conflicts
    message: str = ""


class GitOps:
    """Manage git operations via asyncio subprocess."""

    def __init__(self, project_root: Path):
        """Initialize GitOps for a project root."""
        self.project_root = project_root

    async def _run(self, *args: str) -> tuple[int, str, str]:
        """Run git command, return (returncode, stdout, stderr).

        Strips CLAUDECODE from environment to allow nested CC invocations.
        """
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=self.project_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode(errors="replace").strip(), stderr.decode(errors="replace").strip()

    async def current_branch(self) -> str:
        """Return current branch name."""
        returncode, stdout, stderr = await self._run("rev-parse", "--abbrev-ref", "HEAD")
        if returncode != 0:
            raise RuntimeError(f"Failed to get current branch: {stderr}")
        return stdout

    async def has_changes(self) -> bool:
        """Return True if there are uncommitted changes."""
        returncode, stdout, _ = await self._run("status", "--porcelain")
        if returncode != 0:
            raise RuntimeError("Failed to check git status")
        return bool(stdout)

    async def get_head_hash(self) -> str:
        """Return current HEAD hash (used as pre_hash for rollback)."""
        returncode, stdout, stderr = await self._run("rev-parse", "HEAD")
        if returncode != 0:
            raise RuntimeError(f"Failed to get HEAD hash: {stderr}")
        return stdout

    async def create_branch(self, name: str) -> None:
        """Create and checkout new branch.

        Raises RuntimeError on failure.
        """
        returncode, _, stderr = await self._run("checkout", "-b", name)
        if returncode != 0:
            raise RuntimeError(f"Failed to create branch {name}: {stderr}")

    async def checkout(self, branch: str) -> None:
        """Checkout existing branch.

        Raises RuntimeError on failure.
        """
        returncode, _, stderr = await self._run("checkout", branch)
        if returncode != 0:
            raise RuntimeError(f"Failed to checkout {branch}: {stderr}")

    async def checkpoint(self, msg: str) -> str:
        """git add -A + git commit -m msg.

        Returns commit hash.
        Raises RuntimeError on failure.
        """
        # Stage all changes
        returncode, _, stderr = await self._run("add", "-A")
        if returncode != 0:
            raise RuntimeError(f"Failed to stage changes: {stderr}")

        # Commit
        returncode, stdout, stderr = await self._run("commit", "-m", msg)
        if returncode != 0:
            raise RuntimeError(f"Failed to commit: {stderr}")

        # Extract commit hash from output (git commit outputs hash on success)
        hash_match = re.search(r"\[.+?([a-f0-9]{7})", stdout)
        if hash_match:
            return hash_match.group(1)

        # Fallback: get HEAD hash
        return await self.get_head_hash()

    async def rollback(self, pre_hash: str) -> None:
        """git reset --hard pre_hash.

        Raises RuntimeError on failure.
        """
        returncode, _, stderr = await self._run("reset", "--hard", pre_hash)
        if returncode != 0:
            raise RuntimeError(f"Failed to rollback to {pre_hash}: {stderr}")

    async def diff_stat(self, base: str | None = None) -> DiffStat:
        """Run git diff --stat, parse output → DiffStat.

        If base is None: diff working tree vs HEAD (uncommitted changes).
        If base is provided: diff base..HEAD (committed changes on branch).
        """
        if base is not None:
            returncode, stdout, stderr = await self._run("diff", "--stat", f"{base}..HEAD")
        else:
            returncode, stdout, stderr = await self._run("diff", "--stat", "HEAD")
        if returncode != 0:
            raise RuntimeError(f"Failed to get diff stat: {stderr}")

        raw = stdout
        files_changed = 0
        insertions = 0
        deletions = 0

        # Parse summary line: "X files changed, Y insertions(+), Z deletions(-)"
        # Example: "3 files changed, 25 insertions(+), 10 deletions(-)"
        summary_match = re.search(
            r"(\d+)\s+files?\s+changed,\s+(\d+)\s+insertions?\(\+\),\s+(\d+)\s+deletions?\(-\)",
            stdout,
        )
        if summary_match:
            files_changed = int(summary_match.group(1))
            insertions = int(summary_match.group(2))
            deletions = int(summary_match.group(3))

        return DiffStat(
            files_changed=files_changed,
            insertions=insertions,
            deletions=deletions,
            raw=raw,
        )

    async def merge_to(self, target: str, source: str) -> MergeResult:
        """Checkout target, then git merge --no-ff source.

        On conflict: git merge --abort, restore original branch, return MergeResult(success=False, conflicts=[...]).
        On success: stay on target branch, return MergeResult(success=True).
        """
        original_branch = await self.current_branch()
        try:
            # Checkout target
            returncode, _, stderr = await self._run("checkout", target)
            if returncode != 0:
                raise RuntimeError(f"Failed to checkout {target}: {stderr}")

            # Attempt merge
            returncode, stdout, stderr = await self._run("merge", "--no-ff", source)

            if returncode != 0:
                # Merge failed — likely due to conflicts
                # Get list of conflicted files
                conflict_returncode, conflict_stdout, _ = await self._run(
                    "diff", "--name-only", "--diff-filter=U"
                )
                conflicts = []
                if conflict_returncode == 0 and conflict_stdout:
                    conflicts = conflict_stdout.split("\n")

                # Abort merge
                abort_returncode, _, abort_stderr = await self._run("merge", "--abort")
                if abort_returncode != 0:
                    raise RuntimeError(f"Failed to abort merge: {abort_stderr}")

                # Restore original branch on conflict
                try:
                    await self.checkout(original_branch)
                except Exception:
                    pass

                return MergeResult(
                    success=False,
                    conflicts=conflicts,
                    message=stderr or "Merge conflict detected",
                )

            # On success, stay on target branch (no restore)
            return MergeResult(success=True, message="Merge successful")
        except Exception:
            # On unexpected error, restore and re-raise
            try:
                await self.checkout(original_branch)
            except Exception:
                pass
            raise
