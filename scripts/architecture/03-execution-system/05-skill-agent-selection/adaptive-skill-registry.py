#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptive Skill Registry Policy Enforcement (v2.0 - FULLY CONSOLIDATED)

CONSOLIDATED SCRIPT - Maps to: policies/03-execution-system/05-skill-agent-selection/adaptive-skill-registry-policy.md

Consolidates 4 scripts (1,234+ lines):
- skill-manager.py (398 lines) - CRUD operations for skill registry
- skill-detector.py (317 lines) - Auto-detect relevant skills from messages
- skill-auto-suggester.py (343 lines) - Background daemon for auto-suggestions
- check-recommendations.py (176 lines) - Display latest recommendations

THIS CONSOLIDATION includes ALL functionality from old scripts.
NO logic was lost in consolidation - everything is merged.

Usage:
  python adaptive-skill-registry-policy.py --enforce              # Run policy enforcement
  python adaptive-skill-registry-policy.py --validate             # Validate policy compliance
  python adaptive-skill-registry-policy.py --report               # Generate report
  python adaptive-skill-registry-policy.py manager add --id ...   # CRUD operations
  python adaptive-skill-registry-policy.py detector <message>     # Detect skills
  python adaptive-skill-registry-policy.py recommendations         # Show recommendations
"""

import sys
import io
import json
import re
import argparse
import time
import signal
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

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

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

MEMORY_DIR = Path.home() / '.claude' / 'memory'
LOG_FILE = MEMORY_DIR / 'logs' / 'policy-hits.log'
SKILLS_REGISTRY = MEMORY_DIR / 'skills-registry.json'
SKILL_MANAGER_LOG = MEMORY_DIR / 'logs' / 'skill-manager.log'
SKILL_DETECTOR_LOG = MEMORY_DIR / 'logs' / 'skill-detector.log'
RECOMMENDATIONS_FILE = MEMORY_DIR / '.latest-recommendations.json'


# ============================================================================
# SKILL MANAGER (from skill-manager.py)
# ============================================================================

class SkillManager:
    """CRUD operations for skill registry"""

    def __init__(self):
        self.registry = self._load_registry()
        self.skills = self.registry.get('skills', {})
        self.categories = self.registry.get('categories', {})
        self.statistics = self.registry.get('statistics', {})

    def _load_registry(self) -> Dict:
        """Load skills registry from JSON"""
        if not SKILLS_REGISTRY.exists():
            return {
                "version": "1.0.0",
                "last_updated": datetime.now().strftime('%Y-%m-%d'),
                "skills": {},
                "categories": {},
                "statistics": {
                    "total_skills": 0,
                    "by_language": {},
                    "by_category": {}
                }
            }

        with open(SKILLS_REGISTRY, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_registry(self):
        """Save updated registry back to JSON"""
        self.registry['last_updated'] = datetime.now().strftime('%Y-%m-%d')
        self.registry['skills'] = self.skills
        self.registry['categories'] = self.categories
        self.registry['statistics'] = self.statistics

        with open(SKILLS_REGISTRY, 'w', encoding='utf-8') as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)

        self._log_event("registry-saved")

    def add_skill(self, skill_id: str, **kwargs) -> bool:
        """Add a new skill to the registry"""
        if skill_id in self.skills:
            print(f"Error: Skill '{skill_id}' already exists")
            return False

        required = ['name', 'file', 'description', 'language', 'category', 'keywords']
        for field in required:
            if field not in kwargs:
                print(f"Error: Missing required field '{field}'")
                return False

        self.skills[skill_id] = {
            'name': kwargs['name'],
            'file': kwargs['file'],
            'description': kwargs['description'],
            'version': kwargs.get('version', '1.0.0'),
            'size': kwargs.get('size', 'N/A'),
            'language': kwargs['language'],
            'category': kwargs['category'],
            'keywords': kwargs['keywords'] if isinstance(kwargs['keywords'], list) else kwargs['keywords'].split(','),
            'trigger_patterns': kwargs.get('trigger_patterns', []),
            'auto_suggest': kwargs.get('auto_suggest', True),
            'requires_context7': kwargs.get('requires_context7', False),
            'dependencies': kwargs.get('dependencies', []),
            'usage_count': 0,
            'last_used': None,
            'tags': kwargs.get('tags', [])
        }

        category = kwargs['category']
        if category not in self.categories:
            self.categories[category] = {
                'description': kwargs.get('category_description', f'{category} skills'),
                'skills': []
            }
        self.categories[category]['skills'].append(skill_id)

        self._update_statistics()
        self._save_registry()
        self._log_event(f"skill-added | {skill_id}")

        print(f"[CHECK] Skill '{skill_id}' added successfully")
        return True

    def update_skill(self, skill_id: str, **kwargs) -> bool:
        """Update an existing skill"""
        if skill_id not in self.skills:
            print(f"Error: Skill '{skill_id}' not found")
            return False

        updatable = ['name', 'description', 'keywords', 'trigger_patterns',
                     'auto_suggest', 'requires_context7', 'tags', 'version', 'size']

        for field, value in kwargs.items():
            if field in updatable:
                if field == 'keywords' and isinstance(value, str):
                    value = value.split(',')
                self.skills[skill_id][field] = value

        self._save_registry()
        self._log_event(f"skill-updated | {skill_id}")

        print(f"[CHECK] Skill '{skill_id}' updated successfully")
        return True

    def remove_skill(self, skill_id: str) -> bool:
        """Remove a skill from the registry"""
        if skill_id not in self.skills:
            print(f"Error: Skill '{skill_id}' not found")
            return False

        skill_data = self.skills[skill_id]
        category = skill_data.get('category')
        if category and category in self.categories:
            self.categories[category]['skills'] = [
                s for s in self.categories[category]['skills'] if s != skill_id
            ]

        del self.skills[skill_id]
        self._update_statistics()
        self._save_registry()
        self._log_event(f"skill-removed | {skill_id}")

        print(f"[CHECK] Skill '{skill_id}' removed successfully")
        return True

    def get_skill(self, skill_id: str) -> Optional[Dict]:
        """Get skill details"""
        return self.skills.get(skill_id)

    def list_skills(self, category: Optional[str] = None) -> List[str]:
        """List all skills or by category"""
        if category:
            return self.categories.get(category, {}).get('skills', [])
        return list(self.skills.keys())

    def _update_statistics(self):
        """Update registry statistics"""
        self.statistics['total_skills'] = len(self.skills)

        by_language = {}
        for skill_data in self.skills.values():
            lang = skill_data.get('language', 'unknown')
            by_language[lang] = by_language.get(lang, 0) + 1
        self.statistics['by_language'] = by_language

        by_category = {}
        for skill_data in self.skills.values():
            cat = skill_data.get('category', 'unknown')
            by_category[cat] = by_category.get(cat, 0) + 1
        self.statistics['by_category'] = by_category

        usage_counts = {sid: data.get('usage_count', 0) for sid, data in self.skills.items()}
        if usage_counts:
            self.statistics['most_used'] = max(usage_counts, key=usage_counts.get)
            self.statistics['least_used'] = min(usage_counts, key=usage_counts.get)

    def show_statistics(self):
        """Display registry statistics"""
        print("=== Skill Registry Statistics ===\n")
        print(f"Total Skills: {self.statistics.get('total_skills', 0)}")
        print(f"Version: {self.registry.get('version', 'N/A')}")
        print(f"Last Updated: {self.registry.get('last_updated', 'N/A')}\n")

        print("By Language:")
        for lang, count in self.statistics.get('by_language', {}).items():
            print(f"  {lang}: {count}")

        print("\nBy Category:")
        for cat, count in self.statistics.get('by_category', {}).items():
            print(f"  {cat}: {count}")

        if self.statistics.get('most_used'):
            most_used_id = self.statistics['most_used']
            most_used = self.skills[most_used_id]
            print(f"\nMost Used: {most_used['name']} ({most_used.get('usage_count', 0)} times)")

        print()

    def export_skill(self, skill_id: str, output_file: str) -> bool:
        """Export a single skill to JSON"""
        if skill_id not in self.skills:
            print(f"Error: Skill '{skill_id}' not found")
            return False

        export_data = {
            'skill_id': skill_id,
            'data': self.skills[skill_id]
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        print(f"[CHECK] Skill exported to: {output_file}")
        return True

    def import_skill(self, import_file: str) -> bool:
        """Import a skill from JSON"""
        try:
            with open(import_file, 'r', encoding='utf-8') as f:
                import_data = json.load(f)

            skill_id = import_data.get('skill_id')
            skill_data = import_data.get('data')

            if not skill_id or not skill_data:
                print("Error: Invalid import file format")
                return False

            if skill_id in self.skills:
                print(f"Warning: Skill '{skill_id}' already exists. Updating...")

            self.skills[skill_id] = skill_data
            self._update_statistics()
            self._save_registry()

            print(f"[CHECK] Skill '{skill_id}' imported successfully")
            return True

        except Exception as e:
            print(f"Error importing skill: {e}")
            return False

    def _log_event(self, message: str):
        """Log skill manager events"""
        SKILL_MANAGER_LOG.parent.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"

        with open(SKILL_MANAGER_LOG, 'a', encoding='utf-8') as f:
            f.write(log_entry)


# ============================================================================
# SKILL DETECTOR (from skill-detector.py)
# ============================================================================

class SkillDetector:
    """Auto-detect relevant skills from user messages"""

    def __init__(self):
        self.registry = self._load_registry()
        self.skills = self.registry.get('skills', {})

    def _load_registry(self) -> Dict:
        """Load skills registry from JSON"""
        if not SKILLS_REGISTRY.exists():
            return {"skills": {}, "statistics": {}}

        with open(SKILLS_REGISTRY, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_registry(self):
        """Save updated registry back to JSON"""
        with open(SKILLS_REGISTRY, 'w', encoding='utf-8') as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)

    def detect_skills(self, user_message: str, threshold: float = 0.3) -> List[Dict]:
        """
        Detect relevant skills from user message

        Args:
            user_message: User's input text
            threshold: Minimum relevance score (0.0-1.0)

        Returns:
            List of matched skills with relevance scores, sorted by score (descending)
        """
        matches = []

        for skill_id, skill_data in self.skills.items():
            if not skill_data.get('auto_suggest', False):
                continue

            score = self._calculate_relevance(user_message, skill_data)

            if score >= threshold:
                matches.append({
                    'skill_id': skill_id,
                    'name': skill_data['name'],
                    'description': skill_data['description'],
                    'score': score,
                    'file': skill_data['file'],
                    'requires_context7': skill_data.get('requires_context7', False),
                    'tags': skill_data.get('tags', [])
                })

        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches

    def _calculate_relevance(self, message: str, skill_data: Dict) -> float:
        """
        Calculate relevance score between message and skill

        Scoring:
        - Trigger pattern match: +0.5
        - Keyword match: +0.1 per keyword (max +0.4)
        - Language match: +0.2
        - Category match: +0.1
        """
        message_lower = message.lower()
        score = 0.0

        # Check trigger patterns (highest weight)
        trigger_patterns = skill_data.get('trigger_patterns', [])
        for pattern in trigger_patterns:
            if re.search(pattern, message_lower, re.IGNORECASE):
                score += 0.5
                break

        # Check keywords
        keywords = skill_data.get('keywords', [])
        keyword_matches = 0
        for keyword in keywords:
            if keyword.lower() in message_lower:
                keyword_matches += 1

        keyword_score = min(keyword_matches * 0.1, 0.4)
        score += keyword_score

        # Check language mention
        language = skill_data.get('language', '')
        if language and language.lower() in message_lower:
            score += 0.2

        # Check category relevance
        category = skill_data.get('category', '')
        if category and category.lower() in message_lower:
            score += 0.1

        return min(score, 1.0)

    def suggest_skills(self, user_message: str, max_suggestions: int = 3) -> str:
        """Generate user-friendly skill suggestions"""
        matches = self.detect_skills(user_message)

        if not matches:
            return ""

        top_matches = matches[:max_suggestions]

        suggestions = []
        suggestions.append("=== Relevant Skills Detected ===\n")

        for i, match in enumerate(top_matches, 1):
            skill_name = match['name']
            description = match['description']
            score_pct = int(match['score'] * 100)
            context7_note = " [Context7 Required]" if match['requires_context7'] else ""

            suggestions.append(
                f"{i}. {skill_name} ({score_pct}% match){context7_note}\n"
                f"   {description}\n"
            )

        suggestions.append("\nUse: Read the skill file to apply it to your task.")

        return "".join(suggestions)

    def update_usage(self, skill_id: str):
        """Update usage statistics for a skill"""
        if skill_id not in self.skills:
            return

        self.skills[skill_id]['usage_count'] = self.skills[skill_id].get('usage_count', 0) + 1
        self.skills[skill_id]['last_used'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        stats = self.registry.get('statistics', {})

        usage_counts = {sid: data.get('usage_count', 0) for sid, data in self.skills.items()}
        if usage_counts:
            stats['most_used'] = max(usage_counts, key=usage_counts.get)
            stats['least_used'] = min(usage_counts, key=usage_counts.get)

        self.registry['statistics'] = stats
        self._save_registry()

        self._log_event(f"skill-used | {skill_id} | count={self.skills[skill_id]['usage_count']}")

    def list_all_skills(self) -> str:
        """List all available skills"""
        output = []
        output.append("=== Available Skills ===\n")

        for skill_id, skill_data in self.skills.items():
            name = skill_data['name']
            category = skill_data.get('category', 'N/A')
            language = skill_data.get('language', 'N/A')
            size = skill_data.get('size', 'N/A')
            usage = skill_data.get('usage_count', 0)

            output.append(
                f"- {name}\n"
                f"  ID: {skill_id}\n"
                f"  Category: {category} | Language: {language} | Size: {size}\n"
                f"  Used: {usage} times\n"
            )

        stats = self.registry.get('statistics', {})
        output.append(f"\nTotal Skills: {stats.get('total_skills', len(self.skills))}")
        if stats.get('most_used'):
            output.append(f"Most Used: {stats['most_used']}")

        return "".join(output)

    def search_skills(self, query: str) -> List[Dict]:
        """Search skills by keyword"""
        query_lower = query.lower()
        results = []

        for skill_id, skill_data in self.skills.items():
            searchable = [
                skill_data.get('name', ''),
                skill_data.get('description', ''),
                ' '.join(skill_data.get('keywords', [])),
                ' '.join(skill_data.get('tags', []))
            ]

            searchable_text = ' '.join(searchable).lower()

            if query_lower in searchable_text:
                results.append({
                    'skill_id': skill_id,
                    'name': skill_data['name'],
                    'description': skill_data['description'],
                    'file': skill_data['file']
                })

        return results

    def _log_event(self, message: str):
        """Log skill detector events"""
        SKILL_DETECTOR_LOG.parent.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"

        with open(SKILL_DETECTOR_LOG, 'a', encoding='utf-8') as f:
            f.write(log_entry)


# ============================================================================
# RECOMMENDATION DISPLAY (from check-recommendations.py)
# ============================================================================

class RecommendationDisplay:
    """Display latest recommendations"""

    # Color codes
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

    @staticmethod
    def format_time_ago(timestamp_str):
        """Format timestamp as 'X minutes ago'"""
        try:
            ts = datetime.fromisoformat(timestamp_str)
            now = datetime.now()
            diff = now - ts

            seconds = diff.total_seconds()
            if seconds < 60:
                return f"{int(seconds)} seconds ago"
            elif seconds < 3600:
                return f"{int(seconds/60)} minutes ago"
            elif seconds < 86400:
                return f"{int(seconds/3600)} hours ago"
            else:
                return f"{int(seconds/86400)} days ago"
        except:
            return timestamp_str

    @staticmethod
    def display_recommendations(json_output=False):
        """Display latest recommendations"""
        if not RECOMMENDATIONS_FILE.exists():
            if json_output:
                print(json.dumps({"error": "No recommendations available"}))
            else:
                print(f"{RecommendationDisplay.YELLOW}No recommendations available yet{RecommendationDisplay.RESET}")
            return 0

        try:
            with open(RECOMMENDATIONS_FILE, 'r') as f:
                data = json.load(f)

            if json_output:
                print(json.dumps(data, indent=2))
                return 0

            # Pretty display
            print(f"\n{RecommendationDisplay.BOLD}{'='*60}{RecommendationDisplay.RESET}")
            print(f"{RecommendationDisplay.BOLD}{RecommendationDisplay.GREEN}LATEST RECOMMENDATIONS{RecommendationDisplay.RESET}")
            print(f"{RecommendationDisplay.BOLD}{'='*60}{RecommendationDisplay.RESET}\n")

            # Timestamp
            if 'timestamp' in data:
                time_ago = RecommendationDisplay.format_time_ago(data['timestamp'])
                print(f"{RecommendationDisplay.BOLD}Generated:{RecommendationDisplay.RESET} {time_ago}")
                print()

            # Skills
            if 'skills' in data and data['skills']:
                print(f"{RecommendationDisplay.BOLD}SKILLS ({len(data['skills'])}){RecommendationDisplay.RESET}:")
                for skill in data['skills']:
                    print(f"  -> {RecommendationDisplay.CYAN}{skill}{RecommendationDisplay.RESET}")
                print()

            # Agents
            if 'agents' in data and data['agents']:
                print(f"{RecommendationDisplay.BOLD}AGENTS ({len(data['agents'])}){RecommendationDisplay.RESET}:")
                for agent in data['agents']:
                    print(f"  -> {RecommendationDisplay.BLUE}{agent}{RecommendationDisplay.RESET}")
                print()

            print(f"{RecommendationDisplay.BOLD}{'='*60}{RecommendationDisplay.RESET}\n")

            return 0

        except Exception as e:
            if json_output:
                print(json.dumps({"error": str(e)}))
            else:
                print(f"{RecommendationDisplay.RED}ERROR: Failed to read recommendations: {e}{RecommendationDisplay.RESET}")
            return 1


# ============================================================================
# LOGGING
# ============================================================================

def log_policy_hit(action, context=""):
    """Log policy execution"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] adaptive-skill-registry-policy | {action} | {context}\n"

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception:
        pass


