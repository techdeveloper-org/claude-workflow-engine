#!/usr/bin/env python3
"""
Cross-Project Pattern Detection System
Analyzes work across all projects to detect common patterns.

Detects:
- Technology stack patterns (languages, frameworks, databases)
- Architecture patterns (REST, auth methods, error handling)
- Workflow patterns (testing, git, documentation)
- Code structure patterns (folder structure, naming conventions)

Usage:
  python detect-patterns.py                    # Analyze all projects
  python detect-patterns.py --show             # Show detected patterns
  python detect-patterns.py --suggest <topic>  # Get pattern suggestions

Examples:
  python detect-patterns.py
  python detect-patterns.py --show
  python detect-patterns.py --suggest authentication
"""

# Fix encoding for Windows console
import sys
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


import json
import os
import sys
import io
import re
from datetime import datetime
from pathlib import Path
from collections import defaultdict, Counter

# Fix Windows console encoding

SESSIONS_DIR = Path.home() / ".claude" / "memory" / "sessions"
PATTERNS_FILE = Path.home() / ".claude" / "memory" / "cross-project-patterns.json"
LOG_FILE = Path.home() / ".claude" / "memory" / "logs" / "policy-hits.log"

# Pattern keywords to detect
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


def log_action(action, context):
    """Log pattern detection action."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] pattern-detection | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def load_patterns():
    """Load existing patterns from file."""
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
    """Save patterns to file."""
    patterns_data['metadata']['last_analysis'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    with open(PATTERNS_FILE, 'w', encoding='utf-8') as f:
        json.dump(patterns_data, f, indent=2)


def get_project_sessions(project_dir):
    """Get all session content for a project."""
    content = []

    # Read project summary
    summary_file = project_dir / 'project-summary.md'
    if summary_file.exists():
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                content.append(f.read().lower())
        except:
            pass

    # Read recent session files
    for session_file in project_dir.glob('session-*.md'):
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                content.append(f.read().lower())
        except:
            pass

    return ' '.join(content)


def detect_keywords_in_content(content, keywords_dict):
    """Detect which keywords appear in content."""
    detected = {}

    for category, keywords in keywords_dict.items():
        if isinstance(keywords, dict):
            # Nested category (e.g., languages -> python)
            for subcategory, keyword_list in keywords.items():
                for keyword in keyword_list:
                    if keyword.lower() in content:
                        detected[subcategory] = detected.get(subcategory, 0) + 1
        else:
            # Flat category
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

    # Collect data from all projects
    project_data = {}

    for project_dir in projects:
        project_name = project_dir.name
        content = get_project_sessions(project_dir)

        if not content or len(content) < 100:
            continue  # Skip projects with no meaningful content

        project_data[project_name] = {
            'content': content,
            'patterns': {}
        }

        # Detect patterns in each category
        for category, keywords in PATTERN_KEYWORDS.items():
            detected = detect_keywords_in_content(content, {category: keywords})
            if detected:
                project_data[project_name]['patterns'][category] = detected

    print(f"[CHECK] Analyzed {len(project_data)} projects with content")
    print()

    # Aggregate patterns across projects
    pattern_counts = defaultdict(lambda: {'projects': set(), 'count': 0})

    for project_name, data in project_data.items():
        for category, detected_items in data['patterns'].items():
            for item, count in detected_items.items():
                key = f"{category}:{item}"
                pattern_counts[key]['projects'].add(project_name)
                pattern_counts[key]['count'] += count

    # Identify patterns (appear in 3+ projects)
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
            print(f"   Projects: {', '.join(sorted(list(data['projects'])))}")
            print()

    # Update patterns file
    patterns_data['patterns'] = new_patterns
    patterns_data['metadata']['total_patterns_detected'] = len(new_patterns)
    patterns_data['metadata']['projects_analyzed'] = len(project_data)
    save_patterns(patterns_data)

    log_action('analyzed', f'{len(project_data)} projects | {len(new_patterns)} patterns detected')

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
        print("   python detect-patterns.py")
        return

    print("[TARGET] Cross-Project Patterns Detected")
    print("=" * 70)

    # Group by category
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


def suggest_patterns(topic):
    """Suggest patterns related to a topic."""
    patterns_data = load_patterns()

    if not patterns_data['patterns']:
        print("[U+1F4ED] No patterns detected yet. Run analysis first:")
        print("   python detect-patterns.py")
        return

    # Find matching patterns
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
        print(f"  Suggestion: Based on your {pattern['occurrences']} projects, "
              f"you consistently use {pattern['name']}")


def main():
    """Entry point for the CLI.

    Parses command-line arguments and executes the corresponding action.
    Prints results to stdout in JSON or text format as appropriate.
    """
    if '--show' in sys.argv:
        show_patterns()
    elif '--suggest' in sys.argv:
        if len(sys.argv) < 3:
            print("Usage: python detect-patterns.py --suggest <topic>")
            print("Example: python detect-patterns.py --suggest authentication")
            sys.exit(1)
        topic = sys.argv[2]
        suggest_patterns(topic)
    else:
        analyze_projects()


if __name__ == "__main__":
    main()
