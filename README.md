# UNSLOP — Polish AI-Generated Code to Human Quality

> "AI doesn't write bad code — it writes plausible code. The lines compile, the linter passes, the variable names look reasonable, and on a fast PR review it slides through."

## The Problem

AI-generated code has a distinct signature: it's **locally perfect and globally incoherent**. Humans are inconsistent in small ways but consistent in approach. AI is the exact opposite — eerily uniform line by line, wildly inconsistent in architecture.

## What It Does

Unslop detects and auto-fixes AI-generated code patterns ("slop") in Python and TypeScript projects.

- **12 tell detectors** — Identifies AI-generated code patterns
- **7 auto-fixes** — Safely removes issues with test-gated safety
- **Slop score** — 0-100 metric (lower is better)
- **GitHub integration** — Create PRs with fixes via `gh` CLI

## Quick Start

```bash
# Install
pip install unslop

# Scan a single file
unslop path/to/file.py

# Scan entire codebase
unslop --codebase /path/to/repo

# Auto-fix (safe Tier 1 & 2 tells)
unslop fix /path/to/repo

# Auto-fix with tests
unslop fix /path/to/repo --run-tests

# Create a GitHub PR with fixes
unslop fix /path/to/repo --create-pr
```

## CLI Reference

### `unslop scan` (default)

```bash
unslop /path/to/file.py              # Scan single file
unslop --codebase /path/to/repo       # Scan entire codebase
unslop --max-files 500 /path/to/repo  # Limit files scanned
unslop --verbose /path/to/file.py     # Show detailed issues
unslop --no-markdown /path/to/file.py # Skip markdown output
unslop --no-json /path/to/file.py     # Skip JSON output
unslop --report custom.md /path/to/file.py  # Custom output path
```

### `unslop fix`

```bash
unslop fix /path/to/repo                          # Apply safe fixes
unslop fix /path/to/repo --dry-run                # Preview changes
unslop fix /path/to/repo --run-tests              # Run tests after fixes
unslop fix /path/to/repo --threshold 40           # Target score
unslop fix /path/to/repo --min-confidence 80      # Min confidence %
unslop fix /path/to/repo --max-iterations 10      # Max loop iterations
unslop fix /path/to/repo --test-cmd "pytest"      # Custom test command
unslop fix /path/to/repo --severity high,medium   # Filter by severity
unslop fix /path/to/repo --create-pr              # Create GitHub PR
unslop fix /path/to/repo --create-pr --pr-title "Fix AI tells"
unslop fix /path/to/repo --create-pr --pr-base develop
unslop fix /path/to/repo --no-markdown --no-json  # Skip report files
unslop fix /path/to/repo --report unslopped.md --json-report unslopped.json
```

## Slop Score

| Score | Verdict |
|-------|---------|
| 0-20 | Clean |
| 21-40 | Mostly clean |
| 41-60 | Mixed |
| 61-80 | AI-looking |
| 81-100 | Slop |

## Safety Tiers

| Tier | Tells | Test Gate | Auto-Applied |
|------|-------|-----------|--------------|
| 1 | verbose_comments, todo_artifacts, debug_artifacts | No | Always |
| 2 | empty_error_handling, dead_code, dependency_bloat | Yes | Test-gated |
| 3 | generic_naming, pattern_inconsistency, security | N/A | Never (suggest only) |

## Tell Detectors

| # | Tell | Auto-Fix | Research Source |
|---|------|----------|-----------------|
| 1 | Empty error handling | ✅ `pass` → `raise` | McKelvey Tell #8 |
| 2 | Dead code | ✅ Remove unused imports | Git AutoReview #8 |
| 3 | Dependency bloat | ✅ Remove unused imports | McKelvey Tell #3 |
| 4 | Generic naming | ✅ Strip `new_`/`my_`/`helper_` | McKelvey Tell #4 |
| 5 | Pattern inconsistency | ⚠️ Suggest only | McKelvey Tell #2 |
| 6 | Verbose comments | ✅ Remove restatements | McKelvey Tell #1 |
| 7 | TODO artifacts | ✅ Remove TODO/FIXME | McKelvey Tell #6 |
| 8 | Debug artifacts | ✅ Remove console.log/print | Git AutoReview #10 |
| 9 | Test quality | ⚠️ Suggest only | Cai & Tsantalis 2026 |
| 10 | Security scanner | ❌ Detect only | Veracode 2025 |
| 11 | Volume analysis | ❌ Detect only | McConnell |
| 12 | Cross-file coherence | ❌ Detect only | McKelvey Tell #2 |

## GitHub Integration