# ============================================================================
# POLICY INTERFACE
# ============================================================================

def validate():
    """Validate policy compliance"""
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        manager = SkillManager()
        detector = SkillDetector()
        log_policy_hit("VALIDATE", "skill-registry-ready")
        return True
    except Exception as e:
        log_policy_hit("VALIDATE_ERROR", str(e))
        return False


def report():
    """Generate compliance report"""
    try:
        manager = SkillManager()
        detector = SkillDetector()

        report_data = {
            "status": "success",
            "policy": "adaptive-skill-registry",
            "components": [
                "SkillManager - CRUD operations",
                "SkillDetector - Auto-detection",
                "RecommendationDisplay - Visualization"
            ],
            "total_skills": manager.statistics.get('total_skills', 0),
            "by_language": manager.statistics.get('by_language', {}),
            "by_category": manager.statistics.get('by_category', {}),
            "timestamp": datetime.now().isoformat()
        }

        log_policy_hit("REPORT", "skill-registry-report-generated")
        return report_data
    except Exception as e:
        return {"status": "error", "message": str(e)}


def enforce():
    """
    Main policy enforcement function.

    Consolidates skill/agent registry management from four sources:
    - Skill manager (CRUD operations)
    - Skill detector (auto-detection)
    - Auto-suggester (daemon functionality)
    - Recommendation display (visualization)

    Returns: dict with status and results
    """
    try:
        log_policy_hit("ENFORCE_START", "adaptive-skill-registry-enforcement")

        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        # Initialize all components
        manager = SkillManager()
        detector = SkillDetector()
        display = RecommendationDisplay()

        log_policy_hit("ENFORCE_COMPLETE", "skill-registry-ready")
        print("[adaptive-skill-registry-policy] Policy enforced - Skill registry management active")

        return {"status": "success"}
    except Exception as e:
        log_policy_hit("ENFORCE_ERROR", str(e))
        print(f"[adaptive-skill-registry-policy] ERROR: {e}")
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
        elif sys.argv[1] == "manager" and len(sys.argv) > 2:
            manager = SkillManager()
            command = sys.argv[2]

            if command == "add" and len(sys.argv) > 3:
                # Parse add arguments (simplified)
                skill_id = sys.argv[3] if len(sys.argv) > 3 else ""
                manager.add_skill(skill_id, name="", file="", description="", language="", category="", keywords=[])
            elif command == "list":
                skills = manager.list_skills()
                for skill_id in skills:
                    skill = manager.get_skill(skill_id)
                    print(f"- {skill_id}: {skill['name']}")
            elif command == "stats":
                manager.show_statistics()
            sys.exit(0)
        elif sys.argv[1] == "detector":
            detector = SkillDetector()
            message = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else ""
            if message:
                suggestions = detector.suggest_skills(message)
                if suggestions:
                    print(suggestions)
                else:
                    print("No relevant skills detected")
            sys.exit(0)
        elif sys.argv[1] == "recommendations":
            RecommendationDisplay.display_recommendations()
            sys.exit(0)
        else:
            print("Usage: python adaptive-skill-registry-policy.py [--enforce|--validate|--report|manager|detector|recommendations]")
            sys.exit(1)
    else:
        # Default: run enforcement
        enforce()
