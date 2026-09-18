# Unslop Integration for Claude Code / Codex

## Overview

This file provides instructions for integrating unslop into Claude Code or Codex workflows. When working with AI-generated code, run unslop before creating a PR.

## Quick Commands

```bash
# Unslop a specific file
python -m unslop /path/to/file.py

# Unslop a TypeScript file
python -m unslop /path/to/file.ts

# Unslop the entire codebase (quality exercise)
python -m unslop --codebase /path/to/repo

# Unslop with verbose output
python -m unslop --verbose /path/to/file.py
```

## Integration with Claude Code

### In your `.claude/settings.json` or `.mdc` rules:

```json
{
  "unslop": {
    "enabled": true,
    "auto_run": true,
    "on_pr": true,
    "max_slop_score": 30
  }
}
```

### When Claude Code generates code:

1. Always run unslop on generated code before suggesting it for review
2. Apply fixes automatically
3. Report the slop score to the user
4. If the score is above the threshold, suggest improvements

### Example prompt for Claude Code:

```
After generating code, run unslop on it and apply fixes.
Report the slop score and any remaining issues that need review.
```

## Integration with Codex

### In your Codex configuration:

```yaml
unslop:
  enabled: true
  auto_fix: true
  max_slop_score: 30
  report_format: markdown
```

### When Codex generates code:

1. Generate the code
2. Run unslop
3. Apply fixes
4. Retest
5. If slop score is acceptable, proceed to PR

## Workflow Integration

```
1. Code generation
2. Unslop analysis
3. Auto-fix issues
4. Test
5. If slop score > threshold:
   a. Review remaining issues
   b. Fix manually if needed
   c. Retest
6. PR
```

## Slop Score Thresholds

| Threshold | Action |
|-----------|--------|
| 0-20 | Approve — code looks clean |
| 21-40 | Approve with review — minor issues |
| 41-60 | Request changes — several AI tells |
| 61-80 | Reject — multiple AI tells |
| 81-100 | Reject — strong AI-generated signals |

## Customizing for Your Codebase

### Pattern Index

Unslop builds a pattern index of your codebase. To improve accuracy:

1. Run unslop on the entire codebase first: `unslop --codebase /path/to/repo`
2. This builds a baseline of existing patterns
3. Subsequent file-level analyses will be more accurate

### Adding Custom Tells

To add custom tell detectors for your project:

1. Create a new file in `unslop/tells/`
2. Implement `detect(source, file_path, context)` → `list[UnslopIssue]`
3. Implement `fix(source, issues)` → `str`
4. Register in `unslop/analyzer.py`'s `TELL_DETECTIONS` list

## Security Bonus

Regardless of slop score, always flag:
- **SQL injection** — String-formatted queries
- **Hardcoded secrets** — API keys, tokens, passwords
- **Missing input validation** — User input without sanitization
- **Missing auth guards** — Endpoints without authentication
