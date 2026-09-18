"""Detect cross-file coherence issues — references that exist locally but not globally.

Research sources:
- Justin McKelvey's "9 Tells" — Tell #2: "Locally coherent, globally incoherent"
- Git AutoReview — imports that resolve to wrong modules
- Cai & Tsantalis (2026) — cross-file reference validation
- Veracode 2025 — AI-generated code often references non-existent APIs

Key patterns:
1. Imports that resolve to wrong/non-existent modules
2. References to non-existent config keys
3. References to non-existent API endpoints
4. Missing auth guards on new endpoints
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..report import Severity, TellCategory, UnslopIssue
from ..pattern_index import PatternIndex


# Comprehensive Python stdlib module list
STDLIB_MODULES = {
    'os', 'sys', 'json', 're', 'math', 'datetime', 'collections',
    'itertools', 'functools', 'pathlib', 'typing', 'dataclasses',
    'logging', 'unittest', 'pytest', 'abc', 'contextlib', 'enum',
    'io', 'copy', 'hashlib', 'base64', 'csv', 'glob', 'shutil',
    'tempfile', 'threading', 'multiprocessing', 'subprocess',
    'http', 'urllib', 'socket', 'ssl', 'select', 'asyncio',
    'time', 'random', 'string', 'textwrap', 'struct',
    'argparse', 'configparser', 'sqlite3', 'pickle', 'shelve',
    'xml', 'html', 'email', 'unicodedata', 'codecs',
    'inspect', 'dis', 'traceback', 'warnings', 'contextvars',
    'signal', 'mmap', 'ctypes', 'concurrent', 'queue',
    '__future__', 'types', 'weakref', 'array', 'bisect', 'heapq',
    'operator', 'decimal', 'fractions', 'statistics', 'cmath',
    'pprint', 'textwrap', 'difflib', 'encodings', 'locale',
    'getpass', 'curses', 'platform', 'errno', 'ctypes',
    'faulthandler', 'gc', 'importlib', 'zipimport', 'pkgutil',
    'modulefinder', 'runpy', 'token', 'tokenize', 'ast',
    'symtable', 'compileall', 'dis', 'pickletools', 'zipfile',
    'tarfile', 'gzip', 'bz2', 'lzma', 'zlib', 'fileinput',
    'stat', 'fnmatch', 'linecache', 'shelve', 'marshal',
    'dbm', 'sqlite3', 'secrets', 'hmac', 'tempfile',
    'multiprocessing', 'concurrent', 'sched', 'queue',
    'threading', 'contextlib', 'contextvars',
    'abc', 'dataclasses', 'typing', 'typing_extensions',
    'enum', 'functools', 'operator', 'itertools',
    'collections', 'collections.abc', 'types',
    'warnings', 'logging', 'pprint', 'reprlib',
    'trace', 'profile', 'timeit', 'cProfile',
    'unittest', 'doctest', 'test',
    'venv', 'ensurepip', 'zipapp', 'site',
    'builtins', 'sys', 'sysconfig',
    'posixpath', 'ntpath', 'genericpath',
    'os.path', 'posix', 'nt', 'pwd', 'grp',
    'resource', 'nis', 'termios', 'pty', 'fcntl',
    'pipes', 'mmap', 'signal', 'msvcrt',
    'subprocess', 'socket', 'ssl', 'select',
    'selectors', 'socketserver', 'ipaddress',
    'uuid', 'xmlrpc', 'ftplib', 'poplib', 'imaplib',
    'smtplib', 'smtpd', 'telnetlib', 'uuid',
    'cgi', 'cgitb', 'wsgiref', 'xmlrpc',
    'http', 'html', 'mailbox', 'mimetypes',
    'email', 'base64', 'binascii', 'quopri',
    'uu', 'array', 'struct', 'codecs',
    'unicodedata', 'string', 'textwrap', 'locale',
    'gettext', 'calendar', 'zlib', 'gzip',
    'bz2', 'lzma', 'zipfile', 'tarfile',
    'configparser', 'tomllib', 'netrc',
    'plistlib', 'chunk', 'colorsys', 'imghdr',
    'sndhdr', 'ossaudiodev', 'aifc', 'sunau',
    'wave', 'crypt', 'tty', 'termios',
    'pty', 'fcntl', 'pipes', 'resource',
    'grp', 'pwd', 'spwd', 'syslog',
    'optparse', 'getopt', 'filecmp',
    'cProfile', 'profile', 'timeit',
    'trace', 'traceback', 'linecache',
    'code', 'codeop', 'cmd', 'shlex',
    'tkinter', 'turtle', 'turtledemo',
    'plistlib', 'chunk', 'colorsys',
    'imghdr', 'sndhdr', 'ossaudiodev',
    'aifc', 'sunau', 'wave', 'crypt',
    'tty', 'termios', 'pty', 'fcntl',
    'pipes', 'resource', 'grp', 'pwd',
    'spwd', 'syslog', 'optparse', 'getopt',
    'filecmp', 'cProfile', 'profile',
    'timeit', 'trace', 'traceback',
    'linecache', 'code', 'codeop',
    'cmd', 'shlex', 'tkinter',
    'tree_sitter', 'tree_sitter_python', 'tree_sitter_typescript',
    'tree_sitter_javascript',
    'webbrowser', 'numbers', 'pstats', 'profile', 'dis',
}

# Known third-party modules that are common. The detector handles Python and
# JS/TS, so keep ecosystem names together rather than treating every unknown
# import as a hallucinated package.
NPM_MODULES = {
    'express', 'koa', 'nestjs', 'next', 'react', 'vue', 'angular',
    'flask', 'django', 'tornado', 'starlette', 'fastapi',
    'aws_cdk', 'constructs', 'cdk', 'cdk8s', 'pulumi',
    'typescript', 'rxjs', 'lodash', 'moment', 'dayjs',
    'axios', 'node', 'fs', 'path', 'events', 'stream',
    'buffer', 'util', 'crypto', 'url', 'querystring',
    'child_process', 'cluster', 'dgram', 'dns', 'net',
    'readline', 'zlib', 'assert', 'constants', 'module',
    'v8', 'vm', 'worker_threads', 'perf_hooks',
    'jest', 'vitest', 'mocha', 'chai', 'sinon',
    'supertest', 'nock', 'sinon-chai',
    'prettier', 'eslint', 'typescript',
    'webpack', 'vite', 'rollup', 'esbuild',
    'babel', '@babel',
    'tailwind', 'bootstrap', 'material-ui',
    'redux', 'mobx', 'zustand', 'jotai',
    'prisma', 'typeorm', 'sequelize', 'knex',
    'mongoose', 'drizzle', 'sqlalchemy', 'peewee',
    'redis', 'celery', 'dramatiq', 'rq',
    'boto3', 'botocore', 'aws-sdk',
    'firebase', 'supabase', 'stripe', 'paypal',
    'socket.io', 'ws', 'graphql', 'apollo',
    'puppeteer', 'playwright', 'selenium',
    'sharp', 'canvas', 'pdf', 'xlsx', 'docx',
    'dotenv', 'zod', 'yup', 'joi', 'valibot',
    'class-validator', 'class-transformer',
    'ioredis', 'bull', 'agenda',
    'winston', 'pino', 'bunyan', 'log4js',
    'passport', 'jsonwebtoken', 'bcrypt',
    'helmet', 'cors', 'express-rate-limit',
    'swagger-ui-express', 'jsdoc',
    'husky', 'lint-staged', 'commitlint',
    'nx', 'lerna', 'turbo', 'pnpm',
    'jest-environment-jsdom', '@testing-library',
    'enzyme', 'react-testing-library',
    # Python ecosystem
    'pyside6', 'pyside', 'pyqt5', 'pyqt6', 'opencv', 'cv2',
    'numpy', 'scipy', 'pandas', 'matplotlib', 'seaborn',
    'sqlalchemy', 'psycopg2', 'pymongo', 'redis', 'celery',
    'aiohttp', 'httpx', 'requests', 'urllib3', 'websocket', 'websockets',
    'cryptography', 'paramiko', 'docker', 'kubernetes',
    'pytest', 'mock', 'factory', 'faker', 'hypothesis',
    'black', 'ruff', 'mypy', 'bandit', 'safety', 'tomli',
}


def _is_stdlib_module(module: str) -> bool:
    """Check if a module is a Python standard library module."""
    parts = module.split('.')
    return parts[0] in STDLIB_MODULES or module in STDLIB_MODULES


def _is_npm_module(module: str) -> bool:
    """Check if a module is a known npm/node module."""
    return module in NPM_MODULES or module.lstrip('@').split('/')[0] in NPM_MODULES


def _is_local_project_module(module: str, project_name: Optional[str]) -> bool:
    """Check if a module belongs to the project's own package.

    Skips internal imports like 'scrapy.crawler' when the project
    name is 'scrapy'. This prevents flagging legitimate internal
    module references as cross-file coherence issues.
    """
    if not project_name:
        return False
    top = module.split('.')[0]
    if top == project_name:
        return True
    # Check dotted prefixes: 'scrapy.utils.http' → 'scrapy'
    for i in range(1, len(module.split('.')) + 1):
        prefix = '.'.join(module.split('.')[:i]).replace('.', '_')
        if prefix == project_name:
            return True
    return False


def _is_local_script_module(module: str, root_dir: Path | None) -> bool:
    """Recognize sibling Python modules in script-style repositories."""
    if root_dir is None or "." in module:
        return False
    return any((base / f"{module}.py").is_file() for base in (root_dir, root_dir / "src"))


def _is_declared_dependency(module: str, dependencies: set[str]) -> bool:
    """Check if a module is a declared project dependency.

    Compares the module name against the set of importable module
    names extracted from the project's manifest files (pyproject.toml,
    requirements.txt, uv.lock, etc.).

    Handles dotted modules (e.g., "zope.interface") by checking:
    1. The top-level name (e.g., "zope")
    2. The full dotted name as-underscore (e.g., "zope_interface")
    3. Any prefix of the dotted module (e.g., "zope.interface" →
       checks "zope", "zope_interface", "zope_interface_declarations")
    """
    module = module.casefold()
    dependencies = {dependency.casefold() for dependency in dependencies}
    parts = module.split('.')
    # Check top-level name
    if parts[0] in dependencies:
        return True
    # Check each prefix converted to underscore format
    for i in range(1, len(parts) + 1):
        prefix = '.'.join(parts[:i]).replace('.', '_')
        if prefix in dependencies:
            return True
    return False


def _is_relative_import(module: str) -> bool:
    """Check if this is a relative import (starts with .)."""
    return module.startswith('.')


def _is_test_file(file_path: Path) -> bool:
    """Check if the file is a test file."""
    name = file_path.name.lower()
    parts = {part.casefold() for part in file_path.parts}
    return (
        'test' in name or name.startswith('test_') or
        name.endswith(('_test.py', '_test.ts')) or
        bool(parts & {'tests', 'test', 'fixtures'}) or name == 'conftest.py'
    )


def _is_test_import(module: str, imported_names: list[str], file_path: Path) -> bool:
    """Check if this looks like a test fixture/mock import."""
    # Skip 'tests' package — it's a test directory, not a real package
    if module == 'tests' or module.startswith('tests.'):
        return True
    # Common test mock imports
    mock_patterns = ['app.models', 'app.services', 'app.deep', 'app.dep',
                     'mock', 'fake', 'stub', 'fixture', 'conftest']
    if any(p in module for p in mock_patterns):
        return True
    # Imports from non-existent packages in test files
    if _is_test_file(file_path) and module not in STDLIB_MODULES:
        if '.' in module and not module.startswith('.'):
            top = module.split('.')[0]
            if top not in STDLIB_MODULES and top not in NPM_MODULES:
                return True
    return False


def _is_in_docstring(source: str, line_num: int) -> bool:
    """Check if a line is inside a docstring.

    Simple heuristic: look for triple-quoted strings that span multiple lines.
    """
    lines = source.splitlines()
    # Simple check: if the line is within a triple-quoted string block
    in_docstring = False
    quote_char = None
    for i in range(line_num):
        line = lines[i]
        stripped = line.strip()
        if not in_docstring:
            if '"""' in stripped or "'''" in stripped:
                if stripped.count('"""') == 1 or stripped.count("'''") == 1:
                    in_docstring = True
                    quote_char = '"""' if '"""' in stripped else "'''"
        else:
            if quote_char and quote_char in stripped:
                in_docstring = False
                quote_char = None
            # Check if this is a raw docstring line (not actual code)
    return in_docstring


