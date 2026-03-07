#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-Project Pattern Detection Policy Enforcement (v2.0 - FULLY CONSOLIDATED)

CONSOLIDATED SCRIPT - Maps to: policies/01-sync-system/pattern-detection/cross-project-patterns-policy.md

Consolidates 2 scripts (555+ lines):
- detect-patterns.py (374 lines) - Analyze and detect cross-project patterns
- apply-patterns.py (181 lines) - Apply/suggest patterns for topics

THIS CONSOLIDATION includes ALL functionality from old scripts.
NO logic was lost in consolidation - everything is merged.

Usage:
  python cross-project-patterns-policy.py --enforce            # Run policy enforcement
  python cross-project-patterns-policy.py --validate           # Validate policy compliance
  python cross-project-patterns-policy.py --report             # Generate report
  python cross-project-patterns-policy.py --analyze            # Analyze all projects
  python cross-project-patterns-policy.py --show               # Show detected patterns
  python cross-project-patterns-policy.py --suggest <topic>    # Get pattern suggestions
  python cross-project-patterns-policy.py --apply <topic>      # Apply relevant patterns
"""

import sys
import io
import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

# Fix encoding for Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

MEMORY_DIR = Path.home() / ".claude" / "memory"
SESSIONS_DIR = MEMORY_DIR / "sessions"
PATTERNS_FILE = MEMORY_DIR / "cross-project-patterns.json"
LOG_FILE = MEMORY_DIR / "logs" / "policy-hits.log"

# Pattern keywords (from detect-patterns.py)
PATTERN_KEYWORDS = {
    'languages': {
        'python': ['python', 'py', 'django', 'flask', 'fastapi', 'pytest'],
        'javascript': ['javascript', 'js', 'node', 'nodejs', 'npm', 'express'],
        'typescript': ['typescript', 'ts', 'tsx'],
        'java': ['java', 'spring', 'spring boot', 'maven', 'gradle'],
        'go': ['golang', 'go ', 'gin', 'fiber'],
        'rust': ['rust', 'cargo'],
        'kotlin': ['kotlin', 'ktor'],
        'swift': ['swift', 'swiftui', 'uikit']
    },
    'frontend': {
        'react': ['react', 'jsx', 'react native', 'nextjs', 'next.js'],
        'angular': ['angular', 'ng', '@angular'],
        'vue': ['vue', 'vuejs', 'vue.js', 'nuxt'],
        'svelte': ['svelte', 'sveltekit']
    },
    'databases': {
        'postgresql': ['postgresql', 'postgres', 'pg', 'psql'],
        'mysql': ['mysql', 'mariadb'],
        'mongodb': ['mongodb', 'mongo', 'mongoose'],
        'redis': ['redis', 'cache'],
        'sqlite': ['sqlite', 'sqlite3'],
        'elasticsearch': ['elasticsearch', 'elastic']
    },
    'authentication': {
        'jwt': ['jwt', 'json web token', 'token', 'bearer'],
        'oauth': ['oauth', 'oauth2', 'oauth 2.0'],
        'session': ['session', 'cookie', 'session-based'],
        'basic': ['basic auth', 'basic authentication']
    },
    'api_style': {
        'rest': ['rest', 'restful', 'rest api', 'rest endpoint'],
        'graphql': ['graphql', 'gql', 'apollo'],
        'grpc': ['grpc', 'protobuf', 'protocol buffer']
    },
    'testing': {
        'unit': ['unit test', 'unittest', 'jest', 'pytest', 'mocha'],
        'integration': ['integration test', 'e2e', 'end-to-end'],
        'tdd': ['tdd', 'test-driven', 'test driven']
    },
    'containerization': {
        'docker': ['docker', 'dockerfile', 'container', 'containerize'],
        'kubernetes': ['kubernetes', 'k8s', 'kubectl', 'helm']
    },
    'ci_cd': {
        'github_actions': ['github actions', 'gh actions', '.github/workflows'],
        'jenkins': ['jenkins', 'jenkinsfile'],
        'gitlab_ci': ['gitlab ci', '.gitlab-ci.yml']
    }
}


# ============================================================================
# PATTERN DETECTION & ANALYSIS (from detect-patterns.py)
# ============================================================================

def load_patterns():
    """Load the cross-project patterns data from disk.

    Returns:
        dict: Contains 'patterns' list and 'metadata' dict.
              Returns a default empty structure if the file does not exist
              or cannot be parsed.
    """
    if not PATTERNS_FILE.exists():
        return {"patterns": [], "metadata": {
            "last_analysis": None,
            "total_patterns_detected": 0,
            "projects_analyzed": 0,
            "detection_threshold": 3,
            "confidence_threshold": 0.6
        }}

    try:
        with open(PATTERNS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"patterns": [], "metadata": {}}


def save_patterns(patterns_data):
    """Persist the patterns data dict to disk, updating last_analysis timestamp.

    Args:
        patterns_data (dict): Patterns data with 'patterns' list and 'metadata' dict.
    """
    patterns_data['metadata']['last_analysis'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PATTERNS_FILE, 'w', encoding='utf-8') as f:
        json.dump(patterns_data, f, indent=2)


def get_project_sessions(project_dir):
    """Read and concatenate all session text for a single project directory.

    Args:
        project_dir (Path): Directory containing the project's session files.

    Returns:
        str: Lowercased combined text from project-summary.md and all
             session-*.md files. Empty string if no readable content.
    """
    content = []

    summary_file = project_dir / 'project-summary.md'
    if summary_file.exists():
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                content.append(f.read().lower())
        except:
            pass

    for session_file in project_dir.glob('session-*.md'):
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                content.append(f.read().lower())
        except:
            pass

    return ' '.join(content)


def detect_keywords_in_content(content, keywords_dict):
    """Count how many times each keyword subcategory appears in content.

    Args:
        content (str): Text to search (should be lowercased).
        keywords_dict (dict): Mapping of category to keyword list or
                              subcategory -> keyword list.

    Returns:
        dict: Mapping of detected item name to occurrence count.
    """
    detected = {}

    for category, keywords in keywords_dict.items():
        if isinstance(keywords, dict):
            for subcategory, keyword_list in keywords.items():
                for keyword in keyword_list:
                    if keyword.lower() in content:
                        detected[subcategory] = detected.get(subcategory, 0) + 1
        else:
            for keyword in keywords:
                if keyword.lower() in content:
                    detected[category] = detected.get(category, 0) + 1

    return detected


def analyze_projects():
    """Analyze all projects to detect patterns."""
    if not SESSIONS_DIR.exists():
        print("[CROSS] No sessions directory found")
        return

    projects = [d for d in SESSIONS_DIR.iterdir() if d.is_dir()]

    if not projects:
        print("[CROSS] No projects found")
        return

    print(f"[SEARCH] Analyzing {len(projects)} projects for patterns...")
    print()

    project_data = {}

    for project_dir in projects:
        project_name = project_dir.name
        content = get_project_sessions(project_dir)

        if not content or len(content) < 100:
            continue

        project_data[project_name] = {'content': content, 'patterns': {}}

        for category, keywords in PATTERN_KEYWORDS.items():
            detected = detect_keywords_in_content(content, {category: keywords})
            if detected:
                project_data[project_name]['patterns'][category] = detected

    print(f"[CHECK] Analyzed {len(project_data)} projects with content\n")

    pattern_counts = defaultdict(lambda: {'projects': set(), 'count': 0})

    for project_name, data in project_data.items():
        for category, detected_items in data['patterns'].items():
            for item, count in detected_items.items():
                key = f"{category}:{item}"
                pattern_counts[key]['projects'].add(project_name)
                pattern_counts[key]['count'] += count

    patterns_data = load_patterns()
    threshold = patterns_data['metadata'].get('detection_threshold', 3)
    new_patterns = []

    for key, data in pattern_counts.items():
        if len(data['projects']) >= threshold:
            category, item = key.split(':', 1)
            confidence = min(len(data['projects']) / len(project_data), 1.0)

            pattern = {
                'id': f"{category}-{item}",
                'type': category,
                'name': item,
                'confidence': round(confidence, 2),
                'projects': sorted(list(data['projects'])),
                'occurrences': len(data['projects']),
                'total_mentions': data['count'],
                'first_seen': datetime.now().strftime('%Y-%m-%d'),
                'last_seen': datetime.now().strftime('%Y-%m-%d')
            }

            new_patterns.append(pattern)

            print(f"[CHECK] Pattern detected: {item.upper()} ({category})")
            print(f"   Confidence: {confidence:.0%}")
            print(f"   Found in: {len(data['projects'])} projects")
            print(f"   Projects: {', '.join(sorted(list(data['projects'])))}\n")

    patterns_data['patterns'] = new_patterns
    patterns_data['metadata']['total_patterns_detected'] = len(new_patterns)
    patterns_data['metadata']['projects_analyzed'] = len(project_data)
    save_patterns(patterns_data)

    log_policy_hit('ANALYZED', f'{len(project_data)} projects | {len(new_patterns)} patterns')

    print("=" * 70)
    print(f"[CHART] Summary:")
    print(f"   Projects analyzed: {len(project_data)}")
    print(f"   Patterns detected: {len(new_patterns)}")
    print(f"   Detection threshold: {threshold}+ projects")


def show_patterns():
    """Display all detected patterns."""
    patterns_data = load_patterns()

    if not patterns_data['patterns']:
        print("[U+1F4ED] No patterns detected yet. Run analysis first:")
        print("   python cross-project-patterns-policy.py --analyze")
        return

    print("[TARGET] Cross-Project Patterns Detected")
    print("=" * 70)

    by_category = defaultdict(list)
    for pattern in patterns_data['patterns']:
        by_category[pattern['type']].append(pattern)

    for category, patterns in sorted(by_category.items()):
        print(f"\n[U+1F4C1] {category.upper().replace('_', ' ')}")

        for pattern in sorted(patterns, key=lambda x: x['confidence'], reverse=True):
            confidence_bar = '█' * int(pattern['confidence'] * 10)
            print(f"\n  [CHECK] {pattern['name'].upper()}")
            print(f"    Confidence: [{confidence_bar:<10}] {pattern['confidence']:.0%}")
            print(f"    Found in {pattern['occurrences']} projects: {', '.join(pattern['projects'][:3])}")
            if len(pattern['projects']) > 3:
                print(f"              ... and {len(pattern['projects']) - 3} more")

    print("\n" + "=" * 70)
    meta = patterns_data['metadata']
    print(f"[CHART] Statistics:")
    print(f"   Total patterns: {meta.get('total_patterns_detected', 0)}")
    print(f"   Projects analyzed: {meta.get('projects_analyzed', 0)}")
    print(f"   Last analysis: {meta.get('last_analysis', 'Never')}")


# ============================================================================
# PATTERN APPLICATION (from apply-patterns.py)
# ============================================================================

def find_relevant_patterns(topic):
    """Search the stored patterns for entries relevant to a given topic.

    Scores each pattern by exact match, substring match, and category
    keyword heuristics, then returns them sorted by relevance.

    Args:
        topic (str): Topic keyword to match against pattern names and types.

    Returns:
        list[dict]: Patterns sorted by descending relevance score, or None
                    if no patterns data is available.
    """
    patterns_data = load_patterns()

    if not patterns_data or not patterns_data.get('patterns'):
        return None

    topic_lower = topic.lower()
    matches = []

    for pattern in patterns_data['patterns']:
        score = 0

        if topic_lower == pattern['name'].lower():
            score += 10
        elif topic_lower in pattern['name'].lower():
            score += 5
        elif topic_lower in pattern['type'].lower():
            score += 3

        keywords = [
            'auth' if 'authentication' in pattern['type'] else '',
            'api' if 'api_style' in pattern['type'] else '',
            'lang' if 'language' in pattern['type'] else '',
            'front' if 'frontend' in pattern['type'] else '',
        ]

        for keyword in keywords:
            if keyword and keyword in topic_lower:
                score += 2

        if score > 0:
            matches.append((score, pattern))

    matches.sort(key=lambda x: (x[0], x[1]['confidence']), reverse=True)

    return [m[1] for m in matches]


def apply_patterns(topic):
    """Print pattern suggestions most relevant to a topic.

    Args:
        topic (str): The topic or technology to search for patterns about.
    """
    patterns = find_relevant_patterns(topic)

    if not patterns:
        print(f"[BULB] No established patterns found for: {topic}")
        print("\n   This might be a new approach!")
        print("   Run pattern detection after completing this work:")
        print("   python cross-project-patterns-policy.py --analyze")
        return

    print(f"[BULB] Based on your past projects, here are relevant patterns:")
    print("=" * 70)

    for i, pattern in enumerate(patterns[:5], 1):
        confidence_bar = '█' * int(pattern['confidence'] * 10)
        strength = "STRONG" if pattern['confidence'] >= 0.8 else "MODERATE" if pattern['confidence'] >= 0.6 else "WEAK"

        print(f"\n{i}. {pattern['name'].upper()} ({strength} PATTERN)")
        print(f"   Confidence: [{confidence_bar:<10}] {pattern['confidence']:.0%}")
        print(f"   Category: {pattern['type'].replace('_', ' ').title()}")
        print(f"   Used in: {pattern['occurrences']} of your projects")
        print(f"   Projects: {', '.join(pattern['projects'][:3])}")
        if len(pattern['projects']) > 3:
            print(f"            ... and {len(pattern['projects']) - 3} more")

        if pattern['type'] == 'authentication':
            print(f"\n   [BULB] Suggestion: Consider using {pattern['name']} authentication")
        elif pattern['type'] == 'api_style':
            print(f"\n   [BULB] Suggestion: Build a {pattern['name'].upper()} API")
        elif pattern['type'] == 'languages':
            print(f"\n   [BULB] Suggestion: Use {pattern['name'].title()} for implementation")
        elif pattern['type'] == 'frontend':
            print(f"\n   [BULB] Suggestion: Use {pattern['name'].title()} for the frontend")
        elif pattern['type'] == 'databases':
            print(f"\n   [BULB] Suggestion: Use {pattern['name'].title()} as database")

    print("\n" + "=" * 70)
    print("[U+1F4DD] Note: These are suggestions based on your patterns.")
    print("   You can always choose a different approach!")

    log_policy_hit('APPLIED', f'topic={topic} | {len(patterns)} patterns suggested')


def suggest_patterns(topic):
    """Print all stored patterns whose name or type contains the given topic.

    Args:
        topic (str): The topic keyword to filter patterns by.
    """
    patterns_data = load_patterns()

    if not patterns_data or not patterns_data.get('patterns'):
        print("[U+1F4ED] No patterns detected yet. Run analysis first:")
        print("   python cross-project-patterns-policy.py --analyze")
        return

    topic_lower = topic.lower()
    matches = []

    for pattern in patterns_data['patterns']:
        if (topic_lower in pattern['name'].lower() or
            topic_lower in pattern['type'].lower()):
            matches.append(pattern)

    if not matches:
        print(f"[CROSS] No patterns found related to: {topic}")
        print("\n[BULB] Try these topics:")
        categories = set(p['type'] for p in patterns_data['patterns'])
        for cat in sorted(categories):
            print(f"   - {cat}")
        return

    print(f"[BULB] Patterns related to '{topic}':")
    print("=" * 70)

    for pattern in sorted(matches, key=lambda x: x['confidence'], reverse=True):
        print(f"\n[CHECK] {pattern['name'].upper()} ({pattern['type']})")
        print(f"  Confidence: {pattern['confidence']:.0%}")
        print(f"  Used in: {', '.join(pattern['projects'])}")
        print(f"  Suggestion: Based on your {pattern['occurrences']} projects, you consistently use {pattern['name']}")


# ============================================================================
# LOGGING
# ============================================================================

def log_policy_hit(action, context=""):
    """Append a timestamped entry to the policy-hits log.

    Args:
        action (str): The action identifier (e.g., 'ENFORCE_START', 'VALIDATE').
        context (str): Optional human-readable context or detail string.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] cross-project-patterns-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


