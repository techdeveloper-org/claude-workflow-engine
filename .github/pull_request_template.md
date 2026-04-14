## Summary

<!-- What does this PR do? One paragraph max. -->

## Related Issue

Closes #<!-- issue number -->

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup
- [ ] Documentation
- [ ] Tests only

## Changes Made

<!-- Bullet list of what changed and why -->

-
-

## Testing Done

- [ ] `pytest tests/` — 793/793 (or more) pass
- [ ] `ruff check .` — zero errors
- [ ] Tested manually with `python scripts/3-level-flow.py --task "..."`

## Checklist

- [ ] No `# ruff: noqa: F821` file-level suppressors added
- [ ] No hardcoded paths — using `path_resolver.py`
- [ ] ASCII-only in `.py` files (no non-ASCII literals)
- [ ] New public functions have tests
- [ ] No new LLM providers added (engine uses `claude_cli` + `anthropic` only)
