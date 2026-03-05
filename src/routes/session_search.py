"""
Session ID Search Routes for Claude Insight Dashboard.

Provides Flask Blueprint routes to search for Claude Code sessions by ID,
list recent sessions, and filter sessions by date. Backed by
SessionSearchService which reads session JSON files and the sessions log.

Routes:
    GET /session-search          - Session search UI page
    GET /api/session/search      - Search by session ID (query: session_id)
    GET /api/session/list        - List recent sessions (query: limit)
    GET /api/session/search-by-date  - Filter by date (query: date YYYYMMDD)
"""

from flask import Blueprint, request, jsonify, render_template
from pathlib import Path
import json
from datetime import datetime
import sys

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.path_resolver import get_sessions_dir, get_logs_dir

session_search_bp = Blueprint('session_search', __name__)


class SessionSearchService:
    """Service for searching and retrieving Claude Code session data.

    Reads session JSON files from the sessions directory and the sessions
    log file to support ID-based lookup, recent session listing, and
    date-based filtering.

    Attributes:
        sessions_dir (Path): Directory containing SESSION-*.json files.
        sessions_log (Path): Path to the sessions.log event log file.
    """

    def __init__(self):
        """Initialize SessionSearchService with resolved directory paths."""
        self.sessions_dir = get_sessions_dir()
        self.sessions_log = get_logs_dir() / 'sessions.log'

    def search_session(self, session_id):
        """Search for a session by its unique identifier.

        Loads the session JSON file matching session_id, retrieves associated
        log events, and calculates session statistics (duration, work items).

        Args:
            session_id (str): The session identifier string
                (e.g. 'SESSION-20260305-143022-abcd').

        Returns:
            dict or None: On success, a dict with keys:
                session_data (dict): Parsed session JSON content.
                events (list[dict]): Log events for this session.
                stats (dict): Calculated statistics (duration, completion rate).
                found (bool): True.
            Returns ``{'error': ..., 'found': False}`` if the file cannot be
            read. Returns None if the session file does not exist.
        """
        session_file = self.sessions_dir / f'{session_id}.json'

        if not session_file.exists():
            return None

        try:
            with open(session_file, 'r') as f:
                session_data = json.load(f)

            # Get session events from log
            events = self._get_session_events(session_id)

            # Calculate statistics
            stats = self._calculate_stats(session_data)

            return {
                'session_data': session_data,
                'events': events,
                'stats': stats,
                'found': True
            }
        except Exception as e:
            return {
                'error': str(e),
                'found': False
            }

    def list_recent_sessions(self, limit=50):
        """List the most recently modified session files.

        Scans the sessions directory for SESSION-*.json files, sorts them by
        modification time (newest first), and returns summary records.

        Args:
            limit (int): Maximum number of sessions to return. Defaults to 50.

        Returns:
            list[dict]: Session summary records with keys:
                session_id (str), start_time (str), status (str),
                description (str), work_items_count (int).
            Files that cannot be parsed are silently skipped.
        """
        if not self.sessions_dir.exists():
            return []

        session_files = sorted(
            self.sessions_dir.glob('SESSION-*.json'),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        sessions = []
        for session_file in session_files[:limit]:
            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)
                    sessions.append({
                        'session_id': data['session_id'],
                        'start_time': data['start_time'],
                        'status': data['status'],
                        'description': data.get('description', ''),
                        'work_items_count': len(data.get('work_items', []))
                    })
            except:
                continue

        return sessions

    def search_by_date(self, date_str):
        """Search for sessions created on a specific date.

        Filters session files using a glob pattern that matches the date prefix
        in the filename (SESSION-YYYYMMDD-*.json).

        Args:
            date_str (str): Date string in YYYYMMDD format (e.g. '20260305').

        Returns:
            list[dict]: Parsed session data dicts for all matching files,
                sorted by modification time (newest first). Files that cannot
                be parsed are silently skipped.
        """
        if not self.sessions_dir.exists():
            return []

        pattern = f'SESSION-{date_str}-*.json'
        session_files = sorted(
            self.sessions_dir.glob(pattern),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        sessions = []
        for session_file in session_files:
            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)
                    sessions.append(data)
            except:
                continue

        return sessions

    def _get_session_events(self, session_id):
        """Retrieve all log events for a specific session from the sessions log.

        Reads sessions.log line by line and filters entries that contain the
        given session_id. Parses pipe-delimited lines into structured dicts.

        Args:
            session_id (str): Session identifier to filter log entries by.

        Returns:
            list[dict]: Event records with keys:
                timestamp (str), session_id (str), event_type (str),
                details (str). Returns an empty list if the log does not
                exist or cannot be read.
        """
        if not self.sessions_log.exists():
            return []

        events = []
        try:
            with open(self.sessions_log, 'r') as f:
                for line in f:
                    if session_id in line:
                        parts = line.strip().split(' | ')
                        if len(parts) >= 4:
                            events.append({
                                'timestamp': parts[0],
                                'session_id': parts[1],
                                'event_type': parts[2],
                                'details': parts[3] if len(parts) > 3 else ''
                            })
        except:
            pass

        return events

    def _calculate_stats(self, session_data):
        """Calculate derived statistics from a session data dictionary.

        Computes session duration, work item totals, and completion rate
        from the parsed session JSON.

        Args:
            session_data (dict): Parsed session JSON containing at minimum:
                start_time (str): ISO 8601 start timestamp.
                end_time (str or None): ISO 8601 end timestamp (optional).
                work_items (list[dict]): Work item records with 'status' keys.

        Returns:
            dict: Statistics with keys:
                duration_seconds (float): Total session duration in seconds.
                duration_formatted (str): Human-readable duration ('H:MM:SS').
                total_work_items (int): Total number of work items.
                completed_work_items (int): Count of COMPLETED items.
                in_progress_work_items (int): Count of IN_PROGRESS items.
                completion_rate (float): Percentage of completed items (0-100).
        """
        start_time = datetime.fromisoformat(session_data['start_time'])
        end_time = datetime.fromisoformat(session_data['end_time']) if session_data.get('end_time') else datetime.now()

        duration = end_time - start_time

        work_items = session_data.get('work_items', [])
        completed = [w for w in work_items if w.get('status') == 'COMPLETED']
        in_progress = [w for w in work_items if w.get('status') == 'IN_PROGRESS']

        return {
            'duration_seconds': duration.total_seconds(),
            'duration_formatted': str(duration).split('.')[0],
            'total_work_items': len(work_items),
            'completed_work_items': len(completed),
            'in_progress_work_items': len(in_progress),
            'completion_rate': (len(completed) / len(work_items) * 100) if work_items else 0
        }

