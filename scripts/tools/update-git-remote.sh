#!/bin/bash
# Update Git Remote URL after renaming repository on GitHub

# बताओ क्या नया नाम रखना है?
echo "Current repository: claude-monitoring-system"
echo ""
echo "GitHub पर repository rename करने के बाद ये script run करो:"
echo ""
read -p "Enter new repository name (e.g., claude-workflow-engine): " NEW_REPO_NAME

if [ -z "$NEW_REPO_NAME" ]; then
    echo "Error: Repository name cannot be empty!"
    exit 1
fi

# New remote URL
NEW_URL="https://github.com/techdeveloper-org/${NEW_REPO_NAME}.git"

echo ""
echo "Updating remote URL to: $NEW_URL"
echo ""

# Update remote URL
git remote set-url origin "$NEW_URL"

# Verify
echo "✓ Remote URL updated!"
echo ""
echo "Verification:"
git remote -v

echo ""
echo "✓ Done! Repository remote updated successfully."
echo ""
echo "Ab git push/pull normally kaam karega with new repository name."
