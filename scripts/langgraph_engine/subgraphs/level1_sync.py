"""
Level 1 SubGraph - Context Sync System (CORRECTED)

CORRECT FLOW (per user specification):
1. node_session_loader (FIRST) - Create session in ~/.claude/logs/sessions/{session_id}/
2. node_complexity_calculation (PARALLEL with #3) - Analyze project structure
3. node_context_loader (PARALLEL with #2) - Read SRS, README, CLAUDE.md from PROJECT
4. node_toon_compression (NEW) - Compress to TOON format + clear memory
5. level1_merge_node - Final merge
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

try:
    from langgraph.graph import StateGraph, START, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

from ..flow_state import FlowState

try:
    import toons
    _TOONS_AVAILABLE = True
except ImportError:
    _TOONS_AVAILABLE = False


# ============================================================================
# NODE 1: SESSION LOADER (MUST BE FIRST)
# ============================================================================

def node_session_loader(state: FlowState) -> dict:
    """Create and load session in ~/.claude/logs/sessions/{session_id}/.

    This MUST run first - creates the session container for this execution.
    """
    import uuid

    try:
        # Generate unique session ID
        session_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # Create session folder: ~/.claude/logs/sessions/{session_id}/
        session_path = Path.home() / ".claude" / "logs" / "sessions" / session_id
        session_path.mkdir(parents=True, exist_ok=True)

        # Save session metadata
        session_meta = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "user_message": state.get("user_message", ""),
        }

        meta_file = session_path / "session.json"
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(session_meta, f, indent=2)

        return {
            "session_id": session_id,
            "session_path": str(session_path),
            "session_loaded": True,
        }
    except Exception as e:
        return {
            "session_loaded": False,
            "session_error": str(e),
        }


# ============================================================================
# NODE 2: COMPLEXITY CALCULATION (PARALLEL with context_loader)
# ============================================================================

def node_complexity_calculation(state: FlowState) -> dict:
    """Analyze project structure and calculate complexity.

    Uses existing complexity calculation scripts to understand:
    - Project architecture
    - Call stack and graph
    - Complexity score
    """
    try:
        project_root = Path(state.get("project_root", "."))

        # Call complexity calculation script if it exists
        complexity_script = (
            Path(__file__).parent.parent.parent /
            "architecture" / "03-execution-system" / "04-model-selection" /
            "complexity-calculator.py"
        )

        if complexity_script.exists():
            result = subprocess.run(
                [sys.executable, str(complexity_script)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=project_root
            )

            # Parse output
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    return {
                        "complexity_score": data.get("complexity_score", 5),
                        "project_graph": data.get("graph", {}),
                        "architecture": data.get("architecture", {}),
                        "complexity_calculated": True,
                    }
                except:
                    pass

        # Fallback: basic complexity calculation
        py_files = list(project_root.glob("**/*.py"))
        complexity_score = min(10, max(1, len(py_files) // 50))

        return {
            "complexity_score": complexity_score,
            "project_graph": {},
            "architecture": {},
            "complexity_calculated": True,
        }
    except Exception as e:
        return {
            "complexity_calculated": False,
            "complexity_error": str(e),
            "complexity_score": 5,  # Default
        }


# ============================================================================
# NODE 3: CONTEXT LOADER (PARALLEL with complexity_calculation)
# ============================================================================

def node_context_loader(state: FlowState) -> dict:
    """Load context from PROJECT FILES (not ~/.claude/memory/).

    Reads from project folder:
    - SRS (if exists)
    - README.md (if exists)
    - CLAUDE.md (if exists)

    Saves to session folder.
    """
    try:
        project_root = Path(state.get("project_root", "."))
        session_path = Path(state.get("session_path", ""))

        context_data = {
            "srs": None,
            "readme": None,
            "claude_md": None,
            "files_loaded": [],
        }

        # Try to load SRS
        srs_paths = list(project_root.glob("**/[Ss][Rr][Ss].*"))
        if srs_paths:
            try:
                content = srs_paths[0].read_text(encoding='utf-8', errors='ignore')
                context_data["srs"] = content[:5000]  # First 5000 chars
                context_data["files_loaded"].append("SRS")
            except:
                pass

        # Try to load README
        readme_paths = list(project_root.glob("**/[Rr][Ee][Aa][Dd][Mm][Ee].*"))
        if readme_paths:
            try:
                content = readme_paths[0].read_text(encoding='utf-8', errors='ignore')
                context_data["readme"] = content[:5000]
                context_data["files_loaded"].append("README")
            except:
                pass

        # Try to load CLAUDE.md
        claude_paths = list(project_root.glob("**/[Cc][Ll][Aa][Uu][Dd][Ee].[Mm][Dd]"))
        if claude_paths:
            try:
                content = claude_paths[0].read_text(encoding='utf-8', errors='ignore')
                context_data["claude_md"] = content[:5000]
                context_data["files_loaded"].append("CLAUDE.md")
            except:
                pass

        # Save context to session folder
        if session_path:
            context_file = Path(session_path) / "context-raw.json"
            with open(context_file, 'w', encoding='utf-8') as f:
                json.dump(context_data, f, indent=2)

        return {
            "context_data": context_data,
            "context_loaded": True,
            "files_loaded_count": len(context_data["files_loaded"]),
        }
    except Exception as e:
        return {
            "context_loaded": False,
            "context_error": str(e),
            "context_data": {},
        }


# ============================================================================
# NODE 4: TOON COMPRESSION (NEW - Compress + Clear Memory)
# ============================================================================

def node_toon_compression(state: FlowState) -> dict:
    """Compress context to TOON format and save to session folder.

    After this:
    - Verbose data saved to disk as TOON
    - Memory variables cleared
    - Only compact TOON remains in memory

    TOON object includes:
    - session_id
    - complexity_score
    - files_loaded_count
    - compressed context
    """
    try:
        session_path = Path(state.get("session_path", ""))
        context_data = state.get("context_data", {})
        complexity_score = state.get("complexity_score", 5)
        session_id = state.get("session_id", "")
        files_loaded = context_data.get("files_loaded", [])

        # Build TOON object WITH complexity and file count INSIDE
        toon_object = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "complexity_score": complexity_score,  # ✓ INSIDE TOON
            "files_loaded_count": len(files_loaded),  # ✓ INSIDE TOON
            "context": {
                "files": files_loaded,
                "srs": bool(context_data.get("srs")),  # Just boolean, not full content
                "readme": bool(context_data.get("readme")),
                "claude_md": bool(context_data.get("claude_md")),
            }
        }

        # Save TOON to session folder (uses toons format if available)
        if session_path:
            toon_file = Path(session_path) / "context.toon.json"
            if _TOONS_AVAILABLE:
                try:
                    # Use TOONS for efficient serialization
                    with open(toon_file, 'w', encoding='utf-8') as f:
                        f.write(toons.dumps(toon_object))
                except:
                    # Fallback to standard JSON
                    with open(toon_file, 'w', encoding='utf-8') as f:
                        json.dump(toon_object, f, indent=2)
            else:
                # Standard JSON serialization
                with open(toon_file, 'w', encoding='utf-8') as f:
                    json.dump(toon_object, f, indent=2)

        # Return TOON object, signal memory cleanup
        return {
            "toon_object": toon_object,  # Return the TOON dict (with session_id, complexity, files_count)
            "toon_saved": True,
            "clear_verbose_memory": True,  # Signal to clear: srs, readme, claude_md, context_data
        }
    except Exception as e:
        return {
            "toon_saved": False,
            "toon_error": str(e),
            "toon_object": {},
        }


# ============================================================================
# MERGE NODE - Final Level 1 output
# ============================================================================

def level1_merge_node(state: FlowState) -> dict:
    """Merge all Level 1 data and prepare for Level 2.

    OUTPUT: Only TOON object (contains session_id, complexity_score, files_loaded_count + context)
    CLEARED: All verbose variables from memory
    """
    # Build final Level 1 output
    updates = {
        "level1_complete": True,
        "level1_context_toon": state.get("toon_object", {}),  # ✓ TOON has everything inside
    }

    # Signal memory cleanup - these variables should be cleared from memory
    # (not from disk, just from RAM variables)
    cleanup_signals = {
        "clear_memory": [
            "context_data",      # Full context dict
            "srs",               # Raw SRS content
            "readme",            # Raw README content
            "claude_md",         # Raw CLAUDE.md content
            "complexity_score",  # Now in TOON object
            "files_loaded_count",# Now in TOON object
            "project_graph",     # Large graph object
            "architecture",      # Large architecture object
        ]
    }

    updates.update(cleanup_signals)

    return updates


# ============================================================================
# HELPER: Actual memory cleanup function (called separately)
# ============================================================================

def cleanup_level1_memory(state: FlowState) -> dict:
    """Actually remove verbose variables from state.

    This is called AFTER level1_merge to free up RAM.
    """
    # In Python, we just return empty dicts for these fields
    # LangGraph will update the state
    cleanup = {
        "context_data": None,
        "srs": None,
        "readme": None,
        "claude_md": None,
        "project_graph": None,
        "architecture": None,
    }
    return cleanup
