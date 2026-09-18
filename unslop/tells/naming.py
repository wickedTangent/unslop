"""Detect and fix generic/AI-style naming.

Research source: Justin McKelvey's "9 Tells" — Tell #4
"Generic naming: data2, result_final, handleClick2, newFunction"

McKelvey's core principle: "Names carry intent; AI-in-a-hurry code carries
numbering." The tell is specifically about simple, generic base names with
numeric suffixes — not compound identifiers, year patterns, or descriptive
names. See RESEARCH.md for the full analysis.

KNOWN LIMITATION — Density-based clustering (TODO):
McKelvey's full principle is: "One tell is a hunch. Four or more together is
a diagnosis." Our current implementation counts individual occurrences across
the entire codebase. A file with 854 instances of newState1, newState2,
newState3 is likely test code or a library with intentional variant naming,
not AI slop.

The fix requires:
1. Cluster by base name (data2, data3, data4 = one cluster, not three tells)
2. Count occurrences per file, not globally
3. Weight by file type (production vs. test vs. build artifacts)
4. Only flag when a cluster exceeds a threshold (e.g., 4+ per file)
5. Exclude known test patterns: newState1/newState2/newState3 sequential
   numbering in test files, es2020/es2021 year targets in config

See: blog-generic-naming-tell.md for the full analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..report import Severity, TellCategory, UnslopIssue


# === Year/Version Pattern Exclusions ===
# These are legitimate identifiers that happen to end in digits but are NOT
# AI-generated placeholders. They represent language versions, standards,
# or configuration targets.
_YEAR_VERSION_PATTERNS = [
    # ES target versions: es2020, es2021, es2022, es2023, es2024, es2025, es2026
    r'\bes\d{3,4}\b',
    # TS target versions: ts39, ts50, ts57
    r'\bts\d{2,3}\b',
    # Python version: py311, py312
    r'\bpy\d{3,4}\b',
    # Node version: node16, node18, node20, node22
    r'\bnode\d{2}\b',
    # Rust edition: rust2021
    r'\brust\d{4}\b',
    # Docker/OS versions: alpine320, ubuntu2204, debian12
    r'\balpine\d{3}\b',
    r'\bubuntu\d{4}\b',
    r'\bdebian\d{1,2}\b',
    # Maven/Gradle version properties
    r'\bversion\d\b',
]
_YEAR_VERSION_RE = re.compile('|'.join(_YEAR_VERSION_PATTERNS), re.IGNORECASE)


# === Generic NewPrefix List ===
# McKelvey's example is "newFunction" — a generic placeholder.
# We only flag "newX" when X is a truly generic category word that AI
# commonly uses as a placeholder. Descriptive compound names like
# "newState", "newItem", "newDevtools" are NOT flagged.
_GENERIC_NEW_PREFIXES = {
    'Function', 'Data', 'Result', 'Helper', 'Service', 'Controller',
    'Component', 'Util', 'Config', 'Manager', 'Object', 'Handler',
    'Factory', 'Builder', 'Store', 'Validator', 'Parser', 'Serializer',
    'User', 'Process', 'Item', 'Value', 'State', 'Model', 'Class',
    'Type', 'Entity', 'Resource', 'Record', 'Entry', 'Node', 'Key',
    'Field', 'Prop', 'Option', 'Setting', 'Rule', 'Check', 'Filter',
    'Transform', 'Converter', 'Adapter', 'Wrapper', 'Decorator',
}


# === Underscore-Suffix Patterns ===
# McKelvey explicitly mentions "result_final" as a tell. AI often appends
# _final, _backup, _copy, _temp, _old to indicate tentative naming.
_UNDERSCORE_SUFFIX_PATTERNS = [
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_final\b', 'underscore_suffix', 'Suffix "_final" — suggests tentative or AI-generated naming'),
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_backup\b', 'underscore_suffix', 'Suffix "_backup" — suggests tentative or AI-generated naming'),
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_copy\b', 'underscore_suffix', 'Suffix "_copy" — suggests tentative or AI-generated naming'),
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_temp\b', 'underscore_suffix', 'Suffix "_temp" — suggests tentative or AI-generated naming'),
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_old\b', 'underscore_suffix', 'Suffix "_old" — suggests tentative or AI-generated naming'),
    (r'\b([a-zA-Z_][a-zA-Z0-9_]*?)_new\b', 'underscore_suffix', 'Suffix "_new" — suggests tentative or AI-generated naming'),
]


# === Numeric Suffix Pattern ===
# McKelvey's examples: data2 (4-char base), handleClick2 (11-char base)
# But NOT es2020 (year pattern), NOT newState1 (descriptive compound)
# We require the base name to be 2-12 characters for the strongest signal.
# Single-letter bases (a1, b1) are common in math/test code.
_NUMERIC_SUFFIX_RE = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]{1,12})(\d+)\b')


# === New Prefix Pattern ===
# Only matches new + specific generic placeholder words
# Captures the FULL name (e.g., "newUser" not just "User")
_NEW_PREFIX_RE = re.compile(
    r'\b(new(?:' + '|'.join(_GENERIC_NEW_PREFIXES) + r'))\b'
)


# === My Prefix Pattern ===
# "myX" is less common than "newX" but still a tell when X is generic
_MY_PREFIX_RE = re.compile(r'\bmy([A-Z]\w*)\b')


# === Helper Pattern ===
_HELPER_RE = re.compile(r'\b(helper_function|helper_\w+)\b')


# === Temp Variable Pattern ===
_TEMP_RE = re.compile(
    r'\b(tempData|tempResult|tempValue|tempObject|tempArray|tempList|tempVar)\b'
)


# Patterns that indicate AI-generated naming
# These are the STRONGEST signals — names that are almost certainly AI placeholders
GENERIC_NAME_PATTERNS = [
    # 1. Numeric suffixes on short base names (the strongest signal)
    #    McKelvey: data2, handleClick2
    (_NUMERIC_SUFFIX_RE, 'numeric_suffix',
     'Generic numeric suffix — suggests the AI tried multiple names and kept the last one'),
    # 2. Underscore-suffix tentative naming
    #    McKelvey: result_final
    *_UNDERSCORE_SUFFIX_PATTERNS,
    # 3. Very generic function names with "new" prefix
    #    McKelvey: newFunction
    (_NEW_PREFIX_RE, 'new_prefix',
     'Function starting with "new" + generic word — suggests AI placeholder'),
    # 4. "my" prefix with generic word
    (_MY_PREFIX_RE, 'my_prefix',
     'Function starting with "my" — suggests AI placeholder'),
    # 5. "helper" in name
    (_HELPER_RE, 'helper_name',
     'Function named "helper" — should describe what it helps with'),
    # 6. "temp" variables with specific suffixes
    (_TEMP_RE, 'temp_variable',
     'Temporary variable that wasn\'t cleaned up'),
]

# Regex to strip string literals and inline comments from a line.
# Replaces quoted strings, template literals, and inline comments with spaces
# so the numeric-suffix regex only matches actual identifiers, not values inside
# strings (e.g. "OAuth2", JWT tokens, API keys).
_STRIPE_STRINGS_AND_COMMENTS = re.compile(
    r'''"""[^"]*"""''',  # triple-double-quoted strings
    flags=re.DOTALL,
)
_STRIPE_STRINGS_AND_COMMENTS2 = re.compile(
    r"""'''[^']*'''""",  # triple-single-quoted strings
    flags=re.DOTALL,
)
_STRIPE_STRINGS_AND_COMMENTS3 = re.compile(
    r'"[^"]*"',  # double-quoted strings
)
_STRIPE_STRINGS_AND_COMMENTS4 = re.compile(
    r"'[^']*'",  # single-quoted strings
)
_STRIPE_STRINGS_AND_COMMENTS5 = re.compile(
    r'`[^`]*`',  # template literals
)
_STRIPE_STRINGS_AND_COMMENTS6 = re.compile(
    r'//.*$',  # inline single-line comments
)
_STRIPE_STRINGS_AND_COMMENTS7 = re.compile(
    r'/\*.*?\*/',  # inline block comments (non-greedy)
    flags=re.DOTALL,
)


def _strip_strings_and_comments(line: str) -> str:
    """Remove string literals and inline comments from a code line.

    This prevents the numeric-suffix regex from matching inside string
    values (e.g. "OAuth2", JWT tokens, API keys) or comments.
    """
    # Order matters: triple quotes first, then double/single, then comments
    line = _STRIPE_STRINGS_AND_COMMENTS.sub(' ', line)
    line = _STRIPE_STRINGS_AND_COMMENTS2.sub(' ', line)
    line = _STRIPE_STRINGS_AND_COMMENTS3.sub(' ', line)
    line = _STRIPE_STRINGS_AND_COMMENTS4.sub(' ', line)
    line = _STRIPE_STRINGS_AND_COMMENTS5.sub(' ', line)
    line = _STRIPE_STRINGS_AND_COMMENTS6.sub(' ', line)
    line = _STRIPE_STRINGS_AND_COMMENTS7.sub(' ', line)
    return line


# Names that are common in codebases but not AI-generated placeholders.
# These are all-alphanumeric (no underscores) identifiers that often appear
# in strings/comments (e.g. OAuth2, JWT, API keys) but are legitimate.
_SKIP_ALL_ALPHANUMERIC = {
    # Common API/auth protocols
    'OAuth', 'JWT', 'Bearer', 'API', 'REST', 'GraphQL', 'HTTP', 'HTTPS',
    'WebSocket', 'SSE', 'gRPC', 'SOAP', 'XML', 'JSON', 'YAML', 'TOML',
    # Common tech terms
    'AWS', 'GCP', 'Azure', 'SaaS', 'PaaS', 'IaaS', 'CI', 'CD', 'CI/CD',
    'DB', 'SQL', 'NoSQL', 'ORM', 'MVC', 'RESTful', 'CRUD', 'DOM', 'BOM',
    # Common crypto/auth terms
    'SHA', 'MD5', 'AES', 'RSA', 'ECDSA', 'Ed25519', 'PKCS', 'DER', 'PEM',
    'HMAC', 'PBKDF2', 'bcrypt', 'scrypt', 'argon2', 'Argon2',
    # Common base64-like strings (JWT parts, API keys, tokens)
    'eyJ', 'dGVzdA', 'aGlzdA', 'Y29uZmln', 'c3RyaW5n',
}


def _is_likely_token_or_key(original: str) -> bool:
    """Heuristic: is this likely a JWT token, API key, or other secret?

    JWT tokens start with 'eyJ' (base64-encoded '{').
    API keys and secrets are typically all-alphanumeric, no underscores,
    and longer than 16 characters.
    """
    # JWT tokens always start with 'eyJ'
    if original.lower().startswith('eyJ'):
        return True
    # Long all-alphanumeric strings (no underscores) are likely secrets
    if '_' not in original and len(original) > 16:
        return True
    return False


@dataclass
class NameSuggestion:
    """A suggested name replacement."""
    original: str
    suggested: str
    reason: str


def _infer_better_name(
    original: str,
    context_lines: list[str],
    line_index: int,
    language: str,
) -> NameSuggestion:
    """Infer a better name based on context.

    Uses surrounding code context to guess what the name should be:
    - Parameter names
    - Variable assignments
    - Function purpose from surrounding lines
    """
    # Look at the surrounding context for clues
    context_start = max(0, line_index - 5)
    context_end = min(len(context_lines), line_index + 5)
    context = '\n'.join(context_lines[context_start:context_end])

    # If it's a numeric suffix, strip the number and see what's left
    numeric_match = re.match(r'^(\w+?)(\d+)$', original)
    if numeric_match:
        base_name = numeric_match.group(1)
        # Try to find what the base name should be based on context
        if base_name == 'data':
            # Look for what kind of data is being processed
            data_types = re.findall(r'(\w+)(?:\s*:\s*(?:List|Array|Dict|Map|Optional|Promise|Observable))', context)
            if data_types:
                return NameSuggestion(
                    original=original,
                    suggested=f'format_{data_types[0]}',
                    reason='Inferred from type annotation in surrounding code',
                )
            return NameSuggestion(
                original=original,
                suggested=f'process_{base_name}',
                reason='Generic data name — added "process" prefix for clarity',
            )
        elif base_name == 'result':
            return NameSuggestion(
                original=original,
                suggested=f'return_value',
                reason='"result" is too generic — use "return_value" to clarify purpose',
            )
        elif base_name.startswith('handle'):
            # Try to infer the event/action from surrounding code
            events = re.findall(r'on(\w+)', context)
            if events:
                return NameSuggestion(
                    original=original,
                    suggested=f'on_{events[0].lower()}',
                    reason=f'Inferred event handler from "{events[0]}" in surrounding code',
                )
            return NameSuggestion(
                original=original,
                suggested=f'handle_{base_name[6:].lower()}',
                reason='Generic handler — should describe the specific action',
            )
        elif base_name == 'temp':
            return NameSuggestion(
                original=original,
                suggested=f'temporary_{base_name}',
                reason='Temporary variable should be removed or renamed to describe its purpose',
            )

    # Generic term without suffix — suggest adding context
    if original in ('data', 'result', 'value', 'item', 'obj'):
        return NameSuggestion(
            original=original,
            suggested=f'{original}_value',
            reason=f'"{original}" is too generic — add context',
        )

    return NameSuggestion(
        original=original,
        suggested=f'{original}_refined',
        reason='Name suggests AI-generated placeholder',
    )


def _is_year_or_version_pattern(name: str) -> bool:
    """Check if a name is a year/version pattern, not an AI placeholder.

    Legitimate year/version patterns that AI does NOT use as placeholders:
    - ES target versions: es2020, es2021, ... es2026
    - TS target versions: ts39, ts50, ts57
    - Python versions: py311, py312
    - Node versions: node16, node18, node20
    - Docker/OS: alpine320, ubuntu2204, debian12
    """
    return bool(_YEAR_VERSION_RE.search(name))


def _is_descriptive_compound(name: str) -> bool:
    """Check if a name with numeric suffix is descriptive, not generic.

    McKelvey's tell is about simple base names with numbering (data2, handleClick2).
    Descriptive compounds like newState1, newDevtools2 are NOT the tell.
    """
    # Extract base name (strip trailing digits)
    base = re.match(r'^(\D+)', name)
    if not base:
        return False
    base = base.group(1)

    # If base is 2+ words (e.g., "newState" -> "new" + "State"), it's descriptive
    # Check for camelCase compound: new + State, handle + Click, etc.
    compound_match = re.match(r'^([a-z]+)([A-Z][a-z]+)', base)
    if compound_match:
        # Two+ word compound: newState, handleClick, apiEndpoint
        return True

    # Check if base starts with a known descriptive prefix
    descriptive_prefixes = {
        'reached', 'resolver', 'result', 'tier', 'hop',
        'node', 'edge', 'path', 'link', 'ref', 'dep',
        'symbol', 'import', 'export', 'module', 'file',
        'class', 'method', 'func', 'var', 'val',
        'caps', 'matches', 'captures', 'items',
        'entries', 'roots', 'children', 'parents',
        'sources', 'targets', 'nodes', 'edges',
        'new', 'handle', 'get', 'set', 'create', 'build',
        'format', 'parse', 'validate', 'transform',
    }
    return any(base.startswith(p) for p in descriptive_prefixes)


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect generic/AI-style naming in source code.

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex for additional context.

    Returns:
        List of UnslopIssue for each generic name found.
    """
    issues = []
    lines = source.splitlines()

    for i, line in enumerate(lines):
        # Skip full-line comments
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('*'):
            continue

        # Imports routinely contain legitimate versioned/API names such as
        # PySide6, ID3, QImage, and Format_RGB32. They are not local names
        # chosen by the author and should never trigger this tell.
        if re.match(r'^\s*(?:from\b.*\bimport\b|import\b)', stripped):
            continue

        # Strip string literals and inline comments so the regex only matches
        # actual identifiers, not values inside strings (e.g. "OAuth2", JWT
        # tokens, API keys) or comments.
        code_part = _strip_strings_and_comments(line)

        for pattern, category, description in GENERIC_NAME_PATTERNS:
            for match in re.finditer(pattern, code_part):
                original = match.group(1) if match.lastindex else match.group(0)

                # A dotted call such as ``shutil.copy2`` or ``struct.unpack2``
                # refers to an API member, not a numbered local variable.
                if category == 'numeric_suffix' and match.start() > 0 and code_part[match.start() - 1] == '.':
                    continue

                # Skip all-alphanumeric names that are common in codebases
                # (e.g. OAuth, JWT, Bearer, SHA256, etc.) — these are
                # legitimate identifiers, not AI placeholders.
                if original in _SKIP_ALL_ALPHANUMERIC:
                    continue

                # Skip likely JWT tokens, API keys, or other secrets.
                # These are all-alphanumeric strings that are too long to be
                # meaningful identifiers.
                if _is_likely_token_or_key(original):
                    continue

                # Skip common non-AI names (only when NOT flagged with
                # numeric suffix — those ARE AI-typical)
                if category != 'numeric_suffix' and original in ('data', 'result', 'temp'):
                    continue
                if category != 'numeric_suffix' and original in ('obj', 'item', 'value'):
                    continue

                if category == 'numeric_suffix':
                    # Numeric suffixes are meaningful only when attached to a
                    # genuinely generic placeholder base. Domain names,
                    # protocol fields, and format/version identifiers are
                    # common in real code and carry no AI-slop signal.
                    base_name = re.sub(r'\d+$', '', original).rstrip('_')
                    generic_bases = {
                        'data', 'result', 'value', 'item', 'object', 'thing',
                        'temp', 'var', 'foo', 'bar', 'baz', 'function',
                    }
                    if base_name.casefold() not in generic_bases and not base_name.casefold().startswith('handle'):
                        continue
                    # Skip single-letter names with numeric suffixes — common in test code
                    # (e.g., s1, c1, r1, k1, v1 for skeleton/context/result/key/value)
                    if len(original) == 1:
                        continue
                    # Skip common iteration variables
                    if original in ('i', 'j', 'k', 'n', 'x', 'y', 'z', 'idx', 'num', 'cnt'):
                        continue
                    # Skip common test fixture variables
                    if original in ('s', 'c', 'r', 'k', 'v', 'm', 'd', 'f', 'p', 't', 'e'):
                        continue
                    # Skip TypeScript/JavaScript compiled rename artifacts.
                    # When TypeScript compiles `import { X } from 'Y'`, it renames
                    # to `X_1`, `X_2` etc. The regex captures `X_` as group(1).
                    # Also skip any name ending with `_` + digits (compiler artifacts).
                    if original.endswith('_'):
                        continue
                    underscore_digit = re.match(r'^(.+)_\d+$', original)
                    if underscore_digit:
                        continue
                    # Skip year/version patterns: es2020, ts39, py311, node18, etc.
                    # These are language version targets, not AI placeholders.
                    if _is_year_or_version_pattern(original):
                        continue
                    # Skip descriptive compound names with numeric suffix.
                    # McKelvey's tell is about simple base names (data2, handleClick2),
                    # not compound names (newState1, newDevtools2).
                    if _is_descriptive_compound(original):
                        continue
                    issues.append(UnslopIssue(
                        tell=TellCategory.GENERIC_NAMING,
                        severity=Severity.HIGH,
                        description=f'Generic name with numeric suffix: "{original}" — suggests AI placeholder',
                        file_path=file_path,
                        line=i + 1,
                        code_snippet=line.strip()[:80],
                        suggested_fix=f'Consider renaming to a domain-specific name',
                        confidence=0.95,
                        research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #4',
                    ))
                elif category == 'new_prefix' or category == 'my_prefix':
                    issues.append(UnslopIssue(
                        tell=TellCategory.GENERIC_NAMING,
                        severity=Severity.MEDIUM,
                        description=f'Function name starting with "{original[:2]}": "{original}" — suggests placeholder',
                        file_path=file_path,
                        line=i + 1,
                        code_snippet=line.strip()[:80],
                        suggested_fix=f'Rename to describe the function\'s purpose',
                        confidence=0.7,
                        research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #4',
                    ))
                elif category == 'temp_variable':
                    issues.append(UnslopIssue(
                        tell=TellCategory.GENERIC_NAMING,
                        severity=Severity.LOW,
                        description=f'Temporary variable: "{original}" — should describe its purpose',
                        file_path=file_path,
                        line=i + 1,
                        code_snippet=line.strip()[:80],
                        suggested_fix=f'Rename to describe what it holds',
                        confidence=0.75,
                        research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #4',
                    ))
                elif category == 'underscore_suffix':
                    # McKelvey's missed tell: result_final, data_backup, etc.
                    # AI appends _final, _backup, _copy to indicate tentative naming.
                    original = match.group(0)
                    base_name = match.group(1)
                    # Skip if base is too short (single letter)
                    if len(base_name) <= 1:
                        continue
                    # Skip if base is a common legitimate word
                    if base_name in ('config', 'data', 'result', 'state', 'value', 'item',
                                     'output', 'input', 'output', 'temp', 'backup',
                                     'copy', 'final', 'old', 'new', 'main', 'core'):
                        continue
                    issues.append(UnslopIssue(
                        tell=TellCategory.GENERIC_NAMING,
                        severity=Severity.MEDIUM,
                        description=f'Underscore-suffix tentative name: "{original}" — suggests AI placeholder',
                        file_path=file_path,
                        line=i + 1,
                        code_snippet=line.strip()[:80],
                        suggested_fix=f'Rename to describe the variable\'s purpose',
                        confidence=0.75,
                        research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #4',
                    ))

    return issues


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Apply naming fixes to source code.

    Safe auto-fixes for generic prefixes:
    - `new_X` → `X` (strip "new" prefix)
    - `helper_X` → `X` (strip "helper" prefix)
    - `my_X` → `X` (strip "my" prefix)

    Numeric suffixes are NOT auto-fixed (renaming requires updating all
    references throughout the codebase — too risky for auto-fix).

    Context-aware:
    - Function/class names: minimum 2-char stripped name (single-letter
      function names are never meaningful)
    - Local variables: single-letter names allowed (x, y, z, i, j, k)

    Line-specific: only renames the detected occurrence, not all occurrences
    in the file (avoids breaking call sites).

    Args:
        source: Original source code.
        issues: List of naming issues to fix.

    Returns:
        Fixed source code.
    """
    lines = source.splitlines(keepends=True)

    for issue in issues:
        if not issue.line or not issue.code_snippet:
            continue

        line_idx = issue.line - 1
        if line_idx < 0 or line_idx >= len(lines):
            continue

        # Extract the name from the code snippet
        name = issue.code_snippet.strip()

        # Strip quotes if present
        for quote in ('"', "'", '`'):
            if name.startswith(quote) and name.endswith(quote):
                name = name[1:-1]

        # Determine if this is a function/class definition
        line = lines[line_idx]
        is_func_or_class = (
            re.match(r'\s*(def\s+|class\s+)', line) is not None
        )

        # Determine the minimum stripped name length
        # Function/class names need >= 2 chars (single-letter names are meaningless)
        # Local variables allow >= 1 char (x, y, z, i, j, k are common)
        min_stripped_len = 2 if is_func_or_class else 1

        # Try underscore variants: helper_X, my_X, new_X
        for prefix in ('helper_', 'my_', 'new_'):
            if name.startswith(prefix) and len(name) > len(prefix):
                stripped = name[len(prefix):]
                if len(stripped) >= min_stripped_len:
                    # Find and replace only this occurrence on this line
                    lines[line_idx] = re.sub(
                        r'\b' + re.escape(name) + r'\b',
                        stripped,
                        line,
                        count=1,
                    )
                    break

        # Try camelCase variants: newUser, myProcess
        else:
            camel_match = re.match(r'^(new|my)([A-Z]\w*)$', name)
            if camel_match:
                stripped = camel_match.group(2).lower()
                if len(stripped) >= min_stripped_len:
                    lines[line_idx] = re.sub(
                        r'\b' + re.escape(name) + r'\b',
                        stripped,
                        line,
                        count=1,
                    )

    return ''.join(lines)
