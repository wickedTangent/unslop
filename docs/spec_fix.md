# Unslop Fix — Specification

## Overview

`unslop fix` is an active, test-gated code improvement pipeline that iteratively applies safe fixes to reduce a codebase's slop score. It is the evolution of `unslop scan` (the current read-only analyzer).

**Goal:** Take a project from "AI-looking" (score 60+) to "human-quality" (score < 40) with automated, test-verified changes.

**Safety first:** Every change is reversible, test-gated, and confidence-scored. No changes are applied without passing tests.

## Design Principles

1. **Never leave artifacts behind** — no `.unslopped` files, no temporary files, no broken state
2. **Always reversible** — git diff available, changes revertable
3. **Test-gated** — no fix is applied without passing tests
4. **Confidence-scored** — low-confidence changes are never applied
5. **Agent-readable** — report is a clean, well-structured Markdown file
6. **Iterative** — scan → fix → test → re-scan loop until target score or tests fail

## CLI Interface

```bash
# Dry run — show what would change
unslop fix --repo . --dry-run

# Apply safe fixes, run tests, iterate to target
unslop fix --repo . --threshold 40 --run-tests

# Apply safe fixes, run tests, iterate to target, create PR
unslop fix --repo . --threshold 40 --run-tests --create-pr --branch unslopped

# Custom test command
unslop fix --repo . --threshold 40 --run-tests --test-cmd "pytest tests/"

# Maximum iterations (default: 10)
unslop fix --repo . --threshold 40 --run-tests --max-iterations 15

# Report output path (default: unslopped.md)
unslop fix --repo . --threshold 40 --run-tests --report unslopped.md
```

## Command Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--repo` | `.` | Path to repository root |
| `--threshold` | `40` | Target score to reach (lower is better) |
| `--dry-run` | `false` | Show changes without applying |
| `--run-tests` | `false` | Run test suite after each fix iteration |
| `--test-cmd` | auto-detect | Custom test command (auto-detects pytest, npm test, flutter test, etc.) |
| `--create-pr` | `false` | Create a PR with the cleaned files |
| `--branch` | `unslopped` | Branch name for PR |
| `--max-iterations` | `10` | Maximum scan→fix→test loop iterations |
| `--report` | `unslopped.md` | Path to Markdown report output |
| `--json-report` | `unslopped.json` | Path to structured JSON report (optional, for agents) |
| `--min-confidence` | `80` | Minimum confidence % to apply a fix |
| `--severity` | `low,medium,critical` | Comma-separated list of severity levels to apply |
| `--skip-tells` | (none) | Comma-separated list of tell categories to skip |
| `--include-tells` | (all) | Only apply fixes from these tell categories |

## Iteration Loop

```
START: unslop fix --repo . --run-tests --threshold 40
    │
    ▼
1. Scan repo → get score
    │
    ▼
2. Score < threshold?
    │
Yes ──┘    No ──► DONE: Report generated, PR created if requested
    │
    ▼
3. Apply fixes (confidence > min, in severity list)
    │
    ▼
4. Run tests
    │
    ▼
5. Tests pass?
    │
Yes ──┘    No ──► STOPPED: Tests failed, changes reverted, report saved
    │
    ▼
6. Iteration count < max?
    │
Yes ──┘    No ──► STOPPED: Max iterations reached, report saved
    │
    ▼
Loop to step 1
```

## Fix Categories & Safety

Fixes are divided into safety tiers. Only Tier 1 fixes are applied without test verification. Tier 2+ require tests to pass.

### Tier 1 — Always Safe (no test gate needed)

| Tell | Fix | Why Safe |
|------|-----|----------|
| `verbose_comments` | Remove redundant comments | Comments don't affect behavior |
| `todo_artifacts` | Remove TODO/FIXME markers | Comments don't affect behavior |
| `debug_artifacts` | Remove console.log/print | Removes debug output, doesn't change logic |

### Tier 2 — Test-Gated Safe

| Tell | Fix | Why Requires Tests |
|------|-----|-------------------|
| `empty_error_handling` | Remove `except: pass` blocks | Could expose hidden errors |
| `dead_code` | Remove unreachable code | Could remove dead but intentional code |

### Tier 3 — Never Auto-Apply (suggest only)

| Tell | Reason |
|------|--------|
| `generic_naming` | Renaming could break cross-file references |
| `pattern_inconsistency` | Could break architectural decisions |
| `dependency_bloat` | Removing imports could break imports |
| `security_vulnerability` | Security fixes require human review |
| `test_quality` | Test changes could hide real bugs |
| `volume_anomaly` | Refactoring is too risky |
| `cross_file_coherence` | Cross-file changes are too complex |

