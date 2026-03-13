#!/bin/bash

# Sync Claude Insight changes to Claude Global Library

SOURCE_DIR="$(pwd)"
GLOBAL_DIR="../claude-global-library"

echo "🔄 Syncing Claude Insight to Global Library..."
echo "Source: $SOURCE_DIR"
echo "Target: $GLOBAL_DIR"

if [ ! -d "$GLOBAL_DIR" ]; then
    echo "❌ Global library not found at $GLOBAL_DIR"
    exit 1
fi

# Copy key documentation
echo "📄 Copying documentation..."
cp PHASE2_COMPLETE_GUIDE.md "$GLOBAL_DIR/docs/PHASE2_WORKFLOW_GUIDE.md"
cp FINAL_SUMMARY.txt "$GLOBAL_DIR/docs/PHASE2_FINAL_SUMMARY.txt"
cp System_Requirement_Analysis.md "$GLOBAL_DIR/docs/REQUIREMENTS_ANALYSIS.md"

# Copy E2E test
echo "🧪 Copying E2E test..."
cp test_end_to_end_workflow.py "$GLOBAL_DIR/docs/"

# Sync orchestrator-agent documentation
echo "🤖 Updating orchestrator-agent..."
cat > "$GLOBAL_DIR/agents/orchestrator-agent/PHASE2_WORKFLOW.md" << 'AGENT_DOC'
# Orchestrator Agent - Phase 2 Workflow

The orchestrator-agent now uses the full 14-step WORKFLOW.md-compliant pipeline.

## 14 Steps:
1. Task Analysis
2. Plan Mode Decision (CONDITIONAL)
3-7. Skill Selection & Validation
8-12. GitHub Workflow Integration
13-14. Documentation & Summary

See PHASE2_WORKFLOW_GUIDE.md for complete details.
AGENT_DOC

echo "✅ Documentation synced"

# Git commit in global library
cd "$GLOBAL_DIR"
git add -A
git commit -m "docs: sync Phase 2-4 workflow documentation from claude-insight

- Added PHASE2_WORKFLOW_GUIDE.md
- Added FINAL_SUMMARY.txt 
- Added E2E test documentation
- Updated orchestrator-agent with new workflow info" || true

cd "$SOURCE_DIR"
echo "✅ All synced!"
