#!/bin/bash
################################################################################
# SMART SYNC TO CLAUDE INSIGHT
#
# Automatically syncs ONLY global/reusable content to Claude Insight.
# Uses detect-sync-eligibility.py to prevent syncing project-specific content.
#
# Usage:
#   bash smart-sync-to-claude-insight.sh --skill "skill-name"
#   bash smart-sync-to-claude-insight.sh --agent "agent-name"
#   bash smart-sync-to-claude-insight.sh --policy "policy-file.md"
#   bash smart-sync-to-claude-insight.sh --doc "doc-file.md"
#   bash smart-sync-to-claude-insight.sh --script "script-file.py"
#
# Exit Codes:
#   0 = Synced successfully
#   1 = NOT synced (project-specific)
#   2 = NOT synced (needs manual review/cleanup)
#
# Version: 1.0.0
# Date: 2026-02-17
################################################################################

set -e

MEMORY_PATH="$HOME/.claude/memory"
# Auto-detect project path from git root or fallback to env var
CLAUDE_INSIGHT_PATH="${CLAUDE_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/claude-workflow-engine")}"
DETECTOR="$MEMORY_PATH/current/detect-sync-eligibility.py"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
TYPE=""
NAME=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --skill)
            TYPE="skill"
            NAME="$2"
            shift 2
            ;;
        --agent)
            TYPE="agent"
            NAME="$2"
            shift 2
            ;;
        --policy)
            TYPE="policy"
            NAME="$2"
            shift 2
            ;;
        --doc)
            TYPE="doc"
            NAME="$2"
            shift 2
            ;;
        --script)
            TYPE="script"
            NAME="$2"
            shift 2
            ;;
        --claude-md)
            TYPE="claude-md"
            shift
            ;;
        --master-readme)
            TYPE="master-readme"
            shift
            ;;
        *)
            echo "❌ Unknown option: $1"
            echo ""
            echo "Usage:"
            echo "  bash smart-sync-to-claude-insight.sh --skill 'skill-name'"
            echo "  bash smart-sync-to-claude-insight.sh --agent 'agent-name'"
            echo "  bash smart-sync-to-claude-insight.sh --policy 'policy-file.md'"
            echo "  bash smart-sync-to-claude-insight.sh --doc 'doc-file.md'"
            echo "  bash smart-sync-to-claude-insight.sh --script 'script-file.py'"
            echo "  bash smart-sync-to-claude-insight.sh --claude-md"
            echo "  bash smart-sync-to-claude-insight.sh --master-readme"
            exit 1
            ;;
    esac
done

if [ -z "$TYPE" ]; then
    echo "❌ Error: No type specified"
    exit 1
fi

echo ""
echo "================================================================================"
echo "🔍 SMART SYNC TO CLAUDE INSIGHT - DETECTION MODE"
echo "================================================================================"
echo ""

# Function to detect and sync
detect_and_sync() {
    local detector_args="$1"
    local source_path="$2"
    local dest_path="$3"
    local item_name="$4"

    echo "${BLUE}[1/2] Running eligibility detection...${NC}"
    echo ""

    # Run detector
    python "$DETECTOR" $detector_args
    DETECTION_EXIT=$?

    echo ""

    if [ $DETECTION_EXIT -eq 0 ]; then
        # Eligible - proceed with sync
        echo "${GREEN}[2/2] Syncing to Claude Insight...${NC}"
        echo ""

        # Create destination directory if needed
        mkdir -p "$(dirname "$dest_path")"

        # Copy
        cp -r "$source_path" "$dest_path"

        if [ $? -eq 0 ]; then
            echo "${GREEN}✅ SYNCED SUCCESSFULLY${NC}"
            echo ""
            echo "   Source: $source_path"
            echo "   Destination: $dest_path"
            echo ""
            return 0
        else
            echo "${RED}❌ SYNC FAILED${NC}"
            echo ""
            echo "   Error: Copy command failed"
            echo ""
            return 1
        fi

    elif [ $DETECTION_EXIT -eq 2 ]; then
        # Warning - needs review
        echo "${YELLOW}[2/2] SYNC SKIPPED - Manual review needed${NC}"
        echo ""
        echo "Action required:"
        echo "   1. Review the file: $source_path"
        echo "   2. Replace project-specific examples with generic ones"
        echo "   3. Run smart-sync again after cleanup"
        echo ""
        return 2

    else
        # Not eligible - project-specific
        echo "${RED}[2/2] SYNC BLOCKED - Project-specific content${NC}"
        echo ""
        echo "This content should NOT be synced to Claude Insight (public repo)."
        echo "It contains project-specific business logic or references."
        echo ""
        return 1
    fi
}

