#!/usr/bin/env python3
"""
Failure Solution Learner
Learns solutions from successful fixes and updates KB
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


import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

class FailureSolutionLearner:
    """Learns solutions to failure patterns from successful recoveries.

    Tracks how failures are resolved and builds a knowledge base of effective
    recovery strategies. Recommends solutions based on past successful outcomes.

    Attributes:
        memory_dir (Path): Base memory directory for session storage.
        solutions_kb (dict): Knowledge base of failure solutions.
    """
    def __init__(self):
        """Initialize the FailureSolutionLearner.

        Sets up paths for the knowledge base and learning log files.
        Creates log directory if it does not exist.
        """
        self.memory_dir = Path.home() / '.claude' / 'memory'
        self.kb_file = self.memory_dir / 'failure-kb.json'
        self.learning_log = self.memory_dir / 'logs' / 'solution-learning.log'

        # Ensure log directory exists
        self.learning_log.parent.mkdir(parents=True, exist_ok=True)

    def load_kb(self):
        """Load the failure solution knowledge base from disk.

        Returns:
            dict: Knowledge base dictionary, or empty dict if file doesn't exist.
        """
        if not self.kb_file.exists():
            return {}

        try:
            return json.loads(self.kb_file.read_text())
        except:
            return {}

    def save_kb(self, kb):
        """Save knowledge base"""
        self.kb_file.write_text(json.dumps(kb, indent=2))

    def log_learning(self, event_type, details):
        """Log learning event"""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {event_type} | {details}\n"

        with open(self.learning_log, 'a', encoding='utf-8') as f:
            f.write(log_entry)

    def learn_solution(self, tool, failure_type, solution, confidence=0.8):
        """Learn a solution for a failure type"""
        kb = self.load_kb()

        # Ensure tool exists in KB
        if tool not in kb:
            kb[tool] = []

        # Check if pattern already exists
        pattern_id = f"{tool.lower()}_{failure_type.lower()}"
        existing = None
        for i, pattern in enumerate(kb[tool]):
            if pattern['pattern_id'] == pattern_id:
                existing = i
                break

        if existing is not None:
            # Update existing pattern
            kb[tool][existing]['solution'] = solution
            kb[tool][existing]['confidence'] = min(1.0, kb[tool][existing]['confidence'] + 0.1)
            kb[tool][existing]['frequency'] = kb[tool][existing].get('frequency', 0) + 1

            self.log_learning('SOLUTION_UPDATED', f"{pattern_id} | confidence={kb[tool][existing]['confidence']}")
        else:
            # Add new pattern
            new_pattern = {
                'pattern_id': pattern_id,
                'failure_type': failure_type,
                'tool': tool,
                'solution': solution,
                'confidence': confidence,
                'frequency': 1,
                'learned_at': datetime.now().isoformat()
            }
            kb[tool].append(new_pattern)

            self.log_learning('SOLUTION_LEARNED', f"{pattern_id} | confidence={confidence}")

        # Save KB
        self.save_kb(kb)

        return kb

    def learn_from_fix(self, tool, failure_message, fix_applied):
        """Learn from a successful fix"""
        # Detect failure type from message
        failure_type = self._detect_failure_type(failure_message)

        if not failure_type:
            return None

        # Create solution from fix
        solution = self._create_solution_from_fix(fix_applied)

        if not solution:
            return None

        # Learn the solution
        return self.learn_solution(tool, failure_type, solution)

    def _detect_failure_type(self, message):
        """Detect failure type from message"""
        message_lower = message.lower()

        if 'command not found' in message_lower:
            return 'command_not_found'
        elif 'string to replace not found' in message_lower or 'string not found' in message_lower:
            return 'string_not_found'
        elif 'file too large' in message_lower or 'exceeds maximum' in message_lower:
            return 'file_too_large'
        elif 'no matches' in message_lower:
            return 'no_matches'
        elif 'permission denied' in message_lower:
            return 'permission_denied'
        elif 'not a git repository' in message_lower:
            return 'not_git_repository'
        else:
            return None

    def _create_solution_from_fix(self, fix):
        """Create solution structure from fix description"""
        fix_lower = fix.lower()

        if 'translate' in fix_lower or 'replace' in fix_lower:
            # Extract command mapping if possible
            return {
                'type': 'translate',
                'description': fix
            }
        elif 'strip' in fix_lower or 'remove prefix' in fix_lower:
            return {
                'type': 'strip_prefix',
                'description': fix
            }
        elif 'add offset' in fix_lower or 'add limit' in fix_lower:
            return {
                'type': 'add_params',
                'description': fix
            }
        else:
            return {
                'type': 'custom',
                'description': fix
            }

    def reinforce_solution(self, pattern_id):
        """Reinforce a solution when it's successfully applied"""
        kb = self.load_kb()

        # Find pattern
        for tool, patterns in kb.items():
            for pattern in patterns:
                if pattern['pattern_id'] == pattern_id:
                    # Increase confidence and frequency
                    pattern['frequency'] = pattern.get('frequency', 0) + 1
                    pattern['confidence'] = min(1.0, pattern['confidence'] + 0.05)

                    self.log_learning('SOLUTION_REINFORCED', f"{pattern_id} | confidence={pattern['confidence']}")

                    self.save_kb(kb)
                    return pattern

        return None

    def get_learning_stats(self):
        """Get learning statistics"""
        kb = self.load_kb()

        stats = {
            'total_patterns': 0,
            'by_tool': {},
            'by_confidence': {
                'high': 0,   # >= 0.8
                'medium': 0, # 0.5 - 0.8
                'low': 0     # < 0.5
            },
            'recently_learned': []
        }

        for tool, patterns in kb.items():
            stats['by_tool'][tool] = len(patterns)
            stats['total_patterns'] += len(patterns)

            for pattern in patterns:
                confidence = pattern.get('confidence', 0)
                if confidence >= 0.8:
                    stats['by_confidence']['high'] += 1
                elif confidence >= 0.5:
                    stats['by_confidence']['medium'] += 1
                else:
                    stats['by_confidence']['low'] += 1

                # Track recently learned
                if 'learned_at' in pattern:
                    stats['recently_learned'].append({
                        'pattern_id': pattern['pattern_id'],
                        'tool': tool,
                        'learned_at': pattern['learned_at'],
                        'confidence': confidence
                    })

        # Sort recently learned
        stats['recently_learned'].sort(key=lambda x: x['learned_at'], reverse=True)
        stats['recently_learned'] = stats['recently_learned'][:10]  # Keep top 10

        return stats

