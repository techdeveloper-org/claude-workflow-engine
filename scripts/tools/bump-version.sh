#!/bin/bash
# Automatic Version Bump, Tag, and Release Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Run Python version bumper
python "$SCRIPT_DIR/bump-version.py" "$@"

# If successful and version was bumped
if [ $? -eq 0 ] && [ -n "$1" ]; then
    NEW_VERSION=$(cat "$PROJECT_ROOT/VERSION")
    BUMP_TYPE="$1"

    cd "$PROJECT_ROOT"

    # Update README.md and CHANGELOG.md
    echo ""
    echo "Updating documentation..."
    python "$SCRIPT_DIR/update-docs.py" "$NEW_VERSION" "$BUMP_TYPE"

    # Commit version change + documentation
    git add VERSION src/app.py templates/base.html README.md CHANGELOG.md
    git commit -m "chore: bump version to ${NEW_VERSION}

- Updated VERSION file
- Updated README.md version badge
- Added CHANGELOG.md entry
- Auto-generated release notes"

    # Create and push tag
    git tag "v${NEW_VERSION}"
    git push origin main --tags

    echo ""
    echo "[OK] Version ${NEW_VERSION} tagged and pushed!"
    echo ""

    # Auto-create GitHub Release using gh CLI
    echo "Creating GitHub Release..."

    # Generate simple release notes
    PREV_TAG=$(git describe --tags --abbrev=0 HEAD^ 2>/dev/null || echo "")

    if [ -z "$PREV_TAG" ]; then
        NOTES="Initial release of Claude Workflow Engine v${NEW_VERSION}"
    else
        # Extract from CHANGELOG.md
        CHANGELOG_ENTRY=$(awk "/## \[${NEW_VERSION}\]/,/^---$/" "$PROJECT_ROOT/CHANGELOG.md" | sed '1d;$d')

        if [ -z "$CHANGELOG_ENTRY" ]; then
            # Fallback to git log
            CHANGELOG_ENTRY=$(git log ${PREV_TAG}..HEAD --pretty=format:"- %s" --no-merges | head -20)
        fi

        NOTES=$(cat <<EOF
Claude Workflow Engine v${NEW_VERSION}

${CHANGELOG_ENTRY}

**Full Changelog**: https://github.com/techdeveloper-org/claude-workflow-engine/compare/${PREV_TAG}...v${NEW_VERSION}
EOF
)
    fi

    # Create release
    gh release create "v${NEW_VERSION}" \
        --title "Release v${NEW_VERSION}" \
        --notes "$NOTES"

    echo ""
    echo "[OK] Release created successfully!"
    echo "View: https://github.com/techdeveloper-org/claude-workflow-engine/releases/tag/v${NEW_VERSION}"
fi
