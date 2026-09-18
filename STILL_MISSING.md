# Unslop — Remaining Work

## Current state

The false-positive reduction work is now in commit `2fc9fc1` (pushed to
`origin/main`). The repository currently has **278 passing tests** and a
codebase scan of **11/100** with **198 findings**.

The old DJaay estimates and several examples are no longer actionable. The
naming detector already ignores the cited `proposed_tpe1`, `format_rgb32`,
`user32`, `z103`, and `PySide6` cases. The current backlog should focus on
report quality and evidence, not adding larger allowlists.

## Recently addressed

- Generic naming already filters descriptive compounds, versions, imports,
  and common non-placeholder identifiers.
- Cross-file coherence recognizes common Python packages, test directories,
  and lower-confidence scans without dependency manifests.
- Dead-code detection distinguishes classes from functions, skips conventional
  entry points and framework handlers, and handles multiline returns.
- Dependency-bloat detection skips `TYPE_CHECKING` and known side-effect
  imports.
- Pattern inconsistency requires at least three indexed files.
- Single-file analysis applies the same test-file filtering as codebase scans.

## Remaining work, ordered by value

### 1. Deduplicate unused-import findings — high priority, low effort

`dead_code` and `dependency_bloat` both report unused imports. The current scan
still contains overlapping findings in `cli.py`, `report.py`, `analyzer.py`,
and `github.py`, inflating both the report and the score.

Choose one owner for unused-import reporting, or deduplicate identical issues
in the analyzer while preserving the separate detector APIs. Keep dead-code
responsible for unreachable code and unused functions; keep dependency-bloat
responsible for imports and duplicate-purpose dependencies.

### 2. Do not treat fixture strings as source comments — high priority, medium effort

The current scan reports TODO artifacts from test fixtures and detector test
data, including strings containing `# TODO` or `// FIXME`. Generic naming also
reports intentionally bad names in `tests/test_naming.py` and
`tests/conftest.py`.

Improve source classification before detection:

- Ignore TODO markers inside string literals; keep real comments reportable.
- Apply the existing test-file policy consistently to generic naming, or make
  the policy explicit if test naming is intentionally in scope.
- Keep `test_quality` enabled for tests, since it has a distinct purpose.

### 3. Make pattern evidence file-aware and deduplicated — medium priority

The three-file threshold is useful, but the pattern index still includes the
file being analyzed and can report the same relationship more than once.
Current examples include repeated `time`/`datetime` findings in
`fix_pipeline.py` and helpers matching themselves in the index.

Exclude the candidate file from comparison where possible, require evidence
from distinct files, and emit one issue per module pair or helper relationship.

### 4. Improve volume analysis without suppressing real problems — medium priority

The current scan reports 37 volume findings, including long detector/tooling
functions and intentionally orchestration-heavy files. The detector uses line
counts and a single threshold; it does not distinguish tests, generated code,
migrations, configuration-heavy modules, or comments/blank lines.

Use AST function boundaries for Python, count meaningful lines, and add narrow
file-type/context adjustments. Keep large production functions reportable and
avoid a blanket “skip large files” rule.

### 5. Add cross-file usage evidence to dead-code detection — lower priority

Dead-code detection still only proves local usage. Public functions imported by
another module can be reported as unused unless they happen to be entry points.
Use the existing module index to resolve straightforward local imports before
reporting a function as dead. Dynamic imports and plugin registrations should
lower confidence, not be silently treated as dead.

### 6. Review security findings manually — not an auto-fix target

The current scan reports 41 security findings. Several are Bandit-style
warnings around deliberate subprocess usage, while the SQL-injection findings
in the example service are intentional teaching fixtures. Improve message
context and confidence if useful, but do not broadly suppress or auto-fix them.

## Explicitly not planned yet

- Large ecosystem allowlists for naming or imports.
- Automatic refactoring of long functions/files.
- Automatic fixes for cross-file, architectural, or security findings.
- Adding a parser dependency solely to improve heuristics; the current
  standard-library implementation is sufficient for the remaining work.
