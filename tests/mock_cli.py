"""Mock CLI for testing — re-exports and convenience utilities.

This module provides a convenient testing interface for MockCLI
by re-exporting the implementation from flowtui.core.invoker.
"""

# Re-export MockCLI from core module for test convenience
from flowtui.core.invoker import MockCLI

__all__ = ["MockCLI"]