def main():
    """Entry point for the CLI.

    Parses command-line arguments and executes the corresponding action.
    Prints results to stdout in JSON or text format as appropriate.
    """
    parser = argparse.ArgumentParser(description='Failure solution learner')
    parser.add_argument('--learn', nargs=4, metavar=('TOOL', 'TYPE', 'SOLUTION', 'CONFIDENCE'),
                       help='Learn a solution')
    parser.add_argument('--learn-from-fix', nargs=3, metavar=('TOOL', 'FAILURE_MSG', 'FIX'),
                       help='Learn from a successful fix')
    parser.add_argument('--reinforce', help='Reinforce a solution by pattern ID')
    parser.add_argument('--stats', action='store_true', help='Show learning statistics')
    parser.add_argument('--test', action='store_true', help='Test learning system')

    if len(sys.argv) < 2:
        sys.exit(0)
    args = parser.parse_args()

    learner = FailureSolutionLearner()

    if args.test:
        print("Testing solution learning...")

        # Test 1: Learn a solution
        print("\n1. Learn solution for Windows command")
        solution = {
            'type': 'translate',
            'mapping': {'xcopy': 'cp -r'}
        }
        kb = learner.learn_solution('Bash', 'command_not_found', solution, 0.9)
        print(f"   [OK] Solution learned, KB has {sum(len(v) for v in kb.values())} patterns")

        # Test 2: Learn from fix
        print("\n2. Learn from successful fix")
        kb = learner.learn_from_fix(
            'Edit',
            'String to replace not found: 42->    def foo():',
            'Stripped line number prefix'
        )
        if kb:
            print(f"   [OK] Learned from fix, KB has {sum(len(v) for v in kb.values())} patterns")
        else:
            print(f"   [INFO] Fix not learned (already known or unrecognized)")

        # Test 3: Reinforce solution
        print("\n3. Reinforce existing solution")
        pattern = learner.reinforce_solution('bash_command_not_found')
        if pattern:
            print(f"   [OK] Solution reinforced, confidence={pattern['confidence']}")
        else:
            print(f"   [INFO] Pattern not found")

        # Test 4: Get stats
        print("\n4. Get learning statistics")
        stats = learner.get_learning_stats()
        print(f"   Total patterns: {stats['total_patterns']}")
        print(f"   High confidence: {stats['by_confidence']['high']}")
        print(f"   Recently learned: {len(stats['recently_learned'])}")

        print("\n[OK] All tests completed!")
        return 0

    if args.learn:
        tool, failure_type, solution_json, confidence = args.learn
        try:
            solution = json.loads(solution_json)
            confidence = float(confidence)
        except:
            print("ERROR: Invalid solution JSON or confidence", file=sys.stderr)
            return 1

        kb = learner.learn_solution(tool, failure_type, solution, confidence)
        print(f"Solution learned. KB now has {sum(len(v) for v in kb.values())} patterns")
        return 0

    if args.learn_from_fix:
        tool, failure_msg, fix = args.learn_from_fix
        kb = learner.learn_from_fix(tool, failure_msg, fix)

        if kb:
            print(f"Solution learned from fix. KB now has {sum(len(v) for v in kb.values())} patterns")
        else:
            print("Could not learn from fix (unrecognized pattern)")

        return 0

    if args.reinforce:
        pattern = learner.reinforce_solution(args.reinforce)
        if pattern:
            print(f"Solution reinforced: {pattern['pattern_id']}")
            print(f"New confidence: {pattern['confidence']}")
            print(f"Frequency: {pattern['frequency']}")
        else:
            print(f"Pattern not found: {args.reinforce}")

        return 0

    if args.stats:
        stats = learner.get_learning_stats()
        print(json.dumps(stats, indent=2))
        return 0

    parser.print_help()
    return 1

if __name__ == '__main__':
    sys.exit(main())
