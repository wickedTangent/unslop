"""Detect volume anomalies — functions/files that are too large for their purpose.

Research sources:
- Justin McKelvey's "9 Tells" — AI-generated code tends to be verbose and over-engineered
- Git AutoReview — file/function size as a signal of AI generation
- McConnell (2004) "Code Complete" — ideal function length is 20-40 lines
- SonarQube — cognitive complexity and function length thresholds

Key patterns:
1. Functions significantly longer than typical (threshold: 100+ lines)
2. Files significantly longer than typical (threshold: 500+ lines)
3. Methods that handle too many responsibilities (violates SRP)
4. Code that could be split but isn't
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..report import Severity, TellCategory, UnslopIssue


# Thresholds
FUNCTION_LENGTH_THRESHOLD = 100  # lines — functions longer than this are suspicious
FILE_LENGTH_THRESHOLD = 500  # lines — files longer than this are suspicious
MEDIUM_FUNCTION_THRESHOLD = 60  # lines — functions longer than this are worth noting
MEDIUM_FILE_THRESHOLD = 300  # lines — files longer than this are worth noting


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect volume anomalies in source code.

    Checks for:
    - Functions that are significantly longer than expected
    - Files that are significantly longer than expected
    - Methods that handle too many responsibilities

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex for additional context.

    Returns:
        List of UnslopIssue for each volume issue found.
    """
    issues = []
    lines = source.splitlines()
    total_lines = len(lines)

    # 1. File-level volume check
    if total_lines > FILE_LENGTH_THRESHOLD:
        severity = Severity.LOW if total_lines < MEDIUM_FILE_THRESHOLD * 2 else Severity.MEDIUM
        issues.append(UnslopIssue(
            tell=TellCategory.VOLUME_ANOMALY,
            severity=severity,
            description=f'File is {total_lines} lines (threshold: {FILE_LENGTH_THRESHOLD})',
            file_path=file_path,
            code_snippet=f'{total_lines} lines total',
            suggested_fix='Consider splitting into multiple modules or classes',
            confidence=0.75,
            research_source='McConnell, "Code Complete" (2004) — large files indicate poor module boundaries; Git AutoReview #3',
        ))

    # 2. Function-level volume check (Python)
    func_pattern = re.compile(r'(?:async\s+)?def\s+(\w+)\s*\(')
    current_func = None
    current_func_start = None
    current_func_lines = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect function start
        func_match = func_pattern.match(stripped)
        if func_match:
            # Process previous function
            if current_func is not None and current_func_lines > FUNCTION_LENGTH_THRESHOLD:
                severity = Severity.MEDIUM if current_func_lines > FUNCTION_LENGTH_THRESHOLD * 2 else Severity.LOW
                issues.append(UnslopIssue(
                    tell=TellCategory.VOLUME_ANOMALY,
                    severity=severity,
                    description=f'Function "{current_func}" is {current_func_lines} lines (threshold: {FUNCTION_LENGTH_THRESHOLD})',
                    file_path=file_path,
                    line=current_func_start + 1,
                    code_snippet=f'def {current_func}(...)  # {current_func_lines} lines',
                    suggested_fix='Extract sub-functions or split into multiple methods',
                    confidence=0.8,
                    research_source='McConnell, "Code Complete" — ideal function is 20-40 lines; AI code often exceeds 100 lines',
                ))
            elif current_func is not None and current_func_lines > MEDIUM_FUNCTION_THRESHOLD:
                issues.append(UnslopIssue(
                    tell=TellCategory.VOLUME_ANOMALY,
                    severity=Severity.LOW,
                    description=f'Function "{current_func}" is {current_func_lines} lines (medium threshold: {MEDIUM_FUNCTION_THRESHOLD})',
                    file_path=file_path,
                    line=current_func_start + 1,
                    code_snippet=f'def {current_func}(...)  # {current_func_lines} lines',
                    suggested_fix='Consider extracting sub-functions for better readability',
                    confidence=0.7,
                    research_source='Git AutoReview — function length as AI generation signal',
                ))

            # Start new function
            current_func = func_match.group(1)
            current_func_start = i
            current_func_lines = 0
            continue

        # Count lines within function
        if current_func is not None:
            current_func_lines += 1

    # Handle last function
    if current_func is not None and current_func_lines > FUNCTION_LENGTH_THRESHOLD:
        severity = Severity.MEDIUM if current_func_lines > FUNCTION_LENGTH_THRESHOLD * 2 else Severity.LOW
        issues.append(UnslopIssue(
            tell=TellCategory.VOLUME_ANOMALY,
            severity=severity,
            description=f'Function "{current_func}" is {current_func_lines} lines (threshold: {FUNCTION_LENGTH_THRESHOLD})',
            file_path=file_path,
            line=current_func_start + 1,
            code_snippet=f'def {current_func}(...)  # {current_func_lines} lines',
            suggested_fix='Extract sub-functions or split into multiple methods',
            confidence=0.8,
            research_source='McConnell, "Code Complete" — ideal function is 20-40 lines',
        ))

    # 3. Responsibility check — functions with many different operation types
    if current_func is not None and current_func_lines > MEDIUM_FUNCTION_THRESHOLD:
        operation_types = set()
        for j in range(current_func_start, min(current_func_start + current_func_lines, len(lines))):
            line = lines[j].strip()
            if re.search(r'if\s+|elif\s+', line):
                operation_types.add('conditional')
            if re.search(r'for\s+|while\s+', line):
                operation_types.add('loop')
            if re.search(r'return\s+', line):
                operation_types.add('return')
            if re.search(r'print\s*\(|console\.log', line):
                operation_types.add('output')
            if re.search(r'(?:try|catch|except)\s*:', line):
                operation_types.add('error_handling')
            if re.search(r'(?:import|require)\s+', line):
                operation_types.add('import')

        # More than 4 different operation types in a medium/large function is suspicious
        if len(operation_types) > 4:
            issues.append(UnslopIssue(
                tell=TellCategory.VOLUME_ANOMALY,
                severity=Severity.LOW,
                description=f'Function "{current_func}" handles {len(operation_types)} different responsibilities',
                file_path=file_path,
                line=current_func_start + 1,
                code_snippet=f'def {current_func}(...)  # {len(operation_types)} responsibility types',
                suggested_fix=f'Split function — it handles: {", ".join(sorted(operation_types))}',
                confidence=0.65,
                research_source='Git AutoReview — single-responsibility violation in AI-generated functions',
            ))

    return issues


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Suggest volume fixes.

    Note: Auto-fixing volume issues requires refactoring which is risky.
    We only flag, never auto-fix.

    Args:
        source: Original source code.
        issues: List of volume issues.

    Returns:
        Original source (volume fixes are suggestions only).
    """
    # Volume issues are suggestions only — never auto-fix
    # Refactoring requires understanding domain logic
    return source