# Initialize service
session_search_service = SessionSearchService()

# Routes
@session_search_bp.route('/session-search')
def session_search_page():
    """Session search page"""
    return render_template('session_search.html')

@session_search_bp.route('/api/session/search', methods=['GET'])
def search_session():
    """
    Search for a session by ID
    ---
    parameters:
      - name: session_id
        in: query
        type: string
        required: true
        description: Session ID to search for
    responses:
      200:
        description: Session found
      404:
        description: Session not found
    """
    session_id = request.args.get('session_id', '').strip()

    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400

    result = session_search_service.search_session(session_id)

    if not result or not result.get('found'):
        return jsonify({
            'found': False,
            'error': result.get('error', 'Session not found')
        }), 404

    return jsonify(result), 200

@session_search_bp.route('/api/session/list', methods=['GET'])
def list_sessions():
    """
    List recent sessions
    ---
    parameters:
      - name: limit
        in: query
        type: integer
        default: 50
        description: Number of sessions to return
    responses:
      200:
        description: List of sessions
    """
    limit = int(request.args.get('limit', 50))
    sessions = session_search_service.list_recent_sessions(limit)

    return jsonify({
        'sessions': sessions,
        'count': len(sessions)
    }), 200

@session_search_bp.route('/api/session/search-by-date', methods=['GET'])
def search_by_date():
    """
    Search sessions by date
    ---
    parameters:
      - name: date
        in: query
        type: string
        required: true
        description: Date in YYYYMMDD format
    responses:
      200:
        description: Sessions found for date
    """
    date_str = request.args.get('date', '').strip()

    if not date_str or len(date_str) != 8:
        return jsonify({'error': 'Date must be in YYYYMMDD format'}), 400

    sessions = session_search_service.search_by_date(date_str)

    return jsonify({
        'sessions': sessions,
        'count': len(sessions),
        'date': date_str
    }), 200
