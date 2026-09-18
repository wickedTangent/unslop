# Unslop — Implementation Status

## What's Built

### Core Library (`unslop/`)

| File | Purpose | Status |
|------|---------|--------|
| `__init__.py` | Public API | ✅ Done |
| `analyzer.py` | Main orchestrator | ✅ Done |
| `pattern_index.py` | Codebase pattern mapping | ✅ Done |
| `report.py` | Data structures | ✅ Done |
| `cli.py` | CLI entry point | ✅ Done |

### Tell Detectors & Fixers (`unslop/tells/`)

| Tell | Detector | Fixer | Research Source | Status |
|------|----------|-------|-----------------|--------|
| Generic naming | ✅ | ✅ | McKelvey Tell #4 | ✅ Done |
| Verbose comments | ✅ | ✅ | McKelvey Tell #1 | ✅ Done |
| Dead code | ✅ | ✅ | Git AutoReview #8, McKelvey #7 | ✅ Done |
| Empty error handling | ✅ | ✅ | McKelvey Tell #8, Git AutoReview #5 | ✅ Done |
| TODO artifacts | ✅ | ✅ | McKelvey Tell #6, Git AutoReview #10 | ✅ Done |
| Debug artifacts | ✅ | ✅ | Git AutoReview #10 | ✅ Done |
| Dependency bloat | ✅ | ✅ | McKelvey Tell #3, Git AutoReview #2 | ✅ Done |
| Pattern inconsistency | ✅ | ⚠️ | McKelvey Tell #2, Git AutoReview #12 | ⚠️ Partial (suggests only) |
| Security vulnerability | ✅ | ❌ | Veracode 2025, OWASP Top 10 | ✅ Detect only (auto-fix too risky) |
| Test quality | ✅ | ✅ | Cai & Tsantalis 2026, Veracode 2025 | ✅ Done |
| Volume analysis | ✅ | ❌ | McConnell "Code Complete" | ✅ Detect only (no safe fix) |
| Cross-file coherence | ✅ | ❌ | McKelvey Tell #2 | ✅ Detect only (requires full context) |
| Global incoherence | ✅ | ❌ | McKelvey Tell #9, Mothukuri & Parizi 2026 | ✅ Detect only (config + resource coherence) |

### Integration

| Integration | Status |
|-------------|--------|
| Pi skill (`~/.pi/agent/skills/unslop/SKILL.md`) | ✅ Done |
| Claude Code (`unslop/CLAUDE.md`) | ✅ Done |
| CLI (`unslop/cli.py`) | ✅ Done |
| Package (`pyproject.toml`) | ✅ Done |
| GitHub (`unslop/github.py`) | ✅ Done |

## GitHub Integration

| Component | Purpose |
|-----------|---------|
| `check_github()` | Verify gh CLI installed and authenticated |
| `create_pr()` | Create PR via `gh pr create` |
| `post_comment()` | Post comment on PR |
| `create_branch()` | Create and switch to new branch |
| `commit_changes()` | Stage and commit all changes |
| `push_branch()` | Push branch to remote |
| `get_repo_info()` | Extract owner/repo from remote URL |
| `format_pr_body()` | Generate PR body from fix results |

### Usage

```bash
# Create PR with fixes
unslop fix /path/to/repo --create-pr

# Custom PR title and base branch
unslop fix /path/to/repo --create-pr --pr-title "Fix AI tells" --pr-base develop
```

### Workflow

1. `unslop fix --create-pr` runs the fix pipeline
2. Creates a new branch (`unslop-fix-YYYYMMDD-HHMMSS`)
3. Commits all changes
4. Pushes branch to remote
5. Creates PR via `gh pr create`
6. Returns PR URL in output

## Test Results

### Unit Test Coverage

- **222 tests** across 18 test files
- All 12 tell detectors: detect + fix tested
- Core modules: PatternIndex, Report, FixPipeline, TestRunner, GitOps, CLI

