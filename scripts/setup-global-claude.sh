#!/bin/bash
# =============================================================================
# Claude Insight - Global Claude Memory System Setup (Unix/macOS/Linux/WSL)
# =============================================================================
# This script sets up the Claude Memory System (3-Level Architecture) in your
# ~/.claude directory so Claude Code follows the enforcement policies
# automatically on every request.
#
# What this does:
#   1. Creates ~/.claude/ if it doesn't exist
#   2. Creates ~/.claude/memory/current/ with core scripts
#   3. Installs hooks in ~/.claude/settings.json
#   4. Installs global CLAUDE.md (3-level architecture)
#
# What this does NOT do:
#   - Does not add any project-specific information to your global CLAUDE.md
#   - Does not modify existing project CLAUDE.md files
#   - Does not touch any source code or project files
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CLAUDE_DIR="$HOME/.claude"
MEMORY_CURRENT="$CLAUDE_DIR/memory/current"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"
GLOBAL_CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "============================================================"
echo " Claude Insight - Global Memory System Setup"
echo "============================================================"
echo ""

# Step 1: Create ~/.claude directory structure
echo "[1/5] Setting up ~/.claude directory..."
mkdir -p "$CLAUDE_DIR"
mkdir -p "$MEMORY_CURRENT"
mkdir -p "$CLAUDE_DIR/memory/logs/sessions"
mkdir -p "$CLAUDE_DIR/memory/sessions"
mkdir -p "$CLAUDE_DIR/skills"
mkdir -p "$CLAUDE_DIR/agents"
mkdir -p "$CLAUDE_DIR/hooks"
echo "[OK] ~/.claude directory structure created"

# Step 2: Copy core enforcement scripts from this project
echo "[2/5] Installing core enforcement scripts..."

SCRIPTS_TO_COPY=(
    "auto-fix-enforcer.sh"
    "auto-enforce-all-policies.sh"
    "session-start.sh"
    "per-request-enforcer.py"
    "context-monitor-v2.py"
    "blocking-policy-enforcer.py"
    "session-id-generator.py"
    "session-id-generator.sh"
    "session-logger.py"
    "detect-sync-eligibility.py"
    "clear-session-handler.py"
    "stop-notifier.py"
    "pre-tool-enforcer.py"
    "post-tool-tracker.py"
)

COPIED=0
SKIPPED=0

for script in "${SCRIPTS_TO_COPY[@]}"; do
    src="$SCRIPT_DIR/$script"
    dst="$MEMORY_CURRENT/$script"
    if [ -f "$src" ]; then
        cp "$src" "$dst"
        chmod +x "$dst" 2>/dev/null || true
        echo "  [OK] $script"
        COPIED=$((COPIED + 1))
    else
        echo "  [SKIP] $script (not found in scripts/)"
        SKIPPED=$((SKIPPED + 1))
    fi
done

# Copy 3-level-flow script (the main hook entry point)
if [ -f "$SCRIPT_DIR/3-level-flow.py" ]; then
    cp "$SCRIPT_DIR/3-level-flow.py" "$MEMORY_CURRENT/3-level-flow.py"
    echo "  [OK] 3-level-flow.py"
    COPIED=$((COPIED + 1))
fi

echo "[OK] $COPIED scripts copied, $SKIPPED skipped"

# Step 3: Install global CLAUDE.md
echo "[3/5] Installing global CLAUDE.md..."

TEMPLATE="$SCRIPT_DIR/../docs/templates/global-claude-md-template.md"

