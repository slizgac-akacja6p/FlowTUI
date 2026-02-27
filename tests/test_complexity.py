"""Tests for complexity estimation module."""

import pytest

from flowtui.core.complexity import Complexity, estimate_complexity


class TestComplexityEnum:
    """Test Complexity enum values."""

    def test_all_complexities_enum(self):
        """Complexity enum has expected values."""
        assert Complexity.TRIVIAL == "trivial"
        assert Complexity.SIMPLE == "simple"
        assert Complexity.COMPLEX == "complex"

    def test_complexity_is_string_enum(self):
        """Complexity is a string enum."""
        trivial = Complexity.TRIVIAL
        assert isinstance(trivial, str)
        assert trivial == "trivial"


class TestTrivialKeywords:
    """Test detection of trivial complexity."""

    def test_trivial_fix_typo(self):
        """'fix typo' keyword → TRIVIAL."""
        result = estimate_complexity("fix typo in readme")
        assert result == Complexity.TRIVIAL

    def test_trivial_rename(self):
        """'rename' keyword → TRIVIAL."""
        result = estimate_complexity("rename variable from x to y")
        assert result == Complexity.TRIVIAL

    def test_trivial_update_comment(self):
        """'update comment' keyword → TRIVIAL."""
        result = estimate_complexity("update comment in auth module")
        assert result == Complexity.TRIVIAL

    def test_trivial_change_string(self):
        """'change string' keyword → TRIVIAL."""
        result = estimate_complexity("change string message in error handler")
        assert result == Complexity.TRIVIAL

    def test_trivial_bump_version(self):
        """'bump version' keyword → TRIVIAL."""
        result = estimate_complexity("bump version to 2.0")
        assert result == Complexity.TRIVIAL

    def test_trivial_add_import(self):
        """'add import' keyword → TRIVIAL."""
        result = estimate_complexity("add import for json module")
        assert result == Complexity.TRIVIAL

    def test_trivial_format(self):
        """'format' keyword → TRIVIAL."""
        result = estimate_complexity("format code with black")
        assert result == Complexity.TRIVIAL

    def test_trivial_lint(self):
        """'lint' keyword → TRIVIAL."""
        result = estimate_complexity("lint all python files")
        assert result == Complexity.TRIVIAL

    def test_trivial_whitespace(self):
        """'whitespace' keyword → TRIVIAL."""
        result = estimate_complexity("fix whitespace issues")
        assert result == Complexity.TRIVIAL


class TestComplexKeywords:
    """Test detection of complex complexity."""

    def test_complex_architecture(self):
        """'architecture' keyword → COMPLEX."""
        result = estimate_complexity("redesign application architecture")
        assert result == Complexity.COMPLEX

    def test_complex_refactor(self):
        """'refactor' keyword → COMPLEX."""
        result = estimate_complexity("refactor authentication pipeline")
        assert result == Complexity.COMPLEX

    def test_complex_migrate(self):
        """'migrate' keyword → COMPLEX."""
        result = estimate_complexity("migrate database schema")
        assert result == Complexity.COMPLEX

    def test_complex_integrate(self):
        """'integrate' keyword → COMPLEX."""
        result = estimate_complexity("integrate third party API")
        assert result == Complexity.COMPLEX

    def test_complex_pipeline(self):
        """'pipeline' keyword → COMPLEX."""
        result = estimate_complexity("build continuous integration pipeline")
        assert result == Complexity.COMPLEX

    def test_complex_authentication(self):
        """'authentication' keyword → COMPLEX."""
        result = estimate_complexity("implement OAuth authentication")
        assert result == Complexity.COMPLEX

    def test_complex_security(self):
        """'security' keyword → COMPLEX."""
        result = estimate_complexity("implement security audit")
        assert result == Complexity.COMPLEX

    def test_complex_database(self):
        """'database' keyword → COMPLEX."""
        result = estimate_complexity("optimize database queries")
        assert result == Complexity.COMPLEX

    def test_complex_concurrent(self):
        """'concurrent' keyword → COMPLEX."""
        result = estimate_complexity("implement concurrent task processing")
        assert result == Complexity.COMPLEX

    def test_complex_async(self):
        """'async' keyword → COMPLEX."""
        result = estimate_complexity("refactor code to async patterns")
        assert result == Complexity.COMPLEX

    def test_complex_algorithm(self):
        """'algorithm' keyword → COMPLEX."""
        result = estimate_complexity("implement sorting algorithm")
        assert result == Complexity.COMPLEX

    def test_complex_optimization(self):
        """'optimization' keyword → COMPLEX."""
        result = estimate_complexity("performance optimization of core logic")
        assert result == Complexity.COMPLEX

    def test_complex_design(self):
        """'design' keyword → COMPLEX."""
        result = estimate_complexity("design new module structure")
        assert result == Complexity.COMPLEX

    def test_complex_system(self):
        """'system' keyword → COMPLEX."""
        result = estimate_complexity("system wide refactoring")
        assert result == Complexity.COMPLEX

    def test_complex_protocol(self):
        """'protocol' keyword → COMPLEX."""
        result = estimate_complexity("implement WebSocket protocol")
        assert result == Complexity.COMPLEX


