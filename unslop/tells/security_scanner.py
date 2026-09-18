"""Detect security vulnerabilities commonly introduced by AI-generated code.

For Python files: delegates to Bandit (PyCQA) — AST-based security scanner.
For JS/TS files: custom detection for XSS and CORS patterns.

Research sources:
- Bandit (PyCQA) — Python SAST, 42 AST-based security checks
- Justin McKelvey's "9 Tells" — AI code often lacks security awareness
- Veracode 2025 Report — SQL injection and hardcoded secrets top AI-generated vulns
- OWASP Top 10 — A01:2021 Broken Access Control, A03:2021 Injection, A07:2021 XSS
- Git AutoReview — missing input validation, unsafe patterns

Key patterns:
- Python: SQL injection, hardcoded secrets, weak crypto, shell injection, SSRF, eval
- JS/TS: XSS (innerHTML, document.write), CORS misconfiguration
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..report import Severity, TellCategory, UnslopIssue

# XSS patterns (JavaScript)
XSS_PATTERNS = [
    (r'\.innerHTML\s*=', 'unsafe_innerhtml'),
    (r'document\.write\s*\(', 'unsafe_document_write'),
    (r'\.outerHTML\s*=', 'unsafe_outerhtml'),
    (r'jQuery\s*\(\s*.*?\)\.html\s*\(', 'unsafe_jquery_html'),
]

# CORS misconfiguration
CORS_PATTERNS = [
    (r'Access-Control-Allow-Origin:\s*\*', 'wildcard_cors'),
    (r'Access-Control-Allow-Origin:\s*\*"', 'wildcard_cors_quote'),
    (r'allowCredentials:\s*true.*origin:\s*\*', 'cors_credentials_wildcard'),
    (r'origin:\s*["\']\*["\'].*allowCredentials', 'cors_wildcard_credentials'),
]

# Bandit test ID → (description, default_severity, suggested_fix)
BANDIT_FIXES = {
    # SQL injection
    'B608': ('Possible SQL injection via string-based query construction', 'critical',
             'Use parameterized queries (e.g., cursor.execute("SELECT * FROM t WHERE id = ?", (id,)))'),
    'B610': ('Django raw SQL query — use ORM instead', 'high', 'Use Django ORM query methods instead of raw SQL'),
    'B611': ('Django raw SQL query — use ORM instead', 'high', 'Use Django ORM query methods instead of raw SQL'),
    # Hardcoded passwords
    'B105': ('Hardcoded password string detected', 'critical',
             'Move secrets to environment variables or a secrets manager'),
    'B106': ('Hardcoded password function argument', 'high',
             'Pass credentials via environment variables or a secrets manager'),
    'B107': ('Hardcoded password default value', 'medium',
             'Remove hardcoded default password; use environment variables'),
    # Shell injection
    'B404': ('Consider possible security implications associated with subprocess module', 'medium',
             'Avoid subprocess; if needed, use list args and shell=False'),
    'B602': ('Subprocess call with shell=True identified', 'critical',
             'Use shell=False and pass arguments as a list'),
    'B603': ('Subprocess call without shell=True — check for injection', 'low',
             'Verify arguments are sanitized before passing to subprocess'),
    'B604': ('Any function with shell=True detected', 'critical',
             'Use shell=False and pass arguments as a list'),
    'B605': ('Starting a process with a shell — potential injection', 'high',
             'Use subprocess with shell=False and list arguments'),
    'B606': ('Starting a process without a shell — check for injection', 'medium',
             'Verify arguments are sanitized before passing'),
    'B607': ('Starting a process with a partial command path', 'medium',
             'Use the full path to the command'),
    'B609': ('Linux shell wildcard injection', 'high',
             'Sanitize wildcard patterns to prevent injection'),
    # Crypto
    'B324': ('Use of weak hashlib algorithm', 'high',
             'Use SHA-256 or stronger (e.g., hashlib.sha256)'),
    'B505': ('Weak cryptographic algorithm (TLS 1.0/1.1)', 'high',
             'Use TLS 1.2 or higher'),
    'B506': ('Unknown OpenSSL cipher', 'high',
             'Use a known secure cipher suite'),
    'B507': ('SSH no host key verification', 'high',
             'Enable host key verification (verify=True)'),
    'B509': ('SNMP insecure version', 'medium',
             'Use SNMPv3 with authentication and encryption'),
    'B510': ('SNMP weak crypto', 'medium',
             'Use SNMPv3 with authentication and encryption'),
    # SSRF / Network
    'B501': ('Request without certificate validation', 'high',
             'Enable SSL certificate validation'),
    'B511': ('Request without timeout', 'medium',
             'Add a timeout parameter to requests'),
    # XSS / Template
    'B701': ('Jinja2 autoescape is False — XSS risk', 'high',
             'Enable autoescape or use markupsafe.escape'),
    'B703': ('Django mark_safe used — XSS risk', 'high',
             'Use Django safe string utilities or escape user input'),
    'B704': ('MarkupSafe markup used — XSS risk', 'high',
             'Escape user-generated content before rendering'),
    'B702': ('Use of Mako templates — check for XSS', 'medium',
             'Ensure autoescape is enabled in Mako templates'),
    # Other
    'B101': ('Assert statement used — remove in production', 'low',
             'Remove assert statements in production code'),
    'B102': ('Exec or eval used — potential code injection', 'critical',
             'Never use exec/eval on user input; use safe alternatives'),
    'B110': ('Try/except with pass — silently swallows exceptions', 'medium',
             'Handle exceptions properly or log them'),
    'B112': ('Try/except with continue — may hide errors', 'medium',
             'Handle exceptions properly or log them'),
    'B613': ('Trojansource — bidirectional escape characters', 'critical',
             'Remove bidirectional escape characters from source'),
    'B103': ('Set bad file permissions', 'medium',
             'Use restrictive file permissions (e.g., 0o600)'),
    'B104': ('Hardcoded bind to all interfaces', 'medium',
             'Bind to 127.0.0.1 or a specific interface'),
    'B108': ('Hardcoded temporary directory', 'low',
             'Use tempfile.gettempdir() instead of hardcoded path'),
    'B202': ('Tarfile unsafe members', 'high',
             'Validate tarfile members to prevent path traversal'),
    'B601': ('Paramiko call — verify host key', 'medium',
             'Enable host key verification in paramiko'),
    'B614': ('PyTorch load with potentially unsafe file', 'medium',
             'Only load PyTorch files from trusted sources'),
    'B615': ('HuggingFace unsafe download', 'medium',
             'Verify model sources before downloading'),
    'B502': ('SSL with bad version', 'high',
             'Use a secure TLS version'),
    'B503': ('SSL with bad defaults', 'high',
             'Configure SSL with secure defaults'),
    'B504': ('SSL with no version specified', 'medium',
             'Explicitly specify a secure TLS version'),
    'B612': ('Logging config insecure listen', 'medium',
             'Use secure logging configuration'),
}

# Bandit severity → our severity
BANDIT_SEVERITY_MAP = {
    'low': Severity.LOW,
    'medium': Severity.MEDIUM,
    'high': Severity.HIGH,
    'critical': Severity.CRITICAL,
}


def _run_bandit(file_path: Path) -> list[UnslopIssue]:
    """Run Bandit on a Python file and convert results to UnslopIssue list.

    Args:
        file_path: Path to the Python source file.

    Returns:
        List of UnslopIssue for each security issue found.
    """
    # Bandit is an optional analysis backend.  A source scan should still be
    # useful in minimal/offline environments where the optional dependency was
    # not installed; callers can run the dedicated security extra when they
    # want Bandit findings.
    try:
        from bandit.core import config as bcfg, manager
    except ImportError:
        return []

    b_config = bcfg.BanditConfig()
    b_mgr = manager.BanditManager(config=b_config, agg_type='file')
    b_mgr.files_list = [file_path]
    b_mgr.run_tests()

    issues = []
    for issue in b_mgr.results:
        test_id = issue.test_id
        fix_info = BANDIT_FIXES.get(test_id, (f'Security issue: {test_id}', 'medium', 'Review and fix'))

        description, default_sev, suggested_fix = fix_info
        severity = BANDIT_SEVERITY_MAP.get(default_sev, Severity.MEDIUM)

        # Bandit confidence: HIGH = more certain, MEDIUM = possible, LOW = unsure
        confidence = 0.9 if issue.confidence == 'HIGH' else 0.7 if issue.confidence == 'MEDIUM' else 0.5

        issues.append(UnslopIssue(
            tell=TellCategory.SECURITY_VULNERABILITY,
            severity=severity,
            description=description,
            file_path=file_path,
            line=issue.lineno,
            code_snippet=issue.text[:100] if issue.text else '',
            suggested_fix=suggested_fix,
            confidence=confidence,
            research_source=f'Bandit {test_id} (PyCQA) — AST-based static analysis',
        ))

    return issues


def _scan_js_ts_xss_cors(source: str, file_path: Path) -> list[UnslopIssue]:
    """Scan JS/TS source for XSS and CORS vulnerabilities.

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.

    Returns:
        List of UnslopIssue for each security issue found.
    """
    issues = []
    lines = source.splitlines()

    # XSS
    for i, line in enumerate(lines):
        for pattern, category in XSS_PATTERNS:
            if re.search(pattern, line):
                issues.append(UnslopIssue(
                    tell=TellCategory.SECURITY_VULNERABILITY,
                    severity=Severity.HIGH,
                    description=f'XSS risk: {category}',
                    file_path=file_path,
                    line=i + 1,
                    code_snippet=line.strip()[:100],
                    suggested_fix='Use textContent or sanitize HTML before inserting',
                    confidence=0.8,
                    research_source='OWASP Top 10 A07:2021 — Cross-Site Scripting; Git AutoReview',
                ))
                break

    # CORS
    for i, line in enumerate(lines):
        for pattern, category in CORS_PATTERNS:
            if re.search(pattern, line):
                issues.append(UnslopIssue(
                    tell=TellCategory.SECURITY_VULNERABILITY,
                    severity=Severity.HIGH,
                    description=f'CORS misconfiguration: {category}',
                    file_path=file_path,
                    line=i + 1,
                    code_snippet=line.strip()[:100],
                    suggested_fix='Specify allowed origins explicitly instead of wildcard (*)',
                    confidence=0.85,
                    research_source='OWASP Top 10 A01:2021 — Broken Access Control',
                ))
                break

    return issues


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect security vulnerabilities in source code.

    For Python files: delegates to Bandit (PyCQA) — AST-based security scanner.
    For JS/TS files: custom detection for XSS and CORS patterns.

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex for additional context.

    Returns:
        List of UnslopIssue for each security issue found.
    """
    suffix = file_path.suffix.lower()

    if suffix == '.py':
        return _run_bandit(file_path)
    elif suffix in ('.ts', '.tsx', '.js', '.jsx'):
        return _scan_js_ts_xss_cors(source, file_path)

    return []


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Suggest fixes for security issues.

    Note: Security fixes are suggestions only — never auto-fix.
    Security changes require human review.

    Args:
        source: Original source code.
        issues: List of security issues.

    Returns:
        Original source (security fixes are suggestions only).
    """
    # Security issues are suggestions only — never auto-fix
    return source