```bash
# Check GitHub availability
python -c "from unslop import check_github; print(check_github('/path/to/repo'))"

# Create PR with fixes
unslop fix /path/to/repo --create-pr

# Custom title and base branch
unslop fix /path/to/repo --create-pr \
  --pr-title "Fix AI-generated code patterns" \
  --pr-base develop
```

The `--create-pr` flag:
1. Runs the fix pipeline
2. Creates a new branch (`unslop-fix-YYYYMMDD-HHMMSS`)
3. Commits all changes
4. Pushes to remote
5. Creates PR via `gh pr create`
6. Returns PR URL

## API Usage

```python
from unslop import UnslopAnalyzer, FixPipeline

# Scan
analyzer = UnslopAnalyzer(repo_root="/path/to/repo")
report = analyzer.analyze_file("/path/to/file.py")
print(report.to_markdown())

# Fix
pipeline = FixPipeline(repo_root="/path/to/repo")
result = pipeline.run(threshold=40, run_tests=True)
print(f"Score: {result.original_score} → {result.final_score}")
result.write_report("unslopped.md", "unslopped.json")
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Failure (tests failed, max iterations, no fixes) |
| 2 | Error (dirty tree, not a git repo, auth failure) |

## Languages

- **Python** — Full support (Bandit integration for security)
- **TypeScript/JavaScript** — Full support

## Slop Score Methodology

The slop score uses **density-based scoring** (issues per 1000 LOC) rather than absolute counts, following industry standards for defect density measurement:

### Industry Standards

| Source | Standard | Reference |
|--------|----------|-----------|
| **McConnell (Code Complete)** | 15-50 defects per KLOC industry average; 0-25/KLOC for small projects | [Gauging Software Readiness](https://stevemcconnell.com/articles/gauging-software-readiness-with-defect-tracking/) |
| **SonarQube** | 0-5/1K ideal, 6-10 needs improvement, 10+ needs action | [Code Smells Discussion](https://community.sonarsource.com/t/what-is-the-acceptable-rate-of-code-smells/131227) |
| **CISQ/ISO 5055** | Standardized defect density per KLOC across security, reliability, performance, maintainability | [CISQ Standards](https://www.it-cisq.org/standards/code-quality-standards/) |
| **Cai & Tsantalis (2026)** | Empirical LLM code smell density — smells measured per module, normalized by size | [AI-Generated Smells](https://arxiv.org/html/2605.02741) |

### Scoring Formula

Each tell category has a weight and density thresholds (moderate/critical) calibrated from the research above:

```
score_per_tell = min((density - moderate) / (critical - moderate), 1.0) × weight
total_score = min(sum(score_per_tell), 100.0)
```

**Density thresholds** (issues per 1000 LOC):
- **Moderate** (below this = 0 score): 0.5-5.0/KLOC — SonarQube ideal range
- **Critical** (above this = full weight): 10-50/KLOC — McConnell industry average upper bound

**Weights** (reflect impact severity):
- Security vulnerabilities: 20 (highest)
- Empty error handling, dead code, dependency bloat, generic naming, pattern inconsistency: 15
- Verbose comments, TODO artifacts, test quality: 10
- Debug artifacts, volume anomaly, cross-file coherence: 5-10

### False Positive Filtering

- **Test files**: Security and pattern inconsistency tells are skipped for `test_*.py`, `*_test.py`, `conftest.py`, `tests/`, `test/`, `fixtures/` directories (Bandit B101 assert false positives)
- **Common names**: Generic naming tell skips `self`, `data`, `result`, `value`, `item`, `key`, `config`, etc. (standard Python conventions)
- **Dependency bloat**: Skips compatibility shims (StringIO for Python 2/3), urllib3 imports, and standard re-export patterns

## Research

See `RESEARCH.md` for the full research synthesis from 12 academic and industry sources.

Key sources:
- Justin McKelvey — "9 Tells of AI-Generated Code"
- Git AutoReview — "12-item Checklist for AI-Generated Code"
- Cai & Tsantalis (2026) — "AI-Generated Smells"
- Veracode 2025 — "45% of AI code has OWASP vulnerabilities"
- USENIX Security 2025 — "5.2% package name hallucination rate"
- McConnell (Code Complete) — Defect density benchmarks
- SonarQube — Code smell thresholds
- CISQ/ISO 5055 — Standardized quality measures

## Integrations

| Integration | Usage |
|-------------|-------|
| Pi skill | `unslop this file` in Pi |
| Claude Code | Follow `CLAUDE.md` |
| GitHub | `unslop fix --create-pr` |
| CLI | `unslop scan` / `unslop fix` |

## Development

```bash
pip install -e .
pytest tests/ -v
```