class TestWordCountHeuristics:
    """Test word count fallback heuristics."""

    def test_trivial_word_count_very_short(self):
        """<10 words, no keywords → TRIVIAL."""
        result = estimate_complexity("add button")
        assert result == Complexity.TRIVIAL

    def test_trivial_word_count_short(self):
        """~10 words, no keywords → TRIVIAL."""
        result = estimate_complexity("add a new button to the header section")
        assert result == Complexity.TRIVIAL

    def test_simple_word_count_medium(self):
        """~20-30 words, no keywords → SIMPLE."""
        result = estimate_complexity(
            "add button to show user data on screen with click handler and event listeners"
        )
        assert result == Complexity.SIMPLE

    def test_complex_word_count_long(self):
        """>50 words, no keywords → COMPLEX."""
        result = estimate_complexity(
            "add a comprehensive user management system that includes "
            "profile creation, authentication, authorization, role-based access control, "
            "and detailed audit logging for all user actions and system events"
        )
        assert result == Complexity.COMPLEX


class TestDefaultFallback:
    """Test default SIMPLE fallback."""

    def test_simple_default(self):
        """No keywords, medium length → SIMPLE."""
        result = estimate_complexity(
            "add button and text to display user info on page with styling"
        )
        assert result == Complexity.SIMPLE

    def test_simple_medium_length(self):
        """No keywords, ~20 words → SIMPLE."""
        result = estimate_complexity(
            "display data in list view with filtering options and sorting capabilities available to users"
        )
        assert result == Complexity.SIMPLE


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_case_insensitive_keywords(self):
        """Keywords are matched case-insensitively."""
        result = estimate_complexity("FIX TYPO in readme")
        assert result == Complexity.TRIVIAL

    def test_uppercase_complex_keyword(self):
        """Complex keywords match uppercase."""
        result = estimate_complexity("REFACTOR authentication module")
        assert result == Complexity.COMPLEX

    def test_trivial_takes_precedence(self):
        """Trivial keywords checked before complex."""
        # 'rename' is trivial, should match even if other words are present
        result = estimate_complexity("rename variable in architecture diagram")
        assert result == Complexity.TRIVIAL

    def test_single_word_trivial_keyword(self):
        """Single word trivial keyword."""
        result = estimate_complexity("rename")
        assert result == Complexity.TRIVIAL

    def test_single_word_complex_keyword(self):
        """Single word complex keyword."""
        result = estimate_complexity("refactor")
        assert result == Complexity.COMPLEX

    def test_empty_string_trivial(self):
        """Empty string → TRIVIAL (< 10 words)."""
        result = estimate_complexity("")
        assert result == Complexity.TRIVIAL

    def test_whitespace_only_trivial(self):
        """Whitespace only → TRIVIAL."""
        result = estimate_complexity("   ")
        assert result == Complexity.TRIVIAL
