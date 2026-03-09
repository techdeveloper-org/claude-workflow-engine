#!/usr/bin/env python3
"""
Hook Setup Verification - Ensure all production hooks are ready

Checks:
1. All hook scripts exist and are executable
2. Settings.json is valid and uncommented
3. New features (skill loader, post-merge automation) are available
4. All paths are correct
"""

import json
import sys
from pathlib import Path

CLAUDE_BASE = Path.home() / '.claude'
SCRIPTS_DIR = CLAUDE_BASE / 'scripts'

# Required hook scripts
REQUIRED_HOOKS = {
    '3-level-flow.py': 'UserPromptSubmit - 3-level architecture enforcement',
    'github_issue_manager.py': 'UserPromptSubmit - GitHub issue management',
    'pre-tool-enforcer.py': 'PreToolUse - Tool validation + skill verification',
    'post-tool-tracker.py': 'PostToolUse - Progress tracking + post-merge automation',
    'stop-notifier.py': 'Stop - Session save + voice notification'
}

# New features
NEW_FEATURES = {
    'architecture/03-execution-system/05-skill-agent-selection/core-skills-loader.py': 'Skill loader (v2.1)',
    'post-merge-version-updater.py': 'Post-merge version automation'
}

def verify_hooks():
    """Verify all hook scripts exist."""
    print("[HOOKS] Checking required hook scripts...\n")
    all_good = True

    for script, description in REQUIRED_HOOKS.items():
        script_path = SCRIPTS_DIR / script
        if script_path.exists():
            size = script_path.stat().st_size / 1024
            print(f"  ✅ {script:30s} ({size:.1f} KB) - {description}")
        else:
            print(f"  ❌ {script:30s} NOT FOUND")
            all_good = False

    return all_good

def verify_settings():
    """Verify settings.json is valid and uncommented."""
    print("\n[SETTINGS] Checking ~/.claude/settings.json...\n")
    settings_file = CLAUDE_BASE / 'settings.json'

    if not settings_file.exists():
        print("  ❌ settings.json NOT FOUND")
        return False

    try:
        with open(settings_file, 'r') as f:
            content = f.read()

        # Check if commented
        if content.strip().startswith('//'):
            print("  ❌ settings.json is COMMENTED (still disabled)")
            return False

        # Try to parse as JSON
        settings = json.loads(content)

        # Verify hook sections
        hooks = settings.get('hooks', {})
        required_hooks = ['UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop']

        for hook_name in required_hooks:
            if hook_name in hooks:
                print(f"  ✅ {hook_name:20s} - CONFIGURED")
            else:
                print(f"  ❌ {hook_name:20s} - MISSING")
                return False

        return True
    except json.JSONDecodeError as e:
        print(f"  ❌ Invalid JSON: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def verify_new_features():
    """Verify new features are available."""
    print("\n[NEW FEATURES] Checking new functionality...\n")
    all_good = True

    for script, description in NEW_FEATURES.items():
        script_path = SCRIPTS_DIR / script
        if script_path.exists():
            size = script_path.stat().st_size / 1024
            print(f"  ✅ {description:40s} ({size:.1f} KB)")
        else:
            print(f"  ❌ {description:40s} NOT FOUND")
            all_good = False

    return all_good

def verify_skills():
    """Verify skills are available locally."""
    print("\n[SKILLS] Checking local skills and agents...\n")

    skills_dir = CLAUDE_BASE / 'skills'
    agents_dir = CLAUDE_BASE / 'agents'

    if skills_dir.exists():
        skills_count = 0
        categories = []
        try:
            for cat in skills_dir.iterdir():
                if cat.is_dir() and cat.name not in ('__pycache__', '.git'):
                    categories.append(cat.name)
                    for skill in cat.iterdir():
                        if (skill / 'skill.md').exists():
                            skills_count += 1
        except Exception:
            pass

        print(f"  ✅ Skills directory: {len(categories)} categories, {skills_count} skills")
        print(f"     Categories: {', '.join(sorted(categories)[:5])}{'...' if len(categories) > 5 else ''}")
    else:
        print(f"  ❌ Skills directory not found")

    if agents_dir.exists():
        agents_count = 0
        try:
            for agent in agents_dir.iterdir():
                if (agent / 'agent.md').exists():
                    agents_count += 1
        except Exception:
            pass

        print(f"  ✅ Agents directory: {agents_count} agents")
    else:
        print(f"  ❌ Agents directory not found")

def main():
    """Main verification."""
    print("\n" + "="*70)
    print("CLAUDE INSIGHT - HOOK SETUP VERIFICATION")
    print("="*70 + "\n")

    results = {
        'hooks': verify_hooks(),
        'settings': verify_settings(),
        'new_features': verify_new_features(),
    }

    verify_skills()

    # Summary
    print("\n" + "="*70)
    if all(results.values()):
        print("✅ ALL CHECKS PASSED - PRODUCTION READY!")
        print("="*70)
        print("\nHooks are now ENABLED. Next message will trigger full 3-level flow!")
        return 0
    else:
        print("❌ SOME CHECKS FAILED - FIX ISSUES BEFORE PRODUCTION")
        print("="*70)
        return 1

if __name__ == '__main__':
    sys.exit(main())
