"""Detect and fix verbose comments.

Research source: Justin McKelvey's "9 Tells" — Tell #1
"Comments that explain the obvious, uniformly — # increment the counter
above counter += 1. A human writes that comment zero times. An AI writes it
forty times, in identical style, on every file."

Also: Git AutoReview — Tell #10: Debug artifacts (related — comments that
shouldn't be in production)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..report import Severity, TellCategory, UnslopIssue


# Imperative verbs that signal AI-style "what next line does" comments
# Humans rarely prefix code lines with "do X" comments when X is obvious
IMPERATIVE_VERBS = [
    # Operations
    'increment', 'decrement', 'add', 'subtract', 'multiply', 'divide',
    # Conditionals
    'check', 'verify', 'validate', 'test', 'compare', 'match',
    # Creation/modification
    'create', 'build', 'make', 'set', 'update', 'modify', 'change', 'assign',
    'return', 'send', 'output', 'print', 'display',
    # Iteration
    'iterate', 'loop', 'go through', 'process',
    # Execution
    'call', 'invoke', 'execute', 'run',
    # Data access
    'get', 'fetch', 'retrieve', 'load', 'read',
    # Deletion
    'remove', 'delete', 'clear', 'drop', 'discard',
    # More actions
    'generate', 'insert', 'call', 'perform', 'apply', 'run', 'write',
    'read', 'send', 'receive', 'upload', 'download', 'create', 'delete',
    'update', 'fetch', 'pull', 'push', 'emit', 'trigger', 'fire',
    # Transformation
    'convert', 'transform', 'parse', 'serialize', 'deserialize',
    'format', 'sort', 'order', 'arrange',
    'filter', 'select', 'find', 'search', 'locate',
    'split', 'join', 'concat', 'merge', 'combine',
    'trim', 'strip', 'clean', 'sanitize', 'normalize',
    'encode', 'decode', 'encrypt', 'decrypt', 'hash',
    # Counting
    'count', 'calculate',
    # Storage
    'save', 'store', 'persist',
    # Connections
    'open', 'close', 'connect', 'disconnect',
]

# Comment prefixes that signal "why" (not "what") — these are GOOD
WHY_PREFIXES = [
    'because', 'since', 'as this', 'so that', 'in order',
    'note:', 'todo', 'fixme', 'hack', 'xxx',
    'reason', 'warning', 'caution', 'danger',
    'edge case', 'special case', 'important',
]


@dataclass
class CommentContext:
    """Context around a comment for better classification."""
    comment_line: str
    comment_col: int
    next_code_line: str | None
    prev_code_line: str | None
    is_block_comment: bool
    line_number: int


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect verbose/AI-style comments in source code.

    Uses context-aware analysis to distinguish:
    - BAD: "# increment the counter" above `counter += 1` (restates what)
    - GOOD: "# because the API returns ISO 8601" (explains why)

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex for additional context.

    Returns:
        List of UnslopIssue for each verbose comment found.
    """
    issues = []
    lines = source.splitlines()

    # ----------------------------------------------------------------
    # Phase 1: Detect inline comments that restate what the next line does
    # ----------------------------------------------------------------
    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip non-comment lines
        if not stripped.startswith('#') and not stripped.startswith('//'):
            continue

        # Skip multi-line block comments (they're usually intentional)
        if stripped.startswith('"""') or stripped.startswith("'''"):
            continue

        # Skip comments that start with "why" signals
        lower = stripped.lower()
        if any(lower.startswith(wp) for wp in WHY_PREFIXES):
            continue

        # Skip TODO/FIXME — those are handled by todo_artifacts tell
        if any(kw in lower for kw in ['todo:', 'fixme:', 'hack:']):
            continue

        # Extract the imperative verb from the comment
        verb = _extract_imperative_verb(stripped)
        if verb is None:
            continue

        # Find the next 2-3 non-blank, non-comment lines
        next_lines = _next_code_lines(lines, i)
        if not next_lines:
            continue

        match_line = next_lines[0]
        if _next_line_matches_verb(match_line, verb):
            confidence = 0.88 if _is_obvious_restatement(stripped, match_line) else 0.75
        elif len(next_lines) > 1 and _next_line_matches_verb(next_lines[1], verb):
            confidence = 0.70  # Slightly lower confidence for multi-line match
            match_line = next_lines[1]
        else:
            continue

        issues.append(UnslopIssue(
                tell=TellCategory.VERBOSE_COMMENTS,
                severity=Severity.LOW,
                description=f'Comment restates code: "{stripped[:70]}"',
                file_path=file_path,
                line=i + 1,
                code_snippet=stripped,
                suggested_fix='Remove comment or replace with why this code exists',
                confidence=confidence,
                research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #1: Comments that explain the obvious, uniformly',
            ))

    # ----------------------------------------------------------------
    # Phase 2: Detect uniform docstrings on trivial functions
    # ----------------------------------------------------------------
    issues.extend(_detect_trivial_docstrings(source, file_path))

    return issues


