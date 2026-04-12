# Version Bump & Release Policy (ALWAYS ACTIVE)

## System-Level Requirement

This is a **permanent rule** that applies to all 3 ecosystem repositories after every code push.

---

## Mandatory Version & Release Workflow

### When Code Changes Are Pushed (MANDATORY)

After ANY code commit is pushed to a repository, Claude MUST perform these steps:

#### Step 1: Version Bump

**For claude-code-ide:**
1. Bump `APP_VERSION` in `src/main/java/com/claudecodeide/App.java`
2. Update `VERSION` file at repo root (must match `APP_VERSION`)
3. Version strategy: patch (0.x.Y) for fixes, minor (0.X.0) for features

**For claude-insight:**
1. Update `VERSION` file at repo root
2. Ensure `README.md` header, badge, and footer version match
3. Ensure `CLAUDE.md` version header matches

**For claude-global-library:**
1. Update `VERSION` file at repo root
2. Ensure `README.md` badge version matches

#### Step 2: Build (claude-code-ide only)

```bash
mvn clean package -q -DskipTests
```

Verify `target/claude-code-ide.jar` exists.

#### Step 3: Commit Version Bump

```bash
git add [version files]
git commit -m "bump: v{OLD} -> v{NEW} — {brief description}"
git push origin main
```

#### Step 4: Create GitHub Release (claude-code-ide only)

```bash
gh release create v{VERSION} target/claude-code-ide.jar \
  --title "v{VERSION} — {brief title}" \
  --notes "{changelog notes}"
```

**Why:** The IDE update checker compares `App.APP_VERSION` against the remote `VERSION` file via `raw.githubusercontent.com`. If versions match, no update is detected. Skipping this step means users never see updates.

---

## Changelog Requirements

### Every Version Bump MUST Include

A commit message or release notes describing:
1. **What changed** — files modified, features added/fixed
2. **Why** — the reason for the change
3. **Commit SHA** — reference to the code change commit

### Format

```
## What's New in v{VERSION}

### {Category: Features / Fixes / Docs}
- {Description of change 1} (`{commit_sha}`)
- {Description of change 2} (`{commit_sha}`)
```

---

## Version Consistency Rule

All version references within a single repo MUST match:

| Repo | Version Sources (MUST all match) |
|------|----------------------------------|
| **claude-code-ide** | `VERSION`, `App.APP_VERSION`, GitHub Release tag |
| **claude-insight** | `VERSION`, `README.md` (header + badge + footer), `CLAUDE.md` |
| **claude-global-library** | `VERSION`, `README.md` badge |

If any mismatch is detected, fix it immediately before proceeding.

---

## Exception Cases

**Do NOT bump version when:**
- Only documentation files changed (README, CLAUDE.md, comments)
- The commit is itself a version bump commit
- User explicitly says "don't bump version"

---

## Status

**ACTIVE**: This policy is permanent and applies to all sessions.
**Version**: 1.0.0
**Last Updated**: 2026-03-02
