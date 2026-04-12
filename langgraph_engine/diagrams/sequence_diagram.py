"""
Sequence Diagram Generator - Tier 2 AST + LLM hybrid.

Generates Mermaid sequenceDiagram from call chain analysis.
When FQN call chains are available (CallGraph), class participants are used.
Falls back to flat caller/callee names from legacy AST extraction.
"""

import logging
from pathlib import Path

from .base import AbstractDiagramGenerator
from .templates import clean_mermaid

logger = logging.getLogger(__name__)


def _llm_call(prompt):
    """Call LLM via llm_call.py (lazy import, graceful fallback)."""
    try:
        from langgraph_engine.llm_call import llm_call

        return llm_call(prompt, model="fast", timeout=60)
    except ImportError:
        logger.debug("llm_call not available, skipping LLM enrichment")
        return None
    except Exception as e:
        logger.debug("LLM call failed: %s", e)
        return None


def _participant_name(fqn):
    """Extract class name or module name as participant from FQN.

    FQN format: "rel/path.py::ClassName.method" or "path/file.py::func"
    """
    if "::" not in fqn:
        return fqn
    after = fqn.split("::")[-1]  # "ClassName.method" or "func"
    if "." in after:
        return after.split(".")[0]  # ClassName
    # Standalone function -> use module stem
    before = fqn.split("::")[0]  # "path/file.py"
    return Path(before).stem


def _method_name(fqn):
    """Extract method/function name from FQN."""
    if "::" not in fqn:
        return fqn
    after = fqn.split("::")[-1]
    if "." in after:
        return after.split(".")[-1]
    return after


def _sequence_from_fqn_chains(call_chains, context=""):
    """Build class-aware sequence diagram from FQN call chains."""
    lines = ["sequenceDiagram"]

    # Collect participants in call order (stable ordering)
    participants = {}  # display_name -> insertion order
    order = 0

    for chain in call_chains:
        caller_fqn = chain.get("caller_fqn", "")
        callee_fqn = chain.get("callee_fqn", "")
        if not caller_fqn:
            continue
        cp = _participant_name(caller_fqn)
        if cp and cp not in participants:
            participants[cp] = order
            order += 1
        ep = _participant_name(callee_fqn)
        if ep and ep not in participants:
            participants[ep] = order
            order += 1

    # Declare participants in call order
    for name in sorted(participants, key=lambda k: participants[k]):
        safe = name.replace("-", "_").replace(".", "_")
        if safe != name:
            lines.append("    participant %s as %s" % (safe, name))
        else:
            lines.append("    participant %s" % safe)

    # Add call arrows
    seen = set()
    count = 0
    for chain in call_chains:
        caller_fqn = chain.get("caller_fqn", "")
        callee_fqn = chain.get("callee_fqn", "")
        if not caller_fqn or not callee_fqn:
            continue

        caller_p = _participant_name(caller_fqn).replace("-", "_").replace(".", "_")
        callee_p = _participant_name(callee_fqn).replace("-", "_").replace(".", "_")
        method = _method_name(callee_fqn)

        if caller_p == callee_p:
            key = (caller_p, method, "self")
        else:
            key = (caller_p, callee_p, method)

        if key in seen:
            continue
        seen.add(key)

        lines.append("    %s->>%s: %s()" % (caller_p, callee_p, method))
        count += 1
        if count >= 40:
            break

    if context:
        enriched_prompt = (
            "Improve this sequence diagram Mermaid diagram by adding better "
            "labels and notes. Output ONLY the improved Mermaid syntax, "
            "no markdown fences.\n\nCurrent diagram:\n%s\n\nContext:\n%s" % ("\n".join(lines), context[:1000])
        )
        enriched = _llm_call(enriched_prompt)
        if enriched:
            return clean_mermaid(enriched)

    return "\n".join(lines)


class SequenceDiagramGenerator(AbstractDiagramGenerator):
    """Generate Mermaid sequenceDiagram from call chains.

    Tier 2: AST + optional LLM enrichment.
    When CallGraph FQN data is present, class participants are used.
    """

    @property
    def diagram_type(self):
        return "sequence"

    def generate(self, analysis_data, format="mermaid"):
        """Generate Mermaid sequenceDiagram.

        Args:
            analysis_data: Dict with keys:
                - call_chains: list of call chain dicts (optional)
                - context: str context for LLM enrichment (optional)
                - project_root: project root path for AST fallback (optional)
            format: Ignored - always produces Mermaid syntax.

        Returns:
            Mermaid sequenceDiagram string.
        """
        call_chains = analysis_data.get("call_chains") if analysis_data else None
        context = (analysis_data.get("context") or "") if analysis_data else ""
        project_root = (analysis_data.get("project_root") or "") if analysis_data else ""

        if call_chains is None and project_root:
            # Fallback: per-file AST extraction
            from .ast_analyzer import UMLAstAnalyzer

            analyzer = UMLAstAnalyzer(project_root)
            call_chains = []
            from pathlib import Path as _Path

            root = _Path(project_root)
            for py_file in root.rglob("*.py"):
                rel = str(py_file.relative_to(root))
                if any(skip in rel for skip in ["__pycache__", ".venv", "test"]):
                    continue
                chains = analyzer.extract_call_chains(py_file)
                call_chains.extend(chains[:20])
                if len(call_chains) >= 80:
                    break

        if not call_chains:
            return "sequenceDiagram\n    Note over System: No call chains found"

        # Use FQN-aware path when available
        has_fqn = any(c.get("caller_fqn") for c in call_chains)
        if has_fqn:
            return _sequence_from_fqn_chains(call_chains, context)

        # Legacy flat path
        lines = ["sequenceDiagram"]
        seen = set()
        count = 0
        for chain in call_chains:
            key = (chain["caller"], chain["callee"])
            if key in seen or chain["caller"] == chain["callee"]:
                continue
            seen.add(key)
            lines.append("    %s->>%s: %s()" % (chain["caller"], chain["callee"], chain["callee"]))
            count += 1
            if count >= 30:
                break

        if context:
            enrich_prompt = (
                "Improve this sequence diagram Mermaid diagram by adding better "
                "labels and notes. Output ONLY the improved Mermaid syntax, "
                "no markdown fences.\n\nCurrent diagram:\n%s\n\nContext:\n%s" % ("\n".join(lines), context[:1000])
            )
            enriched = _llm_call(enrich_prompt)
            if enriched:
                return clean_mermaid(enriched)

        return "\n".join(lines)


def _register():
    try:
        from . import DiagramFactory

        DiagramFactory.register("sequence", SequenceDiagramGenerator)
    except ImportError:
        pass  # DiagramFactory not yet available (circular import guard)


_register()
