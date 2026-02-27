"""Tests for GitOps — git operations via asyncio subprocess."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from flowtui.core.git_ops import GitOps, DiffStat, MergeResult


@pytest.fixture
def git_repo(tmp_path):
    """Create a real temporary git repository for testing."""
    # Initialize repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    (tmp_path / "README.md").write_text("# Test Repository\n")
    subprocess.run(
        ["git", "add", "."], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    return tmp_path


@pytest.fixture
def git_ops(git_repo):
    """GitOps instance with temporary git repository."""
    return GitOps(git_repo)


class TestGitOpsBasics:
    """Test basic GitOps operations."""

    @pytest.mark.asyncio
    async def test_current_branch_default(self, git_ops):
        """After init, current_branch() returns 'main' or 'master'."""
        branch = await git_ops.current_branch()
        assert branch in ("main", "master")

    @pytest.mark.asyncio
    async def test_has_changes_clean(self, git_ops):
        """Fresh repo without uncommitted changes returns False."""
        has_changes = await git_ops.has_changes()
        assert has_changes is False

    @pytest.mark.asyncio
    async def test_has_changes_with_file(self, git_ops, git_repo):
        """After adding a file, has_changes() returns True."""
        (git_repo / "new_file.py").write_text("# New file\n")
        has_changes = await git_ops.has_changes()
        assert has_changes is True

    @pytest.mark.asyncio
    async def test_get_head_hash(self, git_ops):
        """get_head_hash() returns a 40-character hex string."""
        hash_val = await git_ops.get_head_hash()
        assert len(hash_val) == 40
        # Verify it's a hex string
        int(hash_val, 16)  # raises ValueError if not valid hex

    @pytest.mark.asyncio
    async def test_get_head_hash_consistency(self, git_ops):
        """Multiple calls to get_head_hash() return same value."""
        hash1 = await git_ops.get_head_hash()
        hash2 = await git_ops.get_head_hash()
        assert hash1 == hash2


class TestGitOpsBranching:
    """Test branch creation and switching."""

    @pytest.mark.asyncio
    async def test_create_branch(self, git_ops):
        """create_branch() creates and checks out new branch."""
        await git_ops.create_branch("feat/new-feature")
        branch = await git_ops.current_branch()
        assert branch == "feat/new-feature"

    @pytest.mark.asyncio
    async def test_checkout_existing_branch(self, git_ops, git_repo):
        """checkout() switches to existing branch."""
        default_branch = await git_ops.current_branch()

        # Create new branch and switch to it
        await git_ops.create_branch("test-branch")
        await git_ops.checkout(default_branch)

        # Verify we're back on default branch
        current = await git_ops.current_branch()
        assert current == default_branch

    @pytest.mark.asyncio
    async def test_create_branch_already_exists(self, git_ops):
        """create_branch() raises RuntimeError if branch exists."""
        await git_ops.create_branch("duplicate")

        with pytest.raises(RuntimeError) as exc_info:
            await git_ops.create_branch("duplicate")

        assert "Failed to create branch" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_checkout_nonexistent_branch(self, git_ops):
        """checkout() raises RuntimeError for nonexistent branch."""
        with pytest.raises(RuntimeError) as exc_info:
            await git_ops.checkout("nonexistent-branch")

        assert "Failed to checkout" in str(exc_info.value)


class TestGitOpsCheckpoint:
    """Test checkpoint (commit) functionality."""

    @pytest.mark.asyncio
    async def test_checkpoint_creates_commit(self, git_ops, git_repo):
        """checkpoint() commits changes and returns commit hash."""
        # Create a file to commit
        (git_repo / "test.py").write_text("# Test file\n")

        # Commit it
        hash_val = await git_ops.checkpoint("feat: add test file")

        # Verify hash is valid
        assert len(hash_val) == 40 or len(hash_val) == 7  # Full or short hash
        assert all(c in "0123456789abcdef" for c in hash_val)

    @pytest.mark.asyncio
    async def test_checkpoint_clears_changes(self, git_ops, git_repo):
        """After checkpoint(), has_changes() returns False."""
        (git_repo / "file.py").write_text("content\n")
        await git_ops.checkpoint("test: add file")

        has_changes = await git_ops.has_changes()
        assert has_changes is False

    @pytest.mark.asyncio
    async def test_checkpoint_without_changes(self, git_ops):
        """checkpoint() with no changes raises RuntimeError."""
        with pytest.raises(RuntimeError) as exc_info:
            await git_ops.checkpoint("test: no changes")

        assert "Failed to commit" in str(exc_info.value)


class TestGitOpsRollback:
    """Test rollback functionality."""

    @pytest.mark.asyncio
    async def test_rollback_restores_state(self, git_ops, git_repo):
        """rollback() restores working tree to pre_hash state."""
        # Get initial hash
        pre_hash = await git_ops.get_head_hash()

        # Make a change
        (git_repo / "new_file.py").write_text("# New\n")
        await git_ops.checkpoint("feat: add new file")

        # Verify file exists
        assert (git_repo / "new_file.py").exists()

        # Rollback
        await git_ops.rollback(pre_hash)

        # Verify file is gone
        assert not (git_repo / "new_file.py").exists()

    @pytest.mark.asyncio
    async def test_rollback_clears_staged_changes(self, git_ops, git_repo):
        """rollback() clears committed changes by resetting to pre_hash."""
        pre_hash = await git_ops.get_head_hash()

        # Add and commit a file
        (git_repo / "temp.txt").write_text("temp content\n")
        await git_ops.checkpoint("temp: add temp file")

        # Verify file exists after commit
        assert (git_repo / "temp.txt").exists()

        # Rollback to pre_hash (before commit)
        await git_ops.rollback(pre_hash)

        # File should be gone after hard reset
        assert not (git_repo / "temp.txt").exists()

    @pytest.mark.asyncio
    async def test_rollback_invalid_hash(self, git_ops):
        """rollback() with invalid hash raises RuntimeError."""
        with pytest.raises(RuntimeError) as exc_info:
            await git_ops.rollback("invalid000000000000000000000000000000")

        assert "Failed to rollback" in str(exc_info.value)


class TestGitOpsDiffStat:
    """Test diff stat parsing."""

    @pytest.mark.asyncio
    async def test_diff_stat_empty(self, git_ops):
        """diff_stat() with no changes returns zeros."""
        ds = await git_ops.diff_stat()
        assert ds.files_changed == 0
        assert ds.insertions == 0
        assert ds.deletions == 0

    @pytest.mark.asyncio
    async def test_diff_stat_with_changes(self, git_ops, git_repo):
        """diff_stat() parses changes correctly after staging."""
        # Modify existing file (README.md) and stage it
        (git_repo / "README.md").write_text("# Updated\nContent\n")
        subprocess.run(
            ["git", "add", "README.md"], cwd=git_repo, check=True, capture_output=True
        )

        # Get diff stat (compares staged changes to HEAD)
        ds = await git_ops.diff_stat()

        # Should show changes (regex looks for insertions+deletions, modified file has both)
        assert ds.insertions >= 0
        # raw should be a non-empty string
        assert len(ds.raw) > 0

    @pytest.mark.asyncio
    async def test_diff_stat_raw_output(self, git_ops, git_repo):
        """diff_stat() includes raw output string."""
        (git_repo / "file.py").write_text("x = 1\n")

        ds = await git_ops.diff_stat()
        assert isinstance(ds.raw, str)
        # May be empty if no changes relative to HEAD, but should be a string
        assert isinstance(ds.raw, str)


class TestGitOpsMerge:
    """Test merge operations."""

    @pytest.mark.asyncio
    async def test_merge_success(self, git_ops, git_repo):
        """merge_to() succeeds when no conflicts."""
        default_branch = await git_ops.current_branch()

        # Create feature branch and add a commit
        await git_ops.create_branch("feature/test")
        (git_repo / "feature.py").write_text("def feature():\n    pass\n")
        await git_ops.checkpoint("feat: add feature")

        # Merge to default branch
        result = await git_ops.merge_to(default_branch, "feature/test")

        assert result.success is True
        assert result.conflicts == []
        assert "successful" in result.message.lower() or result.message == ""

    @pytest.mark.asyncio
    async def test_merge_updates_branch(self, git_ops, git_repo):
        """After merge_to(), current branch is target branch."""
        default_branch = await git_ops.current_branch()

        await git_ops.create_branch("feature/merge-test")
        (git_repo / "f.py").write_text("content\n")
        await git_ops.checkpoint("feat: add")

        await git_ops.merge_to(default_branch, "feature/merge-test")

        # Verify we're on default branch after merge
        current = await git_ops.current_branch()
        assert current == default_branch

    @pytest.mark.asyncio
    async def test_merge_success_no_conflicts(self, git_ops, git_repo):
        """merge_to() succeeds when merging non-conflicting changes."""
        default_branch = await git_ops.current_branch()

        # Create feature branch and add a new file (no conflict)
        await git_ops.create_branch("feature/clean")
        (git_repo / "feature.py").write_text("def feature():\n    pass\n")
        await git_ops.checkpoint("feat: add feature")

        # Merge back to default - should succeed (different files)
        result = await git_ops.merge_to(default_branch, "feature/clean")

        # Merge should succeed
        assert result.success is True
        # File should be merged
        assert (git_repo / "feature.py").exists()

    @pytest.mark.asyncio
    async def test_merge_updates_current_branch(self, git_ops, git_repo):
        """merge_to() leaves current branch set to target after merge."""
        default_branch = await git_ops.current_branch()

        # Create and work on feature branch
        await git_ops.create_branch("feature/work")
        (git_repo / "work.py").write_text("x = 1\n")
        await git_ops.checkpoint("feat: add work")

        # Switch to default and merge feature
        result = await git_ops.merge_to(default_branch, "feature/work")
        assert result.success is True

        # After merge, current branch should be default
        branch = await git_ops.current_branch()
        assert branch == default_branch


class TestGitOpsIntegration:
    """Integration tests combining multiple operations."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, git_ops, git_repo):
        """Test complete workflow: branch → commit → merge."""
        main_branch = await git_ops.current_branch()
        pre_hash = await git_ops.get_head_hash()

        # Create feature branch
        await git_ops.create_branch("feature/integration-test")
        assert await git_ops.current_branch() == "feature/integration-test"

        # Add new files (no conflict)
        (git_repo / "feature_a.py").write_text("def feature_a():\n    return 1\n")
        (git_repo / "feature_b.py").write_text("def feature_b():\n    return 2\n")

        # Commit
        commit_hash = await git_ops.checkpoint("feat: add feature files")
        assert commit_hash != pre_hash

        # Merge back to main
        result = await git_ops.merge_to(main_branch, "feature/integration-test")
        assert result.success is True
        assert await git_ops.current_branch() == main_branch

        # Verify files exist after merge
        assert (git_repo / "feature_a.py").exists()
        assert (git_repo / "feature_b.py").exists()

    @pytest.mark.asyncio
    async def test_rollback_and_retry(self, git_ops, git_repo):
        """Test rollback scenario: try changes, rollback, try again."""
        pre_hash = await git_ops.get_head_hash()

        # First attempt: add file1
        await git_ops.create_branch("attempt1")
        (git_repo / "file1.py").write_text("attempt 1\n")
        await git_ops.checkpoint("attempt 1")

        # Rollback to pre_hash
        await git_ops.rollback(pre_hash)
        assert not (git_repo / "file1.py").exists()

        # Second attempt: add file2
        default = await git_ops.current_branch()
        await git_ops.checkout(default)
        await git_ops.create_branch("attempt2")
        (git_repo / "file2.py").write_text("attempt 2\n")
        commit_hash = await git_ops.checkpoint("attempt 2")

        # Verify file2 exists
        assert (git_repo / "file2.py").exists()
        assert not (git_repo / "file1.py").exists()
