"""Unit tests for sonar_auto_fixer's OWASP guidance enrichment.

Covers two things found via real execution, not speculation:
1. A genuine bug: the VULNERABILITY branch's fix instruction only had an
   f-string prefix on its first concatenated line, so '{rule}' was never
   substituted -- it printed as the literal text '{rule}'.
2. The vague "consult the OWASP guidelines" placeholder is replaced with
   real, category-specific guidance sourced from the sibling
   claude-global-library's application-security-core skill.
"""

from langgraph_engine.level3_execution.sonar_auto_fixer import (
    _GENERIC_OWASP_GUIDANCE,
    _owasp_guidance_for_finding,
    generate_fix_instruction,
)


def test_rule_name_is_actually_substituted_not_literal_placeholder():
    """Regression test for the f-string concatenation bug."""
    result = generate_fix_instruction(
        {
            "file": "app.py",
            "line": 10,
            "severity": "CRITICAL",
            "type": "VULNERABILITY",
            "rule": "python:sql-injection",
            "message": "Possible SQL injection",
        }
    )
    assert "python:sql-injection" in result["instruction"]
    assert "{rule}" not in result["instruction"]


def test_sql_injection_maps_to_injection_category_with_real_guidance():
    guidance = _owasp_guidance_for_finding("python:sql-injection", "Possible SQL injection")
    assert "A03: Injection" in guidance
    assert "parameterized queries" in guidance.lower()


def test_idor_maps_to_broken_access_control():
    guidance = _owasp_guidance_for_finding("python:idor", "Missing object-level authorization check")
    assert "A01: Broken Access Control" in guidance
    assert "server-side" in guidance.lower()


def test_weak_crypto_maps_to_cryptographic_failures():
    guidance = _owasp_guidance_for_finding("python:weak-crypto", "MD5 used for password hashing")
    assert "A02: Cryptographic Failures" in guidance


def test_unmapped_rule_falls_back_to_generic_but_concrete_guidance():
    """No keyword match must still return real content, not a broken placeholder."""
    guidance = _owasp_guidance_for_finding("python:some-unmapped-rule-xyz", "Something obscure")
    assert guidance == _GENERIC_OWASP_GUIDANCE
    assert "{rule}" not in guidance
    assert "OWASP Top 10" in guidance


def test_vulnerability_finding_always_produces_llm_fix_type():
    result = generate_fix_instruction(
        {
            "file": "app.py",
            "line": 5,
            "severity": "MAJOR",
            "type": "VULNERABILITY",
            "rule": "python:xss",
            "message": "Reflected XSS",
        }
    )
    assert result["fix_type"] == "llm"
    assert result["template_fix"] is None
    assert "A03: Injection (XSS)" in result["instruction"]