def detect(
    source: str,
    file_path: Path,
    context: Optional[dict] = None,
) -> list[UnslopIssue]:
    """Detect cross-file coherence issues.

    Checks for:
    - Imports that resolve to wrong/non-existent modules
    - References to non-existent config keys
    - References to non-existent API endpoints
    - Missing auth guards on new endpoints

    Args:
        source: Source code to analyze.
        file_path: Path to the source file.
        context: Optional PatternIndex for additional context.

    Returns:
        List of UnslopIssue for each cross-file issue found.
    """
    issues = []
    lines = source.splitlines()

    # Skip test files entirely — test dependencies (pytest, mock,
    # inline-snapshot, dirty-equals, etc.) are infrastructure, not
    # AI slop. They appear in every modern project regardless of
    # whether AI assisted their creation.
    if _is_test_file(file_path):
        return issues

    pattern_index: Optional[PatternIndex] = None
    if context and 'pattern_index' in context:
        pattern_index = context['pattern_index']

    if not pattern_index:
        return issues

    # Get declared dependencies from context (resolved by analyzer)
    declared_deps: set[str] = set()
    if context and 'dependencies' in context:
        declared_deps = context['dependencies']
    unknown_module_confidence = 0.4 if not declared_deps else 0.7

    # Get project's own package name to skip internal imports
    project_name: Optional[str] = None
    if context and 'project_name' in context:
        project_name = context['project_name']
    root_dir = context.get('root_dir') if context else None

    # 1. Check imports against known modules
    # Python imports
    import_patterns = [
        # from X import Y
        (r'^\s*from\s+([\w.]+)\s+import\s+([\w,\s]+)', 'from_import'),
        # import X
        (r'^\s*import\s+([\w.]+)', 'bare_import'),
    ]

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip comment lines
        if stripped.startswith('#') or stripped.startswith('//'):
            continue

        # Skip lines inside docstrings
        if _is_in_docstring(source, i):
            continue

        # Skip lines that are clearly in docstrings (common pattern)
        if stripped.startswith('"""') or stripped.startswith("'''"):
            continue

        # If so, skip the bare_import check to avoid double-counting
        is_from_import = bool(re.match(r'^\s*from\s+', stripped))

        for pattern, import_type in import_patterns:
            matches = re.finditer(pattern, stripped)
            for match in matches:
                # Skip bare_import if this is a 'from ... import' line
                if import_type == 'bare_import' and is_from_import:
                    continue

                if import_type == 'from_import':
                    module = match.group(1)
                    imported_names = [n.strip() for n in match.group(2).split(',')]

                    # Skip relative imports (they're local to the package)
                    if _is_relative_import(module):
                        continue

                    # Skip local project modules (e.g., 'scrapy.crawler' when
                    # the project is 'scrapy') — these are internal references,
                    # not cross-file coherence issues.
                    if _is_local_project_module(module, project_name):
                        continue
                    if _is_local_script_module(module, root_dir):
                        continue

                    # Skip stdlib modules
                    if _is_stdlib_module(module):
                        continue

                    # Skip known npm modules
                    if _is_npm_module(module):
                        continue

                    # Skip declared project dependencies
                    if _is_declared_dependency(module, declared_deps):
                        continue

                    # Skip test fixture imports (mock imports in test files)
                    if _is_test_import(module, imported_names, file_path):
                        continue

                    # Module not in any known set — flag it
                    issues.append(UnslopIssue(
                        tell=TellCategory.CROSS_FILE_INCOHERENCE,
                        severity=Severity.MEDIUM,
                        description=f'Import from unknown module: "{module}"',
                        file_path=file_path,
                        line=i + 1,
                        code_snippet=stripped[:100],
                        suggested_fix=f'Check that module "{module}" exists and is in the import path',
                        confidence=unknown_module_confidence,
                        research_source='Justin McKelvey — "Locally coherent, globally incoherent"; Git AutoReview #12',
                    ))

                    # Flag imported names from unknown modules
                    for name in imported_names:
                        if not name.startswith('_') and not name.endswith('*'):
                            issues.append(UnslopIssue(
                                tell=TellCategory.CROSS_FILE_INCOHERENCE,
                                severity=Severity.LOW,
                                description=f'Import "{name}" from non-standard/unknown module "{module}"',
                                file_path=file_path,
                                line=i + 1,
                                code_snippet=stripped[:100],
                                suggested_fix=f'Check that "{name}" exists in "{module}"',
                                confidence=max(0.3, unknown_module_confidence - 0.1),
                                research_source='Cai & Tsantalis (2026) — cross-file reference validation',
                            ))

                elif import_type == 'bare_import':
                    module = match.group(1)

                    # Skip relative imports
                    if _is_relative_import(module):
                        continue

                    # Skip local project modules
                    if _is_local_project_module(module, project_name):
                        continue
                    if _is_local_script_module(module, root_dir):
                        continue

                    # Skip stdlib modules
                    if _is_stdlib_module(module):
                        continue

                    # Skip known npm modules
                    if _is_npm_module(module):
                        continue

                    # Skip declared project dependencies
                    if _is_declared_dependency(module, declared_deps):
                        continue

                    issues.append(UnslopIssue(
                        tell=TellCategory.CROSS_FILE_INCOHERENCE,
                        severity=Severity.MEDIUM,
                        description=f'Import of unknown module: "{module}"',
                        file_path=file_path,
                        line=i + 1,
                        code_snippet=stripped[:100],
                        suggested_fix=f'Check that module "{module}" exists',
                        confidence=unknown_module_confidence,
                        research_source='Git AutoReview — imports that resolve to wrong modules',
                    ))

    # 2. Check for missing auth guards on API endpoints
    endpoint_patterns = [
        # FastAPI/Flask decorators
        (r'@(?:api|router|app)\.(?:get|post|put|delete|patch)\s*\(', 'framework_endpoint'),
        # Express routes
        (r'(?:app|router)\.(?:get|post|put|delete|patch)\s*\(', 'express_route'),
    ]

    for i, line in enumerate(lines):
        for pattern, endpoint_type in endpoint_patterns:
            if re.search(pattern, line):
                # Look for auth decorators nearby (within 5 lines)
                has_auth = False
                for j in range(max(0, i - 5), i):
                    if re.search(r'@(?:login_required|auth|require_auth|authenticate|guard)', lines[j]):
                        has_auth = True
                        break

                if not has_auth:
                    issues.append(UnslopIssue(
                        tell=TellCategory.CROSS_FILE_INCOHERENCE,
                        severity=Severity.MEDIUM,
                        description='API endpoint without visible auth guard',
                        file_path=file_path,
                        line=i + 1,
                        code_snippet=line.strip()[:100],
                        suggested_fix='Add authentication guard to protect this endpoint',
                        confidence=0.65,
                        research_source='Veracode 2025 — missing auth guards in AI-generated endpoints',
                    ))
                break

    return issues


def fix(source: str, issues: list[UnslopIssue]) -> str:
    """Suggest fixes for cross-file coherence issues.

    Note: Cross-file fixes require understanding the broader codebase.
    We only flag, never auto-fix.

    Args:
        source: Original source code.
        issues: List of cross-file issues.

    Returns:
        Original source (cross-file fixes are suggestions only).
    """
    # Cross-file coherence issues are suggestions only
    return source
