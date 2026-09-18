"""Resolve declared Python dependencies from project manifest files.

Discovers and parses dependency declarations from:
  - pyproject.toml (PEP 621 / Poetry / Hatch)
  - requirements.txt / requirements-*.txt (pip format)
  - setup.py (install_requires)
  - uv.lock (lock file)

Extracts the top-level importable module name from each dependency
(e.g., "typing-extensions" → "typing_extensions", "PyOpenSSL" → "OpenSSL").

Usage:
    resolver = DependencyResolver(repo_root="/path/to/repo")
    deps = resolver.resolve()  # set of importable module names
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# Map PyPI package names to their importable module names
# (many differ due to hyphens, case, or different distribution names)
_PACKAGE_TO_MODULE: dict[str, str] = {
    # Common cases
    'pyside6': 'PySide6',
    'pysmb': 'smb',
    'typing-extensions': 'typing_extensions',
    'pyopenssl': 'OpenSSL',
    'pyyaml': 'yaml',
    'beautifulsoup4': 'bs4',
    'scikit-learn': 'sklearn',
    'scikit-image': 'skimage',
    'python-dateutil': 'dateutil',
    'python-dotenv': 'dotenv',
    'pillow': 'PIL',
    'opencv-python': 'cv2',
    'python-slugify': 'slugify',
    'python-jose': 'jose',
    'pydantic': 'pydantic',
    'pydantic-core': 'pydantic_core',
    'pydantic-settings': 'pydantic_settings',
    'pydantic-extra-types': 'pydantic_extra_types',
    'pydantic-ai': 'pydantic_ai',
    'pydantic-settings': 'pydantic_settings',
    'google-cloud-storage': 'google.cloud.storage',
    'google-cloud-core': 'google.cloud.core',
    'google-auth': 'google.auth',
    'google-auth-httplib2': 'google.auth.httplib2',
    'google-auth-oauthlib': 'google.auth.oauthlib',
    'googleapis-common-protos': 'googleapis.common.protos',
    'azure-storage-blob': 'azure.storage.blob',
    'azure-identity': 'azure.identity',
    'azure-core': 'azure.core',
    'azure-keyvault-secrets': 'azure.keyvault.secrets',
    'azure-keyvault-certificates': 'azure.keyvault.certificates',
    'azure-keyvault-keys': 'azure.keyvault.keys',
    'fastapi-cli': 'fastapi_cli',
    'annotated-doc': 'annotated_doc',
    'pytest-asyncio': 'pytest_asyncio',
    'pytest-cov': 'pytest_cov',
    'pytest-mock': 'pytest_mock',
    'pytest-xdist': 'pytest_xdist',
    'pytest-sugar': 'pytest_sugar',
    'pytest-benchmark': 'pytest_benchmark',
    'pytest-html': 'pytest_html',
    'pytest-playwright': 'playwright',
    'pytest-snapshot': 'pytest_snapshot',
    'pytest-lazy-fixture': 'pytest_lazy_fixture',
    'pytest-codspeed': 'pytest_codspeed',
    'pytest-twisted': 'pytest_twisted',
    'inline-snapshot': 'inline_snapshot',
    'dirty-equals': 'dirty_equals',
    'pydispatcher': 'PyDispatcher',
    'pypydocker': 'pydodocker',
    'brotlicffi': 'brotlicffi',
    'secretstorage': 'secretstorage',
    'pycryptodomex': 'Cryptodome',
    'yt-dlp-ejs': 'yt_dlp_ejs',
    'curl-cffi': 'curl_cffi',
    'aiofiles': 'aiofiles',
    'aiosqlite': 'aiosqlite',
    'aioredis': 'aioredis',
    'aiohttp': 'aiohttp',
    'httpx': 'httpx',
    'orjson': 'orjson',
    'msgspec': 'msgspec',
    'pygments': 'pygments',
    'sniffio': 'sniffio',
    'idna': 'idna',
    'certifi': 'certifi',
    'charset-normalizer': 'charset_normalizer',
    'chardet': 'chardet',
    'multidict': 'multidict',
    'yarl': 'yarl',
    'async-timeout': 'async_timeout',
    'attrs': 'attr',
    'cattrs': 'cattrs',
    'dataclasses-json': 'dataclasses_json',
    'tomli': 'tomli',
    'tomllib': 'tomllib',
    'exceptiongroup': 'exceptiongroup',
    'wrapt': 'wrapt',
    'importlib-metadata': 'importlib_metadata',
    'importlib-resources': 'importlib_resources',
    'zipp': 'zipp',
    'packaging': 'packaging',
    'platformdirs': 'platformdirs',
    'pluggy': 'pluggy',
    'iniconfig': 'iniconfig',
    'plumbum': 'plumbum',
    'sh': 'sh',
    'invoke': 'invoke',
    'nox': 'nox',
    'tox': 'tox',
    'pre-commit': 'pre_commit',
    'black': 'black',
    'isort': 'isort',
    'flake8': 'flake8',
    'mypy': 'mypy',
    'pyright': 'pyright',
    'ruff': 'ruff',
    'pylint': 'pylint',
    'bandit': 'bandit',
    'coverage': 'coverage',
    'hypothesis': 'hypothesis',
    'sphinx': 'sphinx',
    'mkdocs': 'mkdocs',
    'tabulate': 'tabulate',
    'tqdm': 'tqdm',
    'colorama': 'colorama',
    'termcolor': 'termcolor',
    'click': 'click',
    'typer': 'typer',
    'rich': 'rich',
    'textual': 'textual',
    'prompt-toolkit': 'prompt_toolkit',
    'plumbum': 'plumbum',
    'sh': 'sh',
    'invoke': 'invoke',
    'nox': 'nox',
    'tox': 'tox',
    'pre-commit': 'pre_commit',
    'black': 'black',
    'isort': 'isort',
    'flake8': 'flake8',
    'mypy': 'mypy',
    'pyright': 'pyright',
    'ruff': 'ruff',
    'pylint': 'pylint',
    'bandit': 'bandit',
    'coverage': 'coverage',
    'hypothesis': 'hypothesis',
    'sphinx': 'sphinx',
    'mkdocs': 'mkdocs',
    'tabulate': 'tabulate',
    'tqdm': 'tqdm',
    'colorama': 'colorama',
    'termcolor': 'termcolor',
    'click': 'click',
    'typer': 'typer',
    'rich': 'rich',
    'textual': 'textual',
    'prompt_toolkit': 'prompt_toolkit',
}


def _normalize_package_name(name: str) -> str:
    """Normalize a PyPI package name to a lowercase, hyphen-free string."""
    return re.sub(r'[-_.]+', '-', name.strip().lower()).strip('-')


def _package_to_import_name(package_name: str) -> str:
    """Convert a PyPI package name to its importable module name."""
    normalized = _normalize_package_name(package_name)
    if normalized in _PACKAGE_TO_MODULE:
        return _PACKAGE_TO_MODULE[normalized]
    # Default: replace hyphens with underscores, lowercase
    return normalized.replace('-', '_')


def _parse_pep508_dep(dep_string: str) -> Optional[str]:
    """Parse a PEP 508 dependency string and return the importable module name.

    Handles:
      - Simple: "requests>=2.0"
      - With extras: "requests[security]>=2.0"
      - With markers: "pyOpenSSL>=22.0; platform_python_implementation == 'CPython'"
      - With URLs: "package @ https://..."
    """
    dep_string = dep_string.strip()
    if not dep_string:
        return None

    # Remove URL-based deps: "package @ https://..."
    if ' @ ' in dep_string:
        dep_string = dep_string.split(' @ ')[0].strip()

    # Remove extras: "package[extra1,extra2]"
    dep_string = re.sub(r'\[.*?\]', '', dep_string)

    # Remove version specifiers: ">=1.0", "<2.0", "==1.0.0", etc.
    dep_string = re.split(r'[><=!~;]', dep_string)[0].strip()

    # Remove environment markers (after ;)
    if ';' in dep_string:
        dep_string = dep_string.split(';')[0].strip()

    if not dep_string:
        return None

    return _package_to_import_name(dep_string)


def _parse_pyproject_toml(pyproject_path: Path) -> set[str]:
    """Parse dependencies from a pyproject.toml file (PEP 621 / Poetry)."""
    deps: set[str] = set()
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return deps

    try:
        with open(pyproject_path, 'rb') as f:
            data = tomllib.load(f)
    except Exception:
        return deps

    # PEP 621 [project] section
    project = data.get('project', {})
    # Poetry [tool.poetry] section
    poetry = data.get('tool', {}).get('poetry', {})

    # PEP 621 dependencies
    for dep_str in project.get('dependencies', []):
        name = _parse_pep508_dep(dep_str)
        if name:
            deps.add(name)

    # PEP 621 optional dependencies
    opt_deps = project.get('optional-dependencies', {})
    for group_deps in opt_deps.values():
        for dep_str in group_deps:
            name = _parse_pep508_dep(dep_str)
            if name:
                deps.add(name)

    # Poetry dependencies
    poetry_deps = poetry.get('dependencies', {})
    for pkg_name in poetry_deps:
        if pkg_name.lower() != 'python':  # Skip python version constraint
            name = _package_to_import_name(pkg_name)
            if name:
                deps.add(name)

    # Poetry optional dependencies
    for group_deps in poetry.get('extras', {}).values():
        pass  # extras are just markers, deps are in dependencies

    # Poetry dev dependencies (group dependencies in newer Poetry)
    for group_name, group_config in poetry.get('group', {}).items():
        group_deps = group_config.get('dependencies', {})
        for pkg_name in group_deps:
            if pkg_name.lower() != 'python':
                name = _package_to_import_name(pkg_name)
                if name:
                    deps.add(name)

    # Poetry extras (older Poetry format)
    for dep_str in poetry.get('extras', {}):
        pass  # extras are just markers

    # Poetry dev dependencies (older Poetry format)
    for dep_str in poetry.get('dev-dependencies', {}):
        pass  # handled via group

    # Poetry extra dependencies
    for extra_name, extra_deps in poetry.get('extras-dependencies', {}).items():
        for dep_str in extra_deps:
            name = _parse_pep508_dep(dep_str)
            if name:
                deps.add(name)

    # Direct dependencies
    for dep_str in project.get('dependencies', []):
        name = _parse_pep508_dep(dep_str)
        if name:
            deps.add(name)

    # Optional dependencies — include all of them
    opt_deps = project.get('optional-dependencies', {})
    for group_deps in opt_deps.values():
        for dep_str in group_deps:
            name = _parse_pep508_dep(dep_str)
            if name:
                deps.add(name)

    return deps


def _parse_requirements_txt(req_path: Path) -> set[str]:
    """Parse dependencies from a requirements.txt file."""
    deps: set[str] = set()
    try:
        with open(req_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip comments, empty lines, -r/-e/-i/-c flags
                if not line or line.startswith('#') or line.startswith('-'):
                    continue
                # Skip lines like "-e .[socks]"
                if line.startswith('-e'):
                    # Extract the package name after -e
                    pkg = line[2:].strip()
                    pkg = re.sub(r'\[.*?\]', '', pkg)
                    if pkg:
                        name = _package_to_import_name(pkg)
                        if name:
                            deps.add(name)
                    continue
                name = _parse_pep508_dep(line)
                if name:
                    deps.add(name)
    except Exception:
        pass
    return deps


def _parse_requirements_dir(repo_root: Path) -> set[str]:
    """Parse dependencies from requirements/ subdirectory files.

    Some projects (e.g., celery) store requirements in requirements/*.txt.
    We parse all .txt files in the requirements/ directory.
    """
    deps: set[str] = set()
    req_dir = repo_root / 'requirements'
    if not req_dir.is_dir():
        return deps
    for req_file in sorted(req_dir.glob('*.txt')):
        deps |= _parse_requirements_txt(req_file)
    # Also check requirements/extras/ subdirectory
    extras_dir = req_dir / 'extras'
    if extras_dir.is_dir():
        for req_file in sorted(extras_dir.glob('*.txt')):
            deps |= _parse_requirements_txt(req_file)
    return deps


def _parse_setup_py(setup_path: Path) -> set[str]:
    """Parse install_requires from setup.py (simple AST-free approach)."""
    deps: set[str] = set()
    try:
        with open(setup_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return deps

    # Look for install_requires = [...] or install_requires=[...]
    match = re.search(
        r'install_requires\s*=\s*\[(.*?)\]',
        content,
        re.DOTALL,
    )
    if not match:
        return deps

    block = match.group(1)
    # Extract quoted strings
    strings = re.findall(r"""['"]([^'"]+)['"]""", block)
    for s in strings:
        name = _parse_pep508_dep(s)
        if name:
            deps.add(name)

    return deps


def _extract_setup_py_name(setup_path: Path) -> Optional[str]:
    """Extract the project name from setup.py.

    Looks for patterns like:
      NAME = 'celery'
      name = 'myproject'
    """
    try:
        with open(setup_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None

    # Match NAME = 'value' or name = 'value' at the top level
    match = re.search(r'^\s*(?:NAME|name)\s*=\s*[\'"]([^\'"]+)[\'"]', content, re.MULTILINE)
    if match:
        return match.group(1).lower().replace('-', '_')
    return None


def _parse_uv_lock(lock_path: Path) -> set[str]:
    """Parse all package names from a uv.lock file."""
    deps: set[str] = set()
    try:
        with open(lock_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return deps

    # Extract all [[package]] name = "..." entries
    for match in re.finditer(r'\[\[package\]\]\s*\nname\s*=\s*"([^"]+)"', content):
        pkg_name = match.group(1)
        name = _package_to_import_name(pkg_name)
        if name:
            deps.add(name)

    return deps


class DependencyResolver:
    """Resolve declared Python dependencies from project manifest files.

    Args:
        repo_root: Path to the repository root.
    """

    def __init__(self, repo_root: Path | str) -> None:
        self.repo_root = Path(repo_root).resolve()

    def resolve(self) -> set[str]:
        """Resolve all declared Python dependencies.

        Scans for manifest files in priority order:
        1. pyproject.toml
        2. uv.lock
        3. requirements*.txt (top-level)
        4. requirements/ subdirectory
        5. setup.py

        Returns:
            Set of importable module names (e.g., 'pydantic', 'typing_extensions').
        """
        all_deps: set[str] = set()

        # 1. pyproject.toml (most common modern format)
        pyproject = self.repo_root / 'pyproject.toml'
        if pyproject.exists():
            all_deps |= _parse_pyproject_toml(pyproject)

        # 2. uv.lock (if present, adds transitive deps)
        uv_lock = self.repo_root / 'uv.lock'
        if uv_lock.exists():
            all_deps |= _parse_uv_lock(uv_lock)

        # 3. requirements*.txt files (top-level)
        for req_file in sorted(self.repo_root.glob('requirements*.txt')):
            all_deps |= _parse_requirements_txt(req_file)

        # 4. requirements/ subdirectory (celery-style)
        all_deps |= _parse_requirements_dir(self.repo_root)

        # 5. setup.py
        setup_py = self.repo_root / 'setup.py'
        if setup_py.exists():
            all_deps |= _parse_setup_py(setup_py)

        return all_deps

    def get_project_name(self) -> Optional[str]:
        """Extract the project's own package name.

        Checks pyproject.toml ([project] or [tool.poetry]), then
        falls back to setup.py.

        Returns:
            The project name (e.g., 'fastapi', 'celery', 'rich') or None.
        """
        pyproject = self.repo_root / 'pyproject.toml'
        if pyproject.exists():
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib
                except ImportError:
                    tomllib = None
            else:
                tomllib = tomllib

            if tomllib:
                try:
                    with open(pyproject, 'rb') as f:
                        data = tomllib.load(f)
                    # PEP 621 [project] section
                    project = data.get('project', {})
                    name = project.get('name', '')
                    if name:
                        return name.lower().replace('-', '_')
                    # Poetry [tool.poetry] section
                    poetry = data.get('tool', {}).get('poetry', {})
                    name = poetry.get('name', '')
                    if name:
                        return name.lower().replace('-', '_')
                except Exception:
                    pass

        # 2. setup.py NAME variable
        setup_py = self.repo_root / 'setup.py'
        if setup_py.exists():
            name = _extract_setup_py_name(setup_py)
            if name:
                return name

        return None
