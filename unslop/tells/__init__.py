"""Tell detectors and fixers.

Each tell is a pair of functions:
- detect(source, context) -> list[UnslopIssue]
- fix(source, issues) -> str (fixed code)

The context is a PatternIndex that maps existing codebase patterns.
"""

from __future__ import annotations

from .naming import detect as detect_naming, fix as fix_naming
from .verbose_comments import detect as detect_verbose_comments, fix as fix_verbose_comments
from .dead_code import detect as detect_dead_code, fix as fix_dead_code
from .empty_error_handling import detect as detect_empty_error_handling, fix as fix_empty_error_handling
from .todo_artifacts import detect as detect_todo_artifacts, fix as fix_todo_artifacts
from .debug_artifacts import detect as detect_debug_artifacts, fix as fix_debug_artifacts
from .dependency_bloat import detect as detect_dependency_bloat, fix as fix_dependency_bloat
from .pattern_inconsistency import detect as detect_pattern_inconsistency, fix as fix_pattern_inconsistency
from .test_quality import detect as detect_test_quality, fix as fix_test_quality
from .security_scanner import detect as detect_security_scanner, fix as fix_security_scanner
from .volume_analysis import detect as detect_volume_analysis, fix as fix_volume_analysis
from .cross_file_coherence import detect as detect_cross_file_coherence, fix as fix_cross_file_coherence
from .global_incoherence import detect as detect_global_incoherence, fix as fix_global_incoherence

__all__ = [
    "detect_naming", "fix_naming",
    "detect_verbose_comments", "fix_verbose_comments",
    "detect_dead_code", "fix_dead_code",
    "detect_empty_error_handling", "fix_empty_error_handling",
    "detect_todo_artifacts", "fix_todo_artifacts",
    "detect_debug_artifacts", "fix_debug_artifacts",
    "detect_dependency_bloat", "fix_dependency_bloat",
    "detect_pattern_inconsistency", "fix_pattern_inconsistency",
    "detect_test_quality", "fix_test_quality",
    "detect_security_scanner", "fix_security_scanner",
    "detect_volume_analysis", "fix_volume_analysis",
    "detect_cross_file_coherence", "fix_cross_file_coherence",
    "detect_global_incoherence", "fix_global_incoherence",
]
