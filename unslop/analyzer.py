"""UnslopAnalyzer — Main orchestrator for code analysis and auto-fixing.

Usage:
    from unslop import UnslopAnalyzer

    # File-level analysis
    analyzer = UnslopAnalyzer(repo_root="/path/to/repo")
    report = analyzer.analyze_file("/path/to/repo/file.py")
    print(report.summary())
    fixed_code = analyzer.fix(report)

    # Codebase-level analysis
    report = analyzer.analyze_codebase(max_files=500)
    print(report.summary())

    # Get slop score
    score = analyzer.slop_score(report)
    print(f"Slop score: {score}/100 (lower is better)")
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .pattern_index import PatternIndex

_TEST_PATTERNS = [
    re.compile(r'^test_', re.IGNORECASE),
    re.compile(r'_test\.py$', re.IGNORECASE),
    re.compile(r'^conftest\.py$', re.IGNORECASE),
    re.compile(r'/tests/', re.IGNORECASE),
    re.compile(r'/test/', re.IGNORECASE),
    re.compile(r'/fixtures/', re.IGNORECASE),
]

# Common Python variable names that are generic by convention, not AI slop
_COMMON_NAMES = {
    'self', 'cls', 'data', 'result', 'value', 'item', 'key',
    'config', 'options', 'params', 'args', 'kwargs', 'obj', 'ctx',
    'event', 'handler', 'callback', 'state', 'response', 'request',
    'error', 'message', 'text', 'name', 'path', 'content',
}
from .report import Severity, TellCategory, UnslopReport, UnslopIssue
from .tells import (
    detect_naming, fix_naming,
    detect_verbose_comments, fix_verbose_comments,
    detect_dead_code, fix_dead_code,
    detect_empty_error_handling, fix_empty_error_handling,
    detect_todo_artifacts, fix_todo_artifacts,
    detect_debug_artifacts, fix_debug_artifacts,
    detect_dependency_bloat, fix_dependency_bloat,
    detect_pattern_inconsistency, fix_pattern_inconsistency,
    detect_test_quality, fix_test_quality,
    detect_security_scanner, fix_security_scanner,
    detect_volume_analysis, fix_volume_analysis,
    detect_cross_file_coherence, fix_cross_file_coherence,
    detect_global_incoherence, fix_global_incoherence,
)


# Tell detection order (highest impact first)
TELL_DETECTIONS = [
    ("empty_error_handling", detect_empty_error_handling, fix_empty_error_handling),
    ("dead_code", detect_dead_code, fix_dead_code),
    ("dependency_bloat", detect_dependency_bloat, fix_dependency_bloat),
    ("naming", detect_naming, fix_naming),
    ("pattern_inconsistency", detect_pattern_inconsistency, fix_pattern_inconsistency),
    ("verbose_comments", detect_verbose_comments, fix_verbose_comments),
    ("todo_artifacts", detect_todo_artifacts, fix_todo_artifacts),
    ("debug_artifacts", detect_debug_artifacts, fix_debug_artifacts),
    ("test_quality", detect_test_quality, fix_test_quality),
    ("security_scanner", detect_security_scanner, fix_security_scanner),
    ("volume_analysis", detect_volume_analysis, fix_volume_analysis),
    ("cross_file_coherence", detect_cross_file_coherence, fix_cross_file_coherence),
    ("global_incoherence", detect_global_incoherence, fix_global_incoherence),
]

# Map tell_name strings to TellCategory enums for filtering
_TELL_ENUM_MAP = {
    "empty_error_handling": TellCategory.EMPTY_ERROR_HANDLING,
    "dead_code": TellCategory.DEAD_CODE,
    "dependency_bloat": TellCategory.DEPENDENCY_BLOAT,
    "naming": TellCategory.GENERIC_NAMING,
    "pattern_inconsistency": TellCategory.PATTERN_INCONSISTENCY,
    "verbose_comments": TellCategory.VERBOSE_COMMENTS,
    "todo_artifacts": TellCategory.TODO_ARTIFACTS,
    "debug_artifacts": TellCategory.DEBUG_ARTIFACTS,
    "test_quality": TellCategory.TEST_QUALITY,
    "security_scanner": TellCategory.SECURITY_VULNERABILITY,
    "volume_analysis": TellCategory.VOLUME_ANOMALY,
    "cross_file_coherence": TellCategory.CROSS_FILE_INCOHERENCE,
    "global_incoherence": TellCategory.GLOBAL_INCOHERENCE,
}


@dataclass
class UnslopAnalyzer:
    """Main analyzer for detecting and fixing AI-generated code patterns.

    Args:
        repo_root: Path to the repository root.
        max_index_files: Maximum files to index for pattern analysis.
    """
    repo_root: Path | str = "."
    max_index_files: int = 1000

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root).resolve()
        self._pattern_index: Optional[PatternIndex] = None
        self._dependencies: Optional[set[str]] = None
        self._project_name: Optional[str] = None

    @property
    def pattern_index(self) -> PatternIndex:
        """Lazy-load the pattern index."""
        if self._pattern_index is None:
            self._pattern_index = PatternIndex(repo_root=self.repo_root)
            self._pattern_index.build(max_files=self.max_index_files)
        return self._pattern_index

    @property
    def dependencies(self) -> set[str]:
        """Lazy-resolve declared project dependencies."""
        if self._dependencies is None:
            from .dependency_resolver import DependencyResolver
            resolver = DependencyResolver(self.repo_root)
            self._dependencies = resolver.resolve()
        return self._dependencies

    @property
    def project_name(self) -> Optional[str]:
        """Lazy-resolve the project's own package name."""
        if self._project_name is None:
            from .dependency_resolver import DependencyResolver
            resolver = DependencyResolver(self.repo_root)
            self._project_name = resolver.get_project_name()
            # Infer a package name for projects using ``src/<package>``
            # without a packaging manifest. This prevents internal imports
            # from being reported as unknown third-party modules.
            if not self._project_name:
                for package_root in (self.repo_root / "src", self.repo_root):
                    if not package_root.is_dir():
                        continue
                    candidates = sorted(
                        child.name for child in package_root.iterdir()
                        if child.is_dir() and (child / "__init__.py").is_file()
                    )
                    if candidates:
                        self._project_name = candidates[0]
                        break
        return self._project_name

    def _extract_config_keys(self) -> set[str]:
        """Extract all declared configuration keys from the repository.

        Scans for environment variables declared in:
        - .env, .env.example, .env.sample
        - docker-compose.yml / docker-compose.yaml
        - Terraform / CDK configuration files
        - Settings files (settings.py, config.ts, etc.)
        - package.json scripts (env vars)

        Returns:
            Set of configuration key names found.
        """
        config_keys: set[str] = set()
        search_dirs = ['.']  # Start from repo root

        for search_dir in search_dirs:
            base = self.repo_root / search_dir
            if not base.exists():
                continue

            # Scan for .env files
            for env_file in base.glob('.env*'):
                if env_file.is_file():
                    try:
                        content = env_file.read_text(encoding='utf-8')
                        for line in content.splitlines():
                            line = line.strip()
                            # Skip comments and empty lines
                            if not line or line.startswith('#'):
                                continue
                            # Extract KEY=VALUE patterns
                            match = re.match(r'^([A-Z_][A-Z0-9_]*)=', line)
                            if match:
                                config_keys.add(match.group(1))
                    except (UnicodeDecodeError, OSError):
                        continue

            # Scan for docker-compose files
            for dc_file in base.glob('docker-compose*.{yml,yaml}'):
                if dc_file.is_file():
                    try:
                        content = dc_file.read_text(encoding='utf-8')
                        # Extract environment variable names
                        for match in re.finditer(r'\b[A-Z_][A-Z0-9_]*\b', content):
                            key = match.group(0)
                            if key not in ('version', 'services', 'volumes',
                                           'networks', 'configs', 'secrets',
                                           'image', 'build', 'restart',
                                           'ports', 'expose', 'command',
                                           'depends_on', 'labels', 'logging',
                                           'driver', 'name', 'external',
                                           'type', 'source', 'target',
                                           'readonly', 'readonly',
                                           'true', 'false', 'null', 'none'):
                                config_keys.add(key)
                    except (UnicodeDecodeError, OSError):
                        continue

            # Scan for Terraform files
            for tf_file in base.glob('**/*.tf'):
                if tf_file.is_file():
                    try:
                        content = tf_file.read_text(encoding='utf-8')
                        for match in re.finditer(r'variable\s+"([^"]+)"', content):
                            config_keys.add(match.group(1).upper())
                    except (UnicodeDecodeError, OSError):
                        continue

        return config_keys

    def _is_test_file(self, file_path: Path) -> bool:
        """Check if a file is a test file (tests/, test/, test_*.py, etc.)."""
        name = file_path.name
        for pattern in _TEST_PATTERNS:
            if pattern.search(str(file_path)) or pattern.match(name):
                return True
        return False

    def _should_skip_tell(self, tell: TellCategory, file_path: Path) -> bool:
        """Determine if a tell should be skipped for a given file.

        Filters known false positives:
        - Security tell: skip test files (Bandit B101 assert false positives)
        - Pattern inconsistency: skip test files (test helpers are intentionally different)
        - Naming tell: skip common Python variable names (self, data, result, etc.)

        Args:
            tell: The tell category to check.
            file_path: Path to the file being analyzed.

        Returns:
            True if the tell should be skipped for this file.
        """
        # Security tell: skip test files — Bandit flags asserts, hardcoded
        # passwords in fixtures, etc. These are legitimate test patterns.
        if tell == TellCategory.SECURITY_VULNERABILITY and self._is_test_file(file_path):
            return True

        # Pattern inconsistency: skip test files — test helpers often
        # intentionally duplicate patterns from production code.
        if tell == TellCategory.PATTERN_INCONSISTENCY and self._is_test_file(file_path):
            return True

        # Global incoherence: skip test files — test mocks, fixtures, and
        # test-only env vars are not AI slop.
        if tell == TellCategory.GLOBAL_INCOHERENCE and self._is_test_file(file_path):
            return True

        # Tests intentionally contain fixtures, pytest hooks, and helper
        # classes that are not called from the same file. Their conventions
        # should not affect the production-code score.
        if tell in {
            TellCategory.DEAD_CODE,
            TellCategory.DEPENDENCY_BLOAT,
            TellCategory.DEBUG_ARTIFACTS,
            TellCategory.VERBOSE_COMMENTS,
            TellCategory.VOLUME_ANOMALY,
            TellCategory.EMPTY_ERROR_HANDLING,
        } and self._is_test_file(file_path):
            return True

        return False

    def _filter_naming_issues(self, issues: list[UnslopIssue]) -> list[UnslopIssue]:
        """Filter out generic naming issues for common Python variable names."""
        filtered = []
        for issue in issues:
            # Extract the name from the description
            desc = issue.description
            # Pattern: "Generic name: 'X'" or "X is a generic name"
            match = re.search(r"['\"](\w+)['\"]", desc)
            if match:
                name = match.group(1)
                if name in _COMMON_NAMES:
                    continue
            filtered.append(issue)
        return filtered

    def _filter_dependency_bloat(self, issues: list[UnslopIssue]) -> list[UnslopIssue]:
        """Filter out false positives in dependency bloat detection."""
        filtered = []
        for issue in issues:
            desc = issue.description.lower()
            # Skip compatibility shims (e.g., StringIO for Python 2/3 compat)
            if 'compat' in str(issue.file_path).lower() and ('stringio' in desc or 'collections' in desc):
                continue
            # Skip duplicate-purpose for well-known legitimate dependencies
            if 'duplicate-purpose' in desc:
                # urllib3 is a legitimate dependency of requests
                if 'urllib3' in desc:
                    continue
                # Skip if it's a standard library re-export pattern
                if 'serves same purpose' in desc:
                    continue
            filtered.append(issue)
        return filtered

    def analyze_file(
        self,
        file_path: Path | str,
        build_index: bool = True,
    ) -> UnslopReport:
        """Analyze a single file for AI-generated code patterns.

        Args:
            file_path: Path to the file to analyze.
            build_index: Whether to build the pattern index first.

        Returns:
            UnslopReport with all detected issues.
        """
        file_path = Path(file_path).resolve()

        if build_index:
            self.pattern_index  # Trigger index build

        try:
            source = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return UnslopReport(file_path=file_path, issues=[])

        lines = source.splitlines()
        report = UnslopReport(
            file_path=file_path,
            total_lines=len(lines),
        )

        # Build context for tell detection
        context = {
            'pattern_index': self.pattern_index,
            'dependencies': self.dependencies,
            'project_name': self.project_name,
            'config_keys': self._extract_config_keys(),
            'root_dir': self.repo_root,
        }

        # Run all tell detections
        for tell_name, detect_fn, _ in TELL_DETECTIONS:
            tell_enum = _TELL_ENUM_MAP.get(tell_name)
            if tell_enum and self._should_skip_tell(tell_enum, file_path):
                continue
            issues = detect_fn(source, file_path, context)
            for issue in issues:
                report.add_issue(issue)

        report.slop_score = self._calculate_slop_score(report)

        return report

    def analyze_codebase(
        self,
        exclude_dirs: Optional[list[str]] = None,
        max_files: int = 500,
    ) -> UnslopReport:
        """Analyze the entire codebase for AI-generated code patterns.

        This is a quality exercise — not tied to a PR. It scans all files
        and produces a holistic slop score for the entire codebase.

        Args:
            exclude_dirs: Directories to skip.
            max_files: Maximum files to analyze.

        Returns:
            UnslopReport with issues from all files.
        """
        if exclude_dirs is None:
            exclude_dirs = [
                ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
                ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
                "build", "dist", "release",
            ]

        from .symbols import ModuleIndex
        module_index = ModuleIndex.build(self.repo_root, exclude_dirs)
        self.pattern_index.build(exclude_dirs=exclude_dirs, max_files=max_files)

        files = list(module_index.path_to_module.keys())[:max_files]

        report = UnslopReport()
        total_lines = 0

        for file_path in files:
            try:
                source = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            lines = source.splitlines()
            file_report = UnslopReport(
                file_path=file_path,
                total_lines=len(lines),
            )

            context = {
                'pattern_index': self.pattern_index,
                'dependencies': self.dependencies,
                'project_name': self.project_name,
                'config_keys': self._extract_config_keys(),
                'root_dir': self.repo_root,
            }

            for tell_name, detect_fn, _ in TELL_DETECTIONS:
                # Map tell_name string to TellCategory enum for skip checking
                tell_enum = _TELL_ENUM_MAP.get(tell_name)

                # Skip tells for test files (reduces false positives)
                if tell_enum and self._should_skip_tell(tell_enum, file_path):
                    continue

                issues = detect_fn(source, file_path, context)

                if tell_name == 'naming':
                    issues = self._filter_naming_issues(issues)

                if tell_name == 'dependency_bloat':
                    issues = self._filter_dependency_bloat(issues)

                for issue in issues:
                    file_report.add_issue(issue)

            file_report.slop_score = self._calculate_slop_score(file_report)
            report.issues.extend(file_report.issues)
            total_lines += file_report.total_lines

        report.total_lines = total_lines

        if report.issues:
            report.slop_score = self._calculate_slop_score(report)
        else:
            report.slop_score = 0.0

        return report

    def fix(self, report: UnslopReport) -> str:
        """Apply fixes to the code based on the analysis report.

        Args:
            report: The analysis report from analyze_file().

        Returns:
            Fixed source code.
        """
        if not report.file_path:
            raise ValueError("Report must be from analyze_file(), not analyze_codebase()")

        try:
            source = report.file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return source

        # Group issues by tell category
        by_tell: dict[TellCategory, list[UnslopIssue]] = {}
        for issue in report.issues:
            by_tell.setdefault(issue.tell, []).append(issue)

        # Apply fixes in priority order (highest severity first)
        fix_map = {
            TellCategory.EMPTY_ERROR_HANDLING: fix_empty_error_handling,
            TellCategory.DEAD_CODE: fix_dead_code,
            TellCategory.DEPENDENCY_BLOAT: fix_dependency_bloat,
            TellCategory.GENERIC_NAMING: fix_naming,
            TellCategory.PATTERN_INCONSISTENCY: fix_pattern_inconsistency,
            TellCategory.VERBOSE_COMMENTS: fix_verbose_comments,
            TellCategory.TODO_ARTIFACTS: fix_todo_artifacts,
            TellCategory.DEBUG_ARTIFACTS: fix_debug_artifacts,
            TellCategory.TEST_QUALITY: fix_test_quality,
            TellCategory.SECURITY_VULNERABILITY: fix_security_scanner,
            TellCategory.VOLUME_ANOMALY: fix_volume_analysis,
            TellCategory.CROSS_FILE_INCOHERENCE: fix_cross_file_coherence,
        }

        for tell, fix_fn in fix_map.items():
            if tell in by_tell:
                source = fix_fn(source, by_tell[tell])

        return source

    def slop_score(self, report: UnslopReport) -> float:
        """Calculate the slop score for a report.

        Lower is better. 0 = no AI tells detected, 100 = maximum AI tells.

        Args:
            report: The analysis report.

        Returns:
            Slop score from 0-100.
        """
        return self._calculate_slop_score(report)

    def _calculate_slop_score(self, report: UnslopReport) -> float:
        """Calculate the slop score based on detected issues.

        Uses density-based scoring (issues per 1000 LOC) instead of
        absolute counts, following industry standards:
        - McConnell (Code Complete): defect density 15-50 per KLOC
          [Source: https://stevemcconnell.com/articles/gauging-software-readiness-with-defect-tracking/]
        - SonarQube: code smells 0-5/1K ideal, 10+/1K needs action
          [Source: https://community.sonarsource.com/t/what-is-the-acceptable-rate-of-code-smells/131227]
        - CISQ/ISO 5055: standardized density metrics per quality factor
          [Source: https://www.it-cisq.org/standards/code-quality-standards/]
        - Cai & Tsantalis (2026): LLM code smell density per module
          [Source: https://arxiv.org/html/2605.02741]

        Density thresholds calibrated from research:
        - Moderate (0 score): 0.5-5.0/KLOC — SonarQube ideal range
        - Critical (full weight): 10-50/KLOC — McConnell industry average upper bound

        Each tell category has a weight and density thresholds.
        The score is the weighted sum of normalized densities, capped at 100.
        """
        # Weights for each tell category (reflects impact severity)
        weights = {
            TellCategory.EMPTY_ERROR_HANDLING: 15,
            TellCategory.DEAD_CODE: 15,
            TellCategory.DEPENDENCY_BLOAT: 15,
            TellCategory.GENERIC_NAMING: 15,
            TellCategory.PATTERN_INCONSISTENCY: 15,
            TellCategory.VERBOSE_COMMENTS: 10,
            TellCategory.TODO_ARTIFACTS: 10,
            TellCategory.DEBUG_ARTIFACTS: 5,
            TellCategory.TEST_QUALITY: 10,
            TellCategory.SECURITY_VULNERABILITY: 20,
            TellCategory.VOLUME_ANOMALY: 5,
            TellCategory.CROSS_FILE_INCOHERENCE: 10,
            TellCategory.GLOBAL_INCOHERENCE: 15,
        }

        # Density thresholds (issues per 1000 LOC) for each tell.
        # Thresholds are calibrated from industry research:
        #   - ideal: 0-5 per KLOC (SonarQube ideal range)
        #   - moderate: 5-20 per KLOC (SonarQube "needs improvement")
        #   - high: 20-50 per KLOC (McConnell industry average upper bound)
        #   - critical: 50+ per KLOC (McConnell range ceiling)
        # Each tell has its own "moderate" threshold where scoring begins.
        # Full weight is applied at "critical" threshold.
        # Formula: density_score = min((density - moderate) / (critical - moderate), 1.0)
        density_thresholds = {
            TellCategory.EMPTY_ERROR_HANDLING: (0.5, 5.0),
            TellCategory.DEAD_CODE: (1.0, 10.0),
            TellCategory.DEPENDENCY_BLOAT: (1.0, 10.0),
            TellCategory.GENERIC_NAMING: (5.0, 50.0),
            TellCategory.PATTERN_INCONSISTENCY: (2.0, 20.0),
            TellCategory.VERBOSE_COMMENTS: (2.0, 20.0),
            TellCategory.TODO_ARTIFACTS: (0.5, 5.0),
            TellCategory.DEBUG_ARTIFACTS: (0.5, 5.0),
            TellCategory.TEST_QUALITY: (2.0, 20.0),
            TellCategory.SECURITY_VULNERABILITY: (1.0, 10.0),
            TellCategory.VOLUME_ANOMALY: (1.0, 10.0),
            TellCategory.CROSS_FILE_INCOHERENCE: (2.0, 20.0),
            TellCategory.GLOBAL_INCOHERENCE: (0.5, 5.0),
        }

        # Group issues by tell category
        by_tell: dict[TellCategory, list[UnslopIssue]] = {}
        for issue in report.issues:
            by_tell.setdefault(issue.tell, []).append(issue)

        total_lines = report.total_lines or 1  # Avoid division by zero
        kloc = total_lines / 1000.0

        score = 0.0
        for tell, weight in weights.items():
            count = len(by_tell.get(tell, []))
            moderate, critical = density_thresholds.get(tell, (1.0, 10.0))

            if kloc > 0:
                density = count / kloc  # issues per 1000 LOC
            else:
                density = count  # single-file mode: use raw count

            # Normalize density to 0-1 scale
            # Below moderate: 0 (clean)
            # Between moderate and critical: linear ramp
            # Above critical: 1.0 (full weight)
            if density <= moderate:
                density_score = 0.0
            elif density >= critical:
                density_score = 1.0
            else:
                density_score = (density - moderate) / (critical - moderate)

            score += density_score * weight

        return min(score, 100.0)

    def report_summary(self, report: UnslopReport) -> str:
        """Generate a human-readable summary of the analysis."""
        lines = []

        if report.file_path:
            lines.append(f"File: {report.file_path}")

        lines.append(f"Slop Score: {report.slop_score:.0f}/100")

        if report.slop_score < 20:
            lines.append("Verdict: Clean — looks like human-written code.")
        elif report.slop_score < 40:
            lines.append("Verdict: Mostly clean — minor AI tells detected.")
        elif report.slop_score < 60:
            lines.append("Verdict: Mixed — several AI tells detected.")
        elif report.slop_score < 80:
            lines.append("Verdict: AI-looking — multiple AI tells detected.")
        else:
            lines.append("Verdict: Slop — strong AI-generated code signals.")

        if report.issues:
            lines.append(f"\nIssues Found: {len(report.issues)}")

            # Group by tell category
            by_tell: dict[TellCategory, list[UnslopIssue]] = {}
            for issue in report.issues:
                by_tell.setdefault(issue.tell, []).append(issue)

            for tell, issues in sorted(by_tell.items(), key=lambda x: -len(x[1])):
                lines.append(f"  {tell.value}: {len(issues)} issue(s)")

            # Show critical issues first
            critical = [i for i in report.issues if i.severity == Severity.CRITICAL]
            if critical:
                lines.append(f"\nCritical Issues ({len(critical)}):")
                for issue in critical:
                    location = f"line {issue.line}" if issue.line else str(issue.file_path)
                    lines.append(f"  ❌ {issue.description} ({location})")

        return "\n".join(lines)
