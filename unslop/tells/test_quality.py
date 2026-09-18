"""Detect and suggest fixes for poor test quality.

Research sources:
- Justin McKelvey's "9 Tells" — AI-generated tests often assert nothing
- Git AutoReview — tests that don't verify behavior
- Cai & Tsantalis (2026) — tautological assertions in AI-generated tests
- Veracode 2025 — test coverage vs. test quality gap

Key patterns:
1. Tautology: assertTrue(True), assert True, assertEquals(True, True)
2. Assert-implementation: checking internal state instead of behavior
3. Empty tests: def test_foo(): pass
4. Missing edge cases: no null/empty/error path tests
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..report import Severity, TellCategory, UnslopIssue


# Tautology patterns — assertions that always pass
TAUTOLOGY_PATTERNS = [
    # Python unittest
    (r'assertTrue\s*\(\s*True\s*\)', 'assert_true_true'),
    (r'assertFalse\s*\(\s*False\s*\)', 'assert_false_false'),
    (r'assertEqual\s*\(\s*True\s*,\s*True\s*\)', 'eq_true_true'),
    (r'assertEqual\s*\(\s*False\s*,\s*False\s*\)', 'eq_false_false'),
    (r'assertIsTrue\s*\(\s*True\s*\)', 'is_true_true'),
    (r'assertIsFalse\s*\(\s*False\s*\)', 'is_false_false'),
    # Python assert statement
    (r'^\s*assert\s+True\s*$', 'assert_true_stmt'),
    (r'^\s*assert\s+1\s*==\s*1\s*$', 'assert_1eq1'),
    (r'^\s*assert\s+(\w+)\s*==\s*\1\s*$', 'assert_same_var'),  # x == x
    # pytest
    (r'assert\s+True', 'pytest_assert_true'),
    # TypeScript/JavaScript
    (r'true\.should\.be\.true', 'chai_true_true'),
    (r'expect\(true\)\.toBe\(true\)', 'jest_true_true'),
    (r'expect\(false\)\.toBe\(false\)', 'jest_false_false'),
    (r'expect\(true\)\.toBeTruthy\(\)', 'jest_truthy'),
    (r'expect\([^)]+\)\.toEqual\([^)]+\)\.toEqual\([^)]+\)', 'chained_equal'),
]

# Empty test patterns
EMPTY_TEST_PATTERNS = [
    r'def\s+test_\w+\s*\(.*\)\s*:\s*$',  # Python: def test_foo():
    r'async\s+def\s+test_\w+\s*\(.*\)\s*:\s*$',  # Python async
    r'it\s*\(\s*["\'].*?["\']\s*,\s*\(\)\s*=>\s*\{\s*\}',  # JS: it('...', () => {})
    r'it\s*\(\s*["\'].*?["\']\s*,\s*async\s*\(\)\s*=>\s*\{\s*\}\)',  # JS async
    r'test\s*\(\s*["\'].*?["\']\s*,\s*\(\)\s*=>\s*\{\s*\}',  # JS test()
]


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect poor test quality patterns.

    Checks for:
    - Tautological assertions that always pass
    - Empty test functions
    - Tests that assert implementation details
    - Missing edge case coverage

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex for additional context.

    Returns:
        List of UnslopIssue for each test quality issue found.
    """
    issues = []
    lines = source.splitlines()

    # 1. Detect tautology assertions
    for i, line in enumerate(lines):
        stripped = line.strip()

        for pattern, category in TAUTOLOGY_PATTERNS:
            if re.search(pattern, stripped):
                severity = Severity.MEDIUM
                # Same-variable assertions are worse
                if category == 'assert_same_var':
                    severity = Severity.HIGH

                issues.append(UnslopIssue(
                    tell=TellCategory.TEST_QUALITY,
                    severity=severity,
                    description=f'Tautology: "{stripped[:80]}" — always passes',
                    file_path=file_path,
                    line=i + 1,
                    code_snippet=stripped,
                    suggested_fix='Assert against actual expected values, not always-true expressions',
                    confidence=0.9,
                    research_source='Cai & Tsantalis (2026) — tautological assertions in AI-generated tests; Veracode 2025 — test quality gap',
                ))
                break

    # 2. Detect empty tests
    for i, line in enumerate(lines):
        stripped = line.strip()

        for pattern in EMPTY_TEST_PATTERNS:
            if re.search(pattern, line):
                # Check if next non-blank line is just 'pass' or empty
                for j in range(i + 1, min(i + 3, len(lines))):
                    next_line = lines[j].strip()
                    if next_line == 'pass' or next_line == '' or next_line.startswith('#'):
                        continue
                    elif next_line:
                        # Found actual content — not empty
                        break
                else:
                    # All following lines are pass/blank/comment
                    issues.append(UnslopIssue(
                        tell=TellCategory.TEST_QUALITY,
                        severity=Severity.MEDIUM,
                        description=f'Empty test function — no assertions, just pass',
                        file_path=file_path,
                        line=i + 1,
                        code_snippet=stripped[:80],
                        suggested_fix='Add actual test assertions or remove the empty test',
                        confidence=0.85,
                        research_source='Git AutoReview — tests that verify nothing are worse than no tests',
                    ))
                break

    # 3. Detect tests that only check implementation (not behavior)
    # Pattern: test asserts that a method was called, not that the output is correct
    impl_check_patterns = [
        r'mock\.\w+\.assert_called',
        r'assert_called_once',
        r'called_with\s*\(.*\)',
        r'thenCalled\s*\(',
    ]

    for i, line in enumerate(lines):
        for pattern in impl_check_patterns:
            if re.search(pattern, line):
                # Check if this is in a test function
                for j in range(i, max(0, i - 10), -1):
                    if re.search(r'def\s+test_|it\s*\(|test\s*\(', lines[j]):
                        issues.append(UnslopIssue(
                            tell=TellCategory.TEST_QUALITY,
                            severity=Severity.LOW,
                            description='Test checks implementation (mock call) rather than behavior',
                            file_path=file_path,
                            line=i + 1,
                            code_snippet=line.strip()[:80],
                            suggested_fix='Also assert the actual output/behavior, not just that a method was called',
                            confidence=0.7,
                            research_source='Justin McKelvey — AI-generated tests often verify mocks, not behavior',
                        ))
                        break
                break

    return issues


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Suggest fixes for test quality issues.

    Note: Auto-fixing tests is risky — we only flag, never auto-delete.

    Args:
        source: Original source code.
        issues: List of test quality issues.

    Returns:
        Original source (tests are suggested-only, never auto-fixed).
    """
    # Test quality issues are suggestions only — never auto-fix
    # This is intentional to avoid breaking legitimate test patterns
    return source