## Report Format: `unslopped.md`

```markdown
# Unslop Fix Report

**Repository:** /path/to/repo
**Date:** 2026-01-15 14:30 UTC
**Command:** unslop fix --repo . --threshold 40 --run-tests

## Summary

| Metric | Value |
|--------|-------|
| Original score | 80/100 |
| Final score | 35/100 |
| Changes applied | 12 |
| Iterations | 2 |
| Tests passed | ✅ |
| Time elapsed | 4.2s |

## Changes

### 1. Empty error handling (critical) — `src/user_service.py:117`
- **Action:** Removed empty `except Exception: pass` block
- **Original:**
  ```python
  except Exception:
      pass
  ```
- **Reasoning:** Silently swallowing exceptions is a common AI pattern. The error was being ignored entirely.
- **Confidence:** 95%
- **Safe to revert:** Yes
- **Git diff:**
  ```diff
  -        except Exception:
  -            pass
  ```

### 2. Debug artifact (medium) — `src/user_service.py:53`
- **Action:** Removed debug print statement
- **Original:** `print(f"User data: {user_data}")`
- **Reasoning:** Debug output should not ship to production.
- **Confidence:** 95%
- **Safe to revert:** Yes

### 3. Verbose comments (low) — `src/user_service.py:55`
- **Action:** Removed redundant comment
- **Original:** `# check if the value is a string`
- **Reasoning:** Comment restates what the code already does. Not AI-generated content — just redundant.
- **Confidence:** 90%
- **Safe to revert:** Yes

## Iteration History

### Iteration 1
- **Start score:** 80/100
- **Fixes applied:** 8
- **Score after:** 65/100
- **Tests:** ✅ passed

### Iteration 2
- **Start score:** 65/100
- **Fixes applied:** 4
- **Score after:** 35/100
- **Tests:** ✅ passed

## Changes Not Applied

| File | Line | Tell | Reason |
|------|------|------|--------|
| `src/user_service.py` | 200 | generic_naming | Confidence 70% < threshold 80% |
| `src/user_service.py` | 300 | pattern_inconsistency | Tier 3 — never auto-applied |

## Files Modified

| File | Changes | Score impact |
|------|---------|-------------|
| `src/user_service.py` | 8 | -15 |
| `src/auth_service.py` | 4 | -5 |

## Next Steps

1. Review the changes in the diff above
2. Run `git diff` to see all changes
3. Run tests: `pytest` (or `npm test`, `flutter test`, etc.)
4. If satisfied: commit and push
5. If not: `git reset --hard` to revert all changes
```

## Report Format: `unslopped.json` (Agent-Readable)

```json
{
  "version": "1.0",
  "tool": "unslop",
  "timestamp": "2026-01-15T14:30:00Z",
  "repository": "/path/to/repo",
  "command": "unslop fix --repo . --threshold 40 --run-tests",
  "summary": {
    "original_score": 80,
    "final_score": 35,
    "changes_applied": 12,
    "iterations": 2,
    "tests_passed": true,
    "time_seconds": 4.2
  },
  "iterations": [
    {
      "number": 1,
      "start_score": 80,
      "end_score": 65,
      "fixes_applied": 8,
      "tests_passed": true
    },
    {
      "number": 2,
      "start_score": 65,
      "end_score": 35,
      "fixes_applied": 4,
      "tests_passed": true
    }
  ],
  "changes": [
    {
      "id": 1,
      "file": "src/user_service.py",
      "line": 117,
      "tell": "empty_error_handling",
      "severity": "critical",
      "confidence": 0.95,
      "tier": 2,
      "action": "removed",
      "original": "except Exception:\n    pass",
      "reasoning": "Silently swallowing exceptions is a common AI pattern.",
      "safe_to_revert": true,
      "git_diff": "-        except Exception:\n-            pass"
    },
    {
      "id": 2,
      "file": "src/user_service.py",
      "line": 53,
      "tell": "debug_artifacts",
      "severity": "medium",
      "confidence": 0.95,
      "tier": 1,
      "action": "removed",
      "original": "print(f\"User data: {user_data}\")",
      "reasoning": "Debug output should not ship to production.",
      "safe_to_revert": true,
      "git_diff": "-print(f\"User data: {user_data}\")"
    }
  ],
  "changes_not_applied": [
    {
      "file": "src/user_service.py",
      "line": 200,
      "tell": "generic_naming",
      "reason": "confidence_below_threshold",
      "confidence": 0.70,
      "min_confidence": 0.80
    },
    {
      "file": "src/user_service.py",
      "line": 300,
      "tell": "pattern_inconsistency",
      "reason": "tier3_never_auto_applied"
    }
  ],
  "files_modified": [
    {
      "file": "src/user_service.py",
      "changes_count": 8,
      "score_impact": -15
    },
    {
      "file": "src/auth_service.py",
      "changes_count": 4,
      "score_impact": -5
    }
  ]
}
```

## Auto-Detect Test Commands

The tool should auto-detect the test framework based on project structure:

| Detected | Test Command |
|----------|-------------|
| `pytest.ini`, `pyproject.toml` with pytest, `conftest.py` | `pytest` |
| `package.json` with `"test"` script | `npm test` |
| `package.json` with jest config | `npx jest` |
| `pubspec.yaml` with `flutter_test` | `flutter test` |
| `go.mod` with `go test` | `go test ./...` |
| `pom.xml` or `build.gradle` | `mvn test` / `gradle test` |
| `Makefile` with `test` target | `make test` |
| No detection | `echo "No test framework detected. Use --test-cmd"` |

## Git Integration

### Before applying fixes:
```bash
# Ensure clean working tree
git status --porcelain
if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: Working tree is not clean. Commit or stash changes first."
    exit 1