# Process based on type
case $TYPE in
    skill)
        echo "Type: Skill"
        echo "Name: $NAME"
        echo ""

        SOURCE="$HOME/.claude/skills/$NAME"
        DEST="$CLAUDE_INSIGHT_PATH/skills/$NAME"

        if [ ! -d "$SOURCE" ]; then
            echo "${RED}❌ Error: Skill not found: $SOURCE${NC}"
            exit 1
        fi

        detect_and_sync "--skill \"$NAME\"" "$SOURCE" "$DEST" "$NAME"
        ;;

    agent)
        echo "Type: Agent"
        echo "Name: $NAME"
        echo ""

        SOURCE="$HOME/.claude/agents/$NAME"
        DEST="$CLAUDE_INSIGHT_PATH/agents/$NAME"

        if [ ! -d "$SOURCE" ]; then
            echo "${RED}❌ Error: Agent not found: $SOURCE${NC}"
            exit 1
        fi

        detect_and_sync "--agent \"$NAME\"" "$SOURCE" "$DEST" "$NAME"
        ;;

    policy)
        echo "Type: Policy"
        echo "Name: $NAME"
        echo ""

        SOURCE="$MEMORY_PATH/$NAME"
        DEST="$CLAUDE_INSIGHT_PATH/policies/$NAME"

        if [ ! -f "$SOURCE" ]; then
            echo "${RED}❌ Error: Policy not found: $SOURCE${NC}"
            exit 1
        fi

        detect_and_sync "--file \"$SOURCE\"" "$SOURCE" "$DEST" "$NAME"
        ;;

    doc)
        echo "Type: Documentation"
        echo "Name: $NAME"
        echo ""

        SOURCE="$MEMORY_PATH/docs/$NAME"
        DEST="$CLAUDE_INSIGHT_PATH/docs/$NAME"

        if [ ! -f "$SOURCE" ]; then
            echo "${RED}❌ Error: Doc not found: $SOURCE${NC}"
            exit 1
        fi

        detect_and_sync "--file \"$SOURCE\"" "$SOURCE" "$DEST" "$NAME"
        ;;

    script)
        echo "Type: Script"
        echo "Name: $NAME"
        echo ""

        SOURCE="$MEMORY_PATH/scripts/$NAME"
        DEST="$CLAUDE_INSIGHT_PATH/scripts/$NAME"

        if [ ! -f "$SOURCE" ]; then
            echo "${RED}❌ Error: Script not found: $SOURCE${NC}"
            exit 1
        fi

        detect_and_sync "--file \"$SOURCE\"" "$SOURCE" "$DEST" "$NAME"
        ;;

    claude-md)
        echo "Type: CLAUDE.md (Global Configuration)"
        echo ""

        echo "${RED}❌ SYNC BLOCKED - Global CLAUDE.md should NEVER be synced${NC}"
        echo ""
        echo "Reason:"
        echo "   Global CLAUDE.md (~/.claude/CLAUDE.md) is PERSONAL configuration"
        echo "   It contains:"
        echo "   - Personal paths (C:\\Users\\techd\\...)"
        echo "   - Private session settings"
        echo "   - Personal preferences"
        echo "   - Out of context for public repos"
        echo ""
        echo "What to do instead:"
        echo "   ✅ Each public repo should have its own project-specific CLAUDE.md"
        echo "   ✅ Claude Insight has: claude-insight/CLAUDE.md (monitoring focused)"
        echo "   ✅ Claude Global Library has: claude-global-library/CLAUDE.md (skills/agents focused)"
        echo ""
        echo "Rule: Global CLAUDE.md stays LOCAL ONLY"
        echo ""
        exit 1
        ;;

    master-readme)
        echo "Type: MASTER-README.md"
        echo ""

        SOURCE="$MEMORY_PATH/MASTER-README.md"
        DEST="$CLAUDE_INSIGHT_PATH/MASTER-README.md"

        # MASTER-README is always global - skip detection
        echo "${GREEN}✅ MASTER-README.md is always global - syncing...${NC}"
        echo ""

        cp "$SOURCE" "$DEST"

        if [ $? -eq 0 ]; then
            echo "${GREEN}✅ SYNCED SUCCESSFULLY${NC}"
            echo ""
            echo "   Source: $SOURCE"
            echo "   Destination: $DEST"
            echo ""
        else
            echo "${RED}❌ SYNC FAILED${NC}"
            exit 1
        fi
        ;;

    *)
        echo "${RED}❌ Unknown type: $TYPE${NC}"
        exit 1
        ;;
esac

echo "================================================================================"
echo ""

exit $?