if [ -f "$GLOBAL_CLAUDE_MD" ]; then
    echo "  [INFO] Existing ~/.claude/CLAUDE.md found"
    echo "  [INFO] Backing up to ~/.claude/CLAUDE.md.backup"
    cp "$GLOBAL_CLAUDE_MD" "$GLOBAL_CLAUDE_MD.backup"

    # Check if it already has the 3-level architecture
    if grep -q "HARDCODED 3-LEVEL ARCHITECTURE" "$GLOBAL_CLAUDE_MD" 2>/dev/null; then
        echo "  [OK] Global CLAUDE.md already has 3-level architecture - keeping existing"
    else
        echo "  [INFO] Merging 3-level architecture into existing CLAUDE.md"
        # Prepend the template to the existing file
        cat "$TEMPLATE" > "$GLOBAL_CLAUDE_MD.new"
        echo "" >> "$GLOBAL_CLAUDE_MD.new"
        echo "---" >> "$GLOBAL_CLAUDE_MD.new"
        echo "# EXISTING CUSTOM CONFIGURATION" >> "$GLOBAL_CLAUDE_MD.new"
        echo "---" >> "$GLOBAL_CLAUDE_MD.new"
        cat "$GLOBAL_CLAUDE_MD" >> "$GLOBAL_CLAUDE_MD.new"
        mv "$GLOBAL_CLAUDE_MD.new" "$GLOBAL_CLAUDE_MD"
        echo "  [OK] 3-level architecture merged into existing CLAUDE.md"
    fi
else
    # No existing CLAUDE.md - install fresh
    if [ -f "$TEMPLATE" ]; then
        cp "$TEMPLATE" "$GLOBAL_CLAUDE_MD"
        echo "  [OK] Global CLAUDE.md installed from template"
    else
        echo "  [WARN] Template not found at $TEMPLATE"
        echo "  [INFO] Creating minimal CLAUDE.md..."
        cat > "$GLOBAL_CLAUDE_MD" << 'EOF'
# Claude Memory System
# Install claude-insight for the full 3-level architecture setup.
# See: https://github.com/piyushmakhija28/claude-insight
EOF
    fi
fi

# Step 4: Install hooks in settings.json (from settings-config.json)
echo "[4/5] Installing hooks in ~/.claude/settings.json..."

CONFIG_FILE="$SCRIPT_DIR/settings-config.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "  [ERROR] settings-config.json not found at $CONFIG_FILE"
    echo "  [INFO] This file should be in the scripts/ directory of claude-insight"
    exit 1
fi

if [ -f "$SETTINGS_FILE" ]; then
    echo "  [INFO] Existing settings.json found"
    # Check if hooks already installed
    if grep -q "3-level-flow" "$SETTINGS_FILE" 2>/dev/null; then
        echo "  [OK] Hooks already configured in settings.json - skipping"
    else
        echo "  [WARN] settings.json exists but no 3-level-flow hooks found"
        echo "  [INFO] Installing hooks from settings-config.json..."
        cp "$CONFIG_FILE" "$SETTINGS_FILE"
        echo "  [OK] Hooks installed from settings-config.json"
    fi
else
    # Create new settings.json from config template
    echo "  [INFO] Creating new settings.json from settings-config.json..."
    cp "$CONFIG_FILE" "$SETTINGS_FILE"
    echo "  [OK] settings.json created from settings-config.json"
fi

# Step 5: Finalize
echo "[5/5] Finalizing..."
echo "1.0.0" > "$MEMORY_CURRENT/VERSION"
echo "Claude Insight Memory System" > "$MEMORY_CURRENT/MANIFEST.md"
echo "Installed: $(date)" >> "$MEMORY_CURRENT/MANIFEST.md"

echo ""
echo "============================================================"
echo " Setup Complete!"
echo "============================================================"
echo ""
echo " Installed to: $CLAUDE_DIR"
echo " Core scripts: $MEMORY_CURRENT"
echo " Global CLAUDE.md: $GLOBAL_CLAUDE_MD"
echo " Settings: $SETTINGS_FILE"
echo ""
echo " NEXT STEPS:"
echo "  1. Restart Claude Code (close and reopen)"
echo "  2. The 3-level architecture will run automatically"
echo "     on every message you send"
echo ""
echo " IMPORTANT:"
echo "  - The global CLAUDE.md contains the 3-level architecture rules"
echo "  - Do NOT add project-specific info to ~/.claude/CLAUDE.md"
echo "  - Add project info to your PROJECT's CLAUDE.md instead"
echo "  - Project CLAUDE.md adds context but cannot override global policies"
echo ""
