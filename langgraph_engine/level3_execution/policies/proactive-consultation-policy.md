# Proactive Consultation Policy - DEPRECATED

**Version:** 2.0.0
**Status:** DEPRECATED (2026-03-17)
**Reason:** AskUserQuestion tool cannot be used within LangGraph pipeline execution context.

---

## Deprecation Notice

This policy required using `AskUserQuestion` for medium-complexity (4-6) decisions. However, the LangGraph orchestrator runs as a Python subprocess during hook execution, where interactive user consultation is not possible.

### What Replaced It

- **Complexity-based routing** in `version_selector.py` handles model selection automatically
- **Call graph and pattern data** inform decisions instead of asking users
- **Standards integration hooks** at Steps 10, 13 enforce constraints without user input

### Original Policy Scope

The original policy covered:
- User consultation for complexity scores 4-6
- Decision logging to policy-hits.log
- Transparent decision-making

These are now handled by the pipeline's automated decision engine.