# ============================================================================
# POLICY INTERFACE
# ============================================================================

def validate():
    """Check that the cross-project patterns policy preconditions are met.

    Returns:
        bool: True if validation succeeds, False on any exception.
    """
    try:
        patterns_data = load_patterns()
        log_policy_hit("VALIDATE", f"patterns={len(patterns_data.get('patterns', []))}")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate a compliance report for the cross-project patterns policy.

    Returns:
        dict: Contains 'status', 'policy', 'total_patterns',
              'projects_analyzed', 'last_analysis', and 'timestamp'.
              Returns {'status': 'error', ...} on failure.
    """
    try:
        patterns_data = load_patterns()

        report_data = {
            "status": "success",
            "policy": "cross-project-patterns",
            "total_patterns": len(patterns_data.get('patterns', [])),
            "projects_analyzed": patterns_data.get('metadata', {}).get('projects_analyzed', 0),
            "last_analysis": patterns_data.get('metadata', {}).get('last_analysis'),
            "timestamp": datetime.now().isoformat()
        }

        log_policy_hit("REPORT", "cross-project-patterns-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """Activate the cross-project patterns policy.

    Consolidates pattern detection and application from 2 old scripts:
    - detect-patterns.py: Analyze and detect patterns
    - apply-patterns.py: Apply/suggest patterns

    Loads the existing patterns and logs the active pattern count.

    Returns:
        dict: Contains 'status' ('success' or 'error') and 'patterns' count.
              On error, contains 'message'.
    """
    try:
        log_policy_hit("ENFORCE_START", "cross-project-patterns-enforcement")

        patterns_data = load_patterns()
        pattern_count = len(patterns_data.get('patterns', []))

        log_policy_hit("ENFORCE_COMPLETE", f"cross-project-patterns-ready | count={pattern_count}")
        print(f"[cross-project-patterns-policy] {pattern_count} patterns loaded")

        return {"status": "success", "patterns": pattern_count}
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[cross-project-patterns-policy] ERROR: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--enforce":
            result = enforce()
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--validate":
            is_valid = validate()
            sys.exit(0 if is_valid else 1)
        elif sys.argv[1] == "--report":
            result = report()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("status") == "success" else 1)
        elif sys.argv[1] == "--analyze":
            analyze_projects()
        elif sys.argv[1] == "--show":
            show_patterns()
        elif sys.argv[1] == "--suggest" and len(sys.argv) >= 3:
            topic = sys.argv[2]
            suggest_patterns(topic)
        elif sys.argv[1] == "--apply" and len(sys.argv) >= 3:
            topic = ' '.join(sys.argv[2:])
            apply_patterns(topic)
        else:
            print("Usage: python cross-project-patterns-policy.py [--enforce|--validate|--report|--analyze|--show|--suggest <topic>|--apply <topic>]")
            sys.exit(1)
    else:
        # Default: run enforcement
        enforce()