def _extract_imperative_verb(comment: str) -> str | None:
    """Extract the leading imperative verb from a comment.

    Returns the verb string if the comment starts with one of the
    IMPERATIVE_VERBS, otherwise None.
    """
    stripped = comment.lstrip('#/').strip()
    lower = stripped.lower()

    # Try multi-word verbs first (longer matches take priority)
    for verb in sorted(IMPERATIVE_VERBS, key=len, reverse=True):
        if lower.startswith(verb) and len(verb) > 1:
            # Ensure it's followed by a space/punctuation (not a substring)
            after = lower[len(verb):]
            if after == '' or after[0] in (' ', ':', ',', ';'):
                return verb

    # Try single-word verbs
    first_word = stripped.split()[0] if stripped.split() else ''
    if first_word.lower() in IMPERATIVE_VERBS:
        return first_word.lower()

    return None


def _next_code_lines(
    lines: list[str], current_idx: int, max_lookahead: int = 3,
) -> list[str]:
    """Find the next N non-blank, non-comment lines after current_idx.

    Returns up to max_lookahead code lines.
    """
    result: list[str] = []
    for j in range(current_idx + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped and not stripped.startswith('#') and not stripped.startswith('//'):
            result.append(stripped)
            if len(result) >= max_lookahead:
                break
    return result


def _next_line_matches_verb(next_line: str, verb: str) -> bool:
    """Check if the next line of code performs the action described by the verb.

    Uses keyword matching on the next line to see if the verb's action
    is actually being performed.
    """
    lower = next_line.lower()

    # Map verbs to keywords that appear in the actual code
    verb_to_keywords: dict[str, list[str]] = {
        'increment': ['+=', '++', 'increment'],
        'decrement': ['-= ', '--', 'decrement'],
        'add': ['append', 'extend', 'insert', '+=', 'add', ' + '],
        'subtract': ['-= ', 'subtract'],
        'multiply': ['*= ', 'multiply'],
        'divide': ['/=', 'divide'],
        'check': ['if ', 'isinstance', 'hasattr', 'in ', '==', '!='],
        'verify': ['verify', 'assert', 'check', 'if '],
        'validate': ['validate', 'check', 'if '],
        'test': ['test', 'assert', 'check'],
        'compare': ['==', '!=', '<', '>', 'cmp'],
        'match': ['match ', 'regex', '=='],
        'create': ['= ', '=(', 'new ', 'dict(', 'list(', 'set(', 'class '],
        'build': ['build', 'create', 'construct'],
        'make': ['make', 'create', 'build'],
        'set': ['= ', 'setattr', 'set'],
        'update': ['update', '+= ', 'modify'],
        'modify': ['modify', 'update', '= '],
        'change': ['change', 'update', '= '],
        'assign': ['= ', 'assign'],
        'return': ['return '],
        'send': ['send', 'post', 'emit'],
        'output': ['output', 'print', 'write'],
        'print': ['print'],
        'display': ['display', 'show', 'render'],
        'iterate': ['for ', 'while ', 'each', 'map'],
        'loop': ['for ', 'while ', 'loop'],
        'go through': ['for ', 'while ', 'each'],
        'process': ['process', 'transform', 'handle'],
        'call': ['call', 'invoke', '.('],
        'generate': ['uuid', 'random', 'new_', 'str(', 'id'],
        'insert': ['insert', 'append', 'extend', 'push', 'insert'],
        'invoke': ['invoke', 'call', '.('],
        'execute': ['execute', 'run', 'exec'],
        'run': ['run', 'execute', '.('],
        'get': ['get(', 'getuser', 'get_', 'fetch', 'read', '[', 'query'],
        'fetch': ['fetch', 'get', 'request'],
        'retrieve': ['retrieve', 'get', 'fetch'],
        'load': ['load', 'read', 'import'],
        'read': ['read', 'load', 'open'],
        'remove': ['remove', 'del ', 'pop', 'discard'],
        'delete': ['delete', 'del ', 'drop'],
        'clear': ['clear', 'remove', 'del '],
        'drop': ['drop', 'delete', 'remove'],
        'discard': ['discard', 'remove', 'del '],
        'convert': ['convert', 'cast', 'type(', 'int(', 'str(', 'json.', 'yaml.', 'pickle.', 'to_json', 'to_dict'],
        'transform': ['transform', 'convert', 'map'],
        'parse': ['parse', 'json.', 'yaml.', 'xml'],
        'serialize': ['serialize', 'dump', 'json.'],
        'deserialize': ['deserialize', 'load', 'json.'],
        'format': ['format', 'strftime', 'f"', 'template'],
        'sort': ['sort', 'sorted', 'order'],
        'order': ['sort', 'order', 'sorted'],
        'arrange': ['arrange', 'sort', 'order'],
        'filter': ['filter', 'where', 'if '],
        'select': ['select', 'filter', 'where'],
        'find': ['find', 'search', 'filter'],
        'search': ['search', 'find', 'query'],
        'locate': ['locate', 'find', 'search'],
        'split': ['split', 'partition'],
        'join': ['join', 'concat', '+'],
        'concat': ['concat', 'join', '+'],
        'merge': ['merge', 'join', 'update'],
        'combine': ['combine', 'merge', 'join'],
        'trim': ['strip', 'trim', 'lstrip', 'rstrip'],
        'strip': ['strip', 'trim', 'lstrip', 'rstrip'],
        'clean': ['clean', 'sanitize', 'strip'],
        'sanitize': ['sanitize', 'clean', 'strip'],
        'normalize': ['normalize', 'standardize'],
        'encode': ['encode', 'b64', 'json.'],
        'decode': ['decode', 'b64', 'json.'],
        'encrypt': ['encrypt', 'cipher'],
        'decrypt': ['decrypt', 'cipher'],
        'hash': ['hash', 'sha', 'md5'],
        'count': ['count', 'len(', 'size'],
        'calculate': ['calculate', 'compute', '= ', '+', '-', '*', '/'],
        'save': ['save', 'write', 'store', 'dump'],
        'store': ['store', 'save', 'write'],
        'persist': ['persist', 'save', 'commit'],
        'open': ['open(', 'connect'],
        'close': ['close', 'disconnect', 'shutdown'],
        'connect': ['connect', 'open', 'join'],
        'disconnect': ['disconnect', 'close', 'shutdown'],
    }

    keywords = verb_to_keywords.get(verb, [verb])
    if any(kw in lower for kw in keywords):
        return True

    # Fallback: if the verb itself appears in the next line as a substring,
    # it's likely a match (e.g., "get" in "getUser()", "format" in "formatDate()")
    # Only apply this for verbs that are unlikely to appear as accidental substrings
    safe_verbs = {'get', 'set', 'add', 'remove', 'update', 'create', 'build',
                  'process', 'handle', 'parse', 'format', 'convert', 'transform',
                  'validate', 'check', 'verify', 'load', 'save', 'store',
                  'open', 'close', 'connect', 'disconnect'}
    if verb in safe_verbs and len(verb) >= 3 and verb in lower:
        return True

    return False


def _is_obvious_restatement(comment: str, next_line: str) -> bool:
    """Heuristic: is this comment an obvious, low-value restatement?

    Returns True when the comment is extremely generic and the code is
    equally simple — the kind of comment a human would never write.
    """
    # Remove comment prefix
    comment_body = comment.lstrip('#/').strip().lower()
    # Remove the verb we already matched
    verb = _extract_imperative_verb(comment)
    if verb:
        comment_body = comment_body[len(verb):].lstrip(' ,:')

    # If the comment is very short after removing the verb, it's a restatement
    if len(comment_body) < 10:
        return True

    # If the next line is a single simple expression, it's a restatement
    if next_line.count('(') <= 1 and next_line.count(';') == 0:
        return True

    return False


def _detect_trivial_docstrings(source: str, file_path: Path) -> list[UnslopIssue]:
    """Detect docstrings on trivial functions (< 3 body lines).

    Humans don't write docstrings on one-liners. AI does.
    """
    issues: list[UnslopIssue] = []
    lines = source.splitlines()

    current_func_start: int | None = None
    current_func_name: str | None = None
    in_docstring = False
    docstring_lines: list[str] = []
    func_body_lines = 0
    indent_level = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect function/class definitions
        func_match = re.match(
            r'(?:async\s+)?def\s+(\w+)|(?:^|\s)class\s+(\w+)',
            stripped,
        )
        if func_match:
            # Process previous function
            if current_func_start is not None and in_docstring and docstring_lines:
                _check_trivial_docstring(
                    issues, source, file_path,
                    current_func_start, current_func_name,
                    docstring_lines, func_body_lines,
                )

            # Reset for new function
            current_func_start = i
            current_func_name = func_match.group(1) or func_match.group(2)
            in_docstring = False
            docstring_lines = []
            func_body_lines = 0
            indent_level = len(line) - len(line.lstrip()) + 4
            continue

        # Skip if we haven't hit a function yet
        if current_func_start is None:
            continue

        # Track indentation to know when function ends
        line_indent = len(line) - len(line.lstrip()) if stripped else 999
        if stripped and line_indent <= indent_level and func_body_lines > 0:
            # Function ended — check it
            if in_docstring and docstring_lines:
                _check_trivial_docstring(
                    issues, source, file_path,
                    current_func_start, current_func_name,
                    docstring_lines, func_body_lines,
                )
            current_func_start = None
            continue

        # Detect docstring start
        if stripped.startswith('"""') or stripped.startswith("'''"):
            if not in_docstring:
                in_docstring = True
                docstring_lines.append(stripped)
                if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                    in_docstring = False
            else:
                docstring_lines.append(stripped)
                in_docstring = False
            continue

        # Count body lines (not inside docstring, not blank, not comment)
        if not in_docstring and stripped and not stripped.startswith('#'):
            func_body_lines += 1

    # Handle last function
    if current_func_start is not None and in_docstring and docstring_lines:
        _check_trivial_docstring(
            issues, source, file_path,
            current_func_start, current_func_name,
            docstring_lines, func_body_lines,
        )

    return issues


def _check_trivial_docstring(
    issues: list[UnslopIssue],
    source: str,
    file_path: Path,
    func_start: int,
    func_name: str | None,
    docstring_lines: list[str],
    body_lines: int,
) -> None:
    """Check a single function's docstring and add an issue if trivial."""
    # Only flag single-line docstrings on very trivial functions
    if len(docstring_lines) > 1:
        return

    if body_lines >= 3:
        return

    # Skip if docstring has structured sections (Args/Returns/Raises)
    doc_text = ' '.join(docstring_lines)
    if any(kw in doc_text for kw in ['args:', 'returns:', 'raises:', 'params:', 'yields:']):
        return

    # Skip dunder methods — they often get auto-generated docs
    if func_name and func_name.startswith('__') and func_name.endswith('__'):
        return

    confidence = 0.72 if body_lines == 0 else 0.65
    issues.append(UnslopIssue(
        tell=TellCategory.VERBOSE_COMMENTS,
        severity=Severity.LOW,
        description=f'Docstring on trivial function ({func_name or "?"}) — only {body_lines} body lines',
        file_path=file_path,
        line=func_start + 1,
        code_snippet=doc_text[:80],
        suggested_fix='Remove docstring from trivial function or add meaningful content',
        confidence=confidence,
        research_source='Justin McKelvey — "9 Tells of AI-Generated Code", Tell #1',
    ))


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Apply verbose comment fixes to source code.

    Strategy:
    1. Pure restatements (e.g., "# increment the counter" above `counter += 1`)
       → removed entirely (add zero value)
    2. Verbose but useful comments → shortened to human length
       (e.g., "# increment the counter to reset the view" → "# reset the view")
    3. Truly useful comments → kept as-is

    Also removes single-line docstrings on trivial functions.

    Args:
        source: Original source code.
        issues: List of verbose comment issues to fix.

    Returns:
        Fixed source code with shortened/removed verbose comments.
    """
    # Group issues by line
    by_line: dict[int, list[UnslopIssue]] = {}
    for issue in issues:
        if issue.line:
            by_line.setdefault(issue.line, []).append(issue)

    lines = source.splitlines(keepends=True)
    lines_to_remove: set[int] = set()
    lines_to_replace: dict[int, str] = {}

    for line_num, line_issues in by_line.items():
        idx = line_num - 1
        if idx < 0 or idx >= len(lines):
            continue

        for issue in line_issues:
            if issue.tell != TellCategory.VERBOSE_COMMENTS:
                continue

            stripped = lines[idx].strip()
            prefix = ''
            if stripped.startswith('#'):
                prefix = '#'
            elif stripped.startswith('//'):
                prefix = '//'

            # Handle inline comments
            if prefix:
                # Extract comment body (after prefix)
                comment_body = stripped[len(prefix):].strip()

                # or if it has some value (shorten it)
                new_comment = _shorten_comment(comment_body)

                if new_comment is None:
                    # Pure restatement — remove the line
                    lines_to_remove.add(idx)
                elif new_comment != comment_body:
                    # Verbose but useful — shorten it
                    new_line = lines[idx].replace(comment_body, new_comment)
                    lines_to_replace[idx] = new_line

            # Handle single-line docstrings on trivial functions
            elif stripped.startswith('"""') or stripped.startswith("'''"):
                quote = '"""' if stripped.startswith('"""') else "'''"
                if stripped.count(quote) >= 2:
                    lines_to_remove.add(idx)
                else:
                    # Multi-line docstring — remove start line
                    lines_to_remove.add(idx)

    # Apply changes
    result = []
    for i, line in enumerate(lines):
        if i in lines_to_remove:
            continue
        if i in lines_to_replace:
            result.append(lines_to_replace[i])
        else:
            result.append(line)

    return ''.join(result)


def _shorten_comment(comment_body: str) -> str | None:
    """Shorten a verbose comment to human length.

    Strategy:
    - If the comment is a pure restatement (just verb + article + noun):
      return None (remove entirely)
    - If the comment has extra context after the restatement:
      extract and return only the useful part
    - If the comment is already human-length:
      return unchanged

    Args:
        comment_body: The comment text after the # or // prefix.

    Returns:
        Shortened comment body, or None if the comment should be removed.
    """
    if not comment_body:
        return None

    verb = _extract_imperative_verb(f'#{comment_body}')
    if verb is None:
        # No imperative verb detected — comment is likely human-written
        word_count = len(comment_body.split())
        if word_count <= 15:
            return comment_body
        else:
            # Verbose but no verb — keep as-is (might be a sentence)
            return comment_body

    # Comment starts with an imperative verb — check what follows
    after_verb = comment_body[len(verb):].strip()

    # If nothing follows the verb, it's a pure restatement — remove it
    if not after_verb:
        return None

    # If the comment is very short after the verb, it's likely a pure restatement
    # (e.g., "# increment the counter" → after "increment" → "the counter")
    if len(after_verb.split()) <= 3:
        # e.g., "the counter", "a new dictionary", "the result"
        tokens = after_verb.split()
        if len(tokens) <= 3 and tokens[0] in ('a', 'an', 'the'):
            # Pure restatement — remove it
            return None

    # Comment has extra context after the restatement
    # Extract the useful part (everything after the verb + article+noun pattern)
    useful_part = _extract_useful_context(comment_body, verb)

    if useful_part is None:
        # No useful context found — remove the comment
        return None

    return useful_part


def _extract_useful_context(comment: str, verb: str) -> str | None:
    """Extract the useful context from a comment.

    For comments like "# increment the counter to reset the view",
    this extracts "reset the view" (the WHY, not the WHAT).

    Strategy:
    - Skip the verb + article + noun phrase (e.g., "the counter")
    - Keep everything after (e.g., "to reset the view" → "reset the view")
    - The key is finding where the "what" ends and the "why" begins

    Args:
        comment: Full comment text (with # prefix).
        verb: The imperative verb detected at the start.

    Returns:
        The useful context portion, or None if no useful context found.
    """
    # Remove the verb prefix
    body = comment.lstrip('#/').strip()
    after_verb = body[len(verb):].strip()

    if not after_verb:
        return None

    # Primary strategy: look for "to" infinitive that introduces purpose
    # e.g., "increment the counter to reset the view" → "reset the view"
    # e.g., "create a new dictionary for the response" → "for the response"
    # e.g., "iterate through the data" → nothing useful (just "through the data")
    to_pos = after_verb.lower().find(' to ')
    if to_pos != -1:
        rest = after_verb[to_pos + 4:].strip()
        if rest:
            return rest

    # Secondary strategy: look for "for" that introduces purpose
    # e.g., "create a new dictionary for the response" → "for the response"
    for_pos = after_verb.lower().find(' for ')
    if for_pos != -1:
        rest = after_verb[for_pos + 5:].strip()
        if rest:
            return rest

    # No useful context found — the comment is just verb + object
    return None