fi
```

### After applying fixes:
- Changes are applied in-place (no `.unslopped` files)
- Git diff is captured for each change
- If `--create-pr` is set: `git checkout -b unslopped` then `git add .` then `git commit -m "unslop: polish AI-generated code"` then `git push origin unslopped` then `gh pr create`

### If tests fail:
```bash
git reset --hard HEAD
echo "Tests failed. All changes reverted."
```

## Error Handling

| Error | Action |
|-------|--------|
| Working tree not clean | Abort with error message |
| No test framework detected | Warn, continue (Tier 1 fixes only) |
| Tests fail | Revert changes, abort |
| Git error (no repo) | Abort with error message |
| Too many iterations (max reached) | Save report, exit with code 1 |
| Score below threshold | Save report, exit with code 0 |
| File read error | Skip file, log warning, continue |
| Fix application error | Revert file, log error, continue |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — score < threshold or dry-run complete |
| 1 | Failure — max iterations reached, tests failed, or error occurred |
| 2 | Error — working tree not clean, no git repo, or invalid arguments |

## Integration Points

### Pi Skill
The Pi skill (`~/.pi/agent/skills/unslop/SKILL.md`) should be updated to reference `unslop fix` as an option:
- Current: `unslop scan` for passive analysis
- Future: `unslop fix --repo . --threshold 40 --run-tests` for active improvement

### Claude Code
Claude Code can use `unslop fix` as a post-code step:
```
After writing code, run: unslop fix --repo . --threshold 40 --run-tests
```

### CI/CD
GitHub Actions workflow (`.github/workflows/unslop.yml`):
```yaml
name: Unslop
on: [pull_request]
jobs:
  unslop:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run unslop fix
        run: |
          pip install unslop
          unslop fix --repo . --threshold 40 --dry-run
          unslop fix --repo . --threshold 40 --run-tests --report unslopped.md
```

## Implementation Plan

### Phase 1: Report Generator (Current Sprint)
- [ ] `unslop report --json` — structured JSON output
- [ ] `unslop report --markdown` — human-readable Markdown output
- [ ] Both formats include: changes, confidence, severity, git diff, reasoning

### Phase 2: Fix Pipeline (Next Sprint)
- [ ] `unslop fix --apply` — apply Tier 1 & 2 fixes in-place
- [ ] `unslop fix --dry-run` — show what would change
- [ ] `unslop fix --run-tests` — auto-detect and run test suite
- [ ] Iteration loop: scan → fix → test → re-scan

### Phase 3: PR & CI (Following Sprint)
- [ ] `unslop fix --create-pr` — create GitHub PR
- [ ] GitHub Actions workflow
- [ ] Git integration (clean tree check, revert on failure)

### Phase 4: Agent Protocol (Future)
- [ ] Standard agent-readable report format
- [ ] Autoring Agent integration
- [ ] Interactive mode (agent reviews each change before applying)

## Coding Style

Unslop itself follows Python conventions (PEP 8). When analyzing other repos, unslop **adopts the repo's existing conventions** — it does not impose its own style. This is handled by:
- `PatternIndex` detecting naming conventions per-file
- `cross_file_coherence` detecting import patterns
- `pattern_inconsistency` detecting naming deviations (with unittest/pytest exceptions)

Unslop does **not** enforce coding style. That's the job of linters (ruff, eslint, dart analyze). Unslop detects AI-generated patterns, not style violations.
