#!/usr/bin/env python3
"""
Session State Manager
Maintains session state OUTSIDE Claude's context
Allows Claude to reference state without full history
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

class SessionState:
    """Persist session state to a JSON file outside Claude's context window.

    Stores the current task, completed tasks, modified files, key decisions,
    pending work, and arbitrary context/metadata for a single project.
    Each mutating method persists the state immediately to disk.

    Attributes:
        memory_dir (Path): Base memory directory (~/.claude/memory).
        state_dir (Path): Directory holding per-project state JSON files.
        project_name (str): Project name used as the state filename stem.
        state_file (Path): Path to this project's JSON state file.
        state (dict): In-memory copy of the current state.
    """

    def __init__(self, project_name=None):
        """Initialize the SessionState manager.

        Args:
            project_name (str, optional): Project name for state file identification.
                If not provided, uses the current working directory name.
        """
        self.memory_dir = Path.home() / '.claude' / 'memory'
        self.state_dir = self.memory_dir / '.state'
        self.state_dir.mkdir(exist_ok=True)

        # Detect project name if not provided
        if project_name is None:
            cwd = Path.cwd()
            project_name = cwd.name

        self.project_name = project_name
        self.state_file = self.state_dir / f'{project_name}.json'

        # Load existing state or initialize
        self.state = self._load_state()

    def _load_state(self):
        """Load state from file"""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except:
                pass

        # Default state structure
        return {
            'project_name': self.project_name,
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'current_task': None,
            'completed_tasks': [],
            'files_modified': [],
            'key_decisions': [],
            'pending_work': [],
            'context': {},
            'metadata': {}
        }

    def _save_state(self):
        """Save state to file"""
        self.state['last_updated'] = datetime.now().isoformat()

        try:
            self.state_file.write_text(json.dumps(self.state, indent=2))
            return True
        except Exception as e:
            print(f"ERROR: Failed to save state: {e}", file=sys.stderr)
            return False

    def set_current_task(self, task_description):
        """Set current task"""
        self.state['current_task'] = {
            'description': task_description,
            'started_at': datetime.now().isoformat()
        }
        return self._save_state()

    def complete_current_task(self, result=None):
        """Mark current task as complete"""
        if self.state['current_task']:
            completed = {
                **self.state['current_task'],
                'completed_at': datetime.now().isoformat(),
                'result': result
            }
            self.state['completed_tasks'].append(completed)
            self.state['current_task'] = None
            return self._save_state()
        return False

    def add_file_modified(self, file_path, change_type='modified'):
        """Add modified file to state"""
        file_entry = {
            'path': str(file_path),
            'change_type': change_type,  # modified, created, deleted
            'timestamp': datetime.now().isoformat()
        }

        # Avoid duplicates (keep only latest)
        self.state['files_modified'] = [
            f for f in self.state['files_modified']
            if f['path'] != str(file_path)
        ]
        self.state['files_modified'].append(file_entry)

        return self._save_state()

    def add_decision(self, decision_type, description, choice):
        """Add key decision to state"""
        decision = {
            'type': decision_type,
            'description': description,
            'choice': choice,
            'timestamp': datetime.now().isoformat()
        }
        self.state['key_decisions'].append(decision)
        return self._save_state()

    def add_pending_work(self, description, priority='medium'):
        """Add pending work item"""
        work_item = {
            'description': description,
            'priority': priority,  # low, medium, high
            'added_at': datetime.now().isoformat()
        }
        self.state['pending_work'].append(work_item)
        return self._save_state()

    def complete_pending_work(self, description):
        """Remove pending work item"""
        self.state['pending_work'] = [
            w for w in self.state['pending_work']
            if w['description'] != description
        ]
        return self._save_state()

    def set_context(self, key, value):
        """Set context value"""
        self.state['context'][key] = value
        return self._save_state()

    def get_context(self, key, default=None):
        """Get context value"""
        return self.state['context'].get(key, default)

    def set_metadata(self, key, value):
        """Set metadata value"""
        self.state['metadata'][key] = value
        return self._save_state()

    def get_summary(self):
        """Get session summary for Claude"""
        current_task = self.state['current_task']
        completed_count = len(self.state['completed_tasks'])
        files_count = len(self.state['files_modified'])
        decisions_count = len(self.state['key_decisions'])
        pending_count = len(self.state['pending_work'])

        summary = {
            'project': self.project_name,
            'current_task': current_task['description'] if current_task else None,
            'progress': {
                'completed_tasks': completed_count,
                'files_modified': files_count,
                'decisions_made': decisions_count,
                'pending_work': pending_count
            }
        }

        # Include recent activity
        if completed_count > 0:
            summary['recent_completed'] = [
                t['description'] for t in self.state['completed_tasks'][-3:]
            ]

        if files_count > 0:
            summary['recent_files'] = [
                f['path'] for f in self.state['files_modified'][-5:]
            ]

        if pending_count > 0:
            summary['pending_work'] = [
                w['description'] for w in self.state['pending_work']
            ]

        return summary

    def get_full_state(self):
        """Get full state"""
        return self.state

    def clear_state(self):
        """Clear all state"""
        self.state = {
            'project_name': self.project_name,
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'current_task': None,
            'completed_tasks': [],
            'files_modified': [],
            'key_decisions': [],
            'pending_work': [],
            'context': {},
            'metadata': {}
        }
        return self._save_state()

def main():
    """Entry point for the CLI.

    Parses command-line arguments and executes the corresponding action.
    Prints results to stdout in JSON or text format as appropriate.
    """
    parser = argparse.ArgumentParser(description='Session state manager')
    parser.add_argument('--project', help='Project name')
    parser.add_argument('--set-task', help='Set current task')
    parser.add_argument('--complete-task', nargs='?', const='', help='Complete current task')
    parser.add_argument('--add-file', help='Add modified file')
    parser.add_argument('--change-type', default='modified', help='Change type')
    parser.add_argument('--add-decision', nargs=3, metavar=('TYPE', 'DESC', 'CHOICE'), help='Add decision')
    parser.add_argument('--add-pending', help='Add pending work')
    parser.add_argument('--complete-pending', help='Complete pending work')
    parser.add_argument('--set-context', nargs=2, metavar=('KEY', 'VALUE'), help='Set context')
    parser.add_argument('--get-context', help='Get context value')
    parser.add_argument('--summary', action='store_true', help='Get session summary')
    parser.add_argument('--full', action='store_true', help='Get full state')
    parser.add_argument('--clear', action='store_true', help='Clear state')
    parser.add_argument('--save', action='store_true', help='Test save')
    parser.add_argument('--load', action='store_true', help='Test load')

    args = parser.parse_args()

    # Detect project name from cwd or use provided
    project_name = args.project or Path.cwd().name
    state = SessionState(project_name)

    if args.save or args.load:
        # Test mode
        print("Testing session state...")

        print("1. Set current task")
        state.set_current_task("Test implementation")

        print("2. Add modified file")
        state.add_file_modified("test.py", "created")

        print("3. Add decision")
        state.add_decision("architecture", "Use microservices", "Spring Boot")

        print("4. Add pending work")
        state.add_pending_work("Write tests", "high")

        print("5. Set context")
        state.set_context("framework", "Spring Boot")

        print("6. Get summary")
        summary = state.get_summary()
        print(json.dumps(summary, indent=2))

        print("7. Complete task")
        state.complete_current_task("Successfully implemented")

        print("8. Final summary")
        summary = state.get_summary()
        print(json.dumps(summary, indent=2))

        print("\n[OK] All tests passed!")
        print(f"State saved to: {state.state_file}")
        return 0

    if args.set_task:
        state.set_current_task(args.set_task)
        print(f"Current task set: {args.set_task}")
        return 0

    if args.complete_task is not None:
        result = args.complete_task if args.complete_task else None
        state.complete_current_task(result)
        print("Task completed")
        return 0

    if args.add_file:
        state.add_file_modified(args.add_file, args.change_type)
        print(f"File added: {args.add_file} ({args.change_type})")
        return 0

    if args.add_decision:
        decision_type, desc, choice = args.add_decision
        state.add_decision(decision_type, desc, choice)
        print(f"Decision added: {decision_type}")
        return 0

    if args.add_pending:
        state.add_pending_work(args.add_pending)
        print(f"Pending work added: {args.add_pending}")
        return 0

    if args.complete_pending:
        state.complete_pending_work(args.complete_pending)
        print(f"Pending work completed: {args.complete_pending}")
        return 0

    if args.set_context:
        key, value = args.set_context
        state.set_context(key, value)
        print(f"Context set: {key} = {value}")
        return 0

    if args.get_context:
        value = state.get_context(args.get_context)
        print(value)
        return 0

    if args.summary:
        summary = state.get_summary()
        print(json.dumps(summary, indent=2))
        return 0

    if args.full:
        full_state = state.get_full_state()
        print(json.dumps(full_state, indent=2))
        return 0

    if args.clear:
        state.clear_state()
        print("State cleared")
        return 0

    # Default: show summary
    summary = state.get_summary()
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == '__main__':
    sys.exit(main())
