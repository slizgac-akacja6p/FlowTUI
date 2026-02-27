"""Task complexity estimation based on keywords and heuristics."""
from enum import Enum


class Complexity(str, Enum):
    """Task complexity levels."""

    TRIVIAL = "trivial"
    SIMPLE = "simple"
    COMPLEX = "complex"


# Keyword lists for heuristic detection
COMPLEX_KEYWORDS = [
    "architecture",
    "refactor",
    "migrate",
    "integrate",
    "pipeline",
    "authentication",
    "security",
    "database",
    "concurrent",
    "async",
    "algorithm",
    "optimization",
    "design",
    "system",
    "protocol",
]

TRIVIAL_KEYWORDS = [
    "fix typo",
    "rename",
    "update comment",
    "change string",
    "bump version",
    "add import",
    "format",
    "lint",
    "whitespace",
]


def estimate_complexity(description: str) -> Complexity:
    """
    Estimate task complexity using keyword-based heuristic.

    Rules:
    1. Check trivial keywords first (most specific).
    2. Check complex keywords.
    3. Use word count as fallback: <10 words = trivial, >50 = complex.
    """
    lower = description.lower()

    # Check trivial first (most specific)
    if any(kw in lower for kw in TRIVIAL_KEYWORDS):
        return Complexity.TRIVIAL

    # Check complex
    if any(kw in lower for kw in COMPLEX_KEYWORDS):
        return Complexity.COMPLEX

    # Count words as fallback: <10 words = trivial, >50 = complex
    word_count = len(description.split())
    if word_count < 10:
        return Complexity.TRIVIAL
    if word_count > 50:
        return Complexity.COMPLEX

    return Complexity.SIMPLE