### Auto-Fix Tiers

| Tier | Tells | Test Gate |
|------|-------|-----------|
| 1 (always safe) | verbose_comments, todo_artifacts, debug_artifacts | No |
| 2 (test-gated) | empty_error_handling, dead_code, dependency_bloat | Yes |
| 3 (never auto) | generic_naming, pattern_inconsistency, security, test_quality, volume, cross_file | N/A |

### Auto-Fix Capabilities

| Tell | What It Fixes |
|------|---------------|
| empty_error_handling | `except: pass` → `raise` |
| dead_code | Unused imports, unreachable code |
| dependency_bloat | Unused imports (bare + from-import, multi-import line aware) |
| generic_naming | `new_X`/`newX`, `my_X`/`myX`, `helper_X` prefix stripping |
| verbose_comments | Observable comment restatements |
| todo_artifacts | TODO/FIXME/HACK standalone lines |
| debug_artifacts | console.log, print, debugger statements |

## What's Working Well

1. **Empty error handling** — Detects and removes `except Exception: pass` blocks
2. **TODO artifacts** — Detects and removes TODO/FIXME/HACK comments
3. **Debug artifacts** — Detects and removes console.log/print/debugger
4. **Dependency bloat** — Detects unused imports and removes them
5. **Dead code** — Detects unused imports and unreachable code

## What Needs Improvement

1. **Verbose comments** — Detects but auto-fix is limited (needs judgment on which comments to keep)
2. **Pattern inconsistency** — Detects but only suggests (can't auto-fix without full context)
3. **Global incoherence** — Phantom API detection disabled due to high false positive rate; config incoherence and resource coherence working well
4. **Phase 3: PR & CI** — `unslop fix --create-pr`, GitHub Actions workflow, CI/CD integration

## What's Left to Build

### Phase 3: PR & CI Integration

1. **`unslop fix --create-pr`** — Create GitHub PR with fixes
2. **GitHub Actions workflow** — Auto-scan on PR
3. **CI/CD integration** — Block PRs with slop score above threshold

### Medium Priority

4. **Better comment fixer** — Distinguish between useful and verbose comments
5. **Cross-file coherence** — Detect when new code references APIs/config that don't exist
6. **`pattern_inconsistency` auto-fix** — Requires full codebase context for safe renaming
7. **Global incoherence phantom API** — Better filtering needed (currently disabled due to false positives)

### Out of Scope (Explicitly Excluded)

8. **More languages** — Java, C++, C#, Swift (Phase 2+)
9. **IDE extension** — Real-time slop scoring in VS Code / Cursor
10. **CI/CD pipeline gating** — Unslop scores and remediates, teams integrate however they want

## How to Use

### File-level (minimum)
```bash
unslop /path/to/file.py
unslop --fix /path/to/file.py  # Auto-fix
```

### Project-level (ideal)
```bash
unslop --codebase /path/to/repo
```

### Holistic quality exercise
```bash
unslop --codebase /path/to/repo --max-files 1000
```

### Pi skill
```
"unslop this file"
"unslop the codebase"
```

### Claude Code
Follow instructions in `unslop/CLAUDE.md`

## Research Citations

All tells are cited with their research sources in the code. Key sources:

1. **Justin McKelvey** — "9 Tells of AI-Generated Code" (2026) — 50+ real codebase rescues
2. **Git AutoReview** — "12-item Checklist for AI-Generated Code" — 470 PRs analyzed
3. **Cai & Tsantalis (2026)** — "AI-Generated Smells" — Volume-Quality Inverse Law
4. **Veracode 2025** — 45% of AI code has OWASP vulnerabilities
5. **USENIX Security 2025** — 5.2% package name hallucination rate
6. **Thoughtbot** — "How to Review AI-Generated PRs"
7. **Pyor** — "Reviewing AI-Generated Code: A Practical Checklist"
