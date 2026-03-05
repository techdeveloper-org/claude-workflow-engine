"""
History Tracker for Claude Insight Dashboard.

Records and retrieves daily metric snapshots for trend analysis and historical
charting. Each day's data is stored as a single entry (upserted by date) in
a JSON file, keeping at most 90 days of history.

The tracker stores these daily metrics per entry:
  - health_score: System health percentage (0-100)
  - errors_24h: Error count in the last 24 hours
  - policy_hits: Total policy execution count
  - context_usage: Context window usage percentage
  - tokens_used: Estimated token usage
  - daemons_running / daemons_total: Hook script counts

Classes:
    HistoryTracker: Records and queries daily metric history.
"""
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add path resolver for portable paths
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.path_resolver import get_data_dir


class HistoryTracker:
    """Record and retrieve daily metric snapshots for dashboard trend charts.

    Persists metrics to ``~/.claude/memory/dashboard_history.json`` (or the
    local data directory in portable mode). Automatically deduplicates by
    date (one entry per calendar day) and caps history at 90 days.

    Attributes:
        memory_dir (Path): Root data directory resolved by PathResolver.
        history_file (Path): Path to the dashboard_history.json file.
    """

    def __init__(self):
        """Initialize HistoryTracker and ensure the history file exists."""
        self.memory_dir = get_data_dir()
        self.history_file = self.memory_dir / 'dashboard_history.json'
        self.ensure_history_file()

    def ensure_history_file(self):
        """Create the history JSON file with an empty structure if it does not exist.

        Returns:
            None
        """
        if not self.history_file.exists():
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            self.history_file.write_text(json.dumps({
                'daily_metrics': [],
                'last_updated': datetime.now().isoformat()
            }))

    def load_history(self):
        """Load the full history dictionary from the JSON file.

        Returns:
            dict: History data with keys:
                daily_metrics (list[dict]): List of daily metric entries.
                last_updated (str or None): ISO timestamp of last write.
            Returns an empty structure on read errors.
        """
        try:
            if self.history_file.exists():
                return json.loads(self.history_file.read_text())
            return {'daily_metrics': [], 'last_updated': None}
        except Exception as e:
            print(f"Error loading history: {e}")
            return {'daily_metrics': [], 'last_updated': None}

    def save_history(self, data):
        """Write the history dictionary to the JSON file.

        Args:
            data (dict): History data to persist. Should follow the structure
                returned by load_history().

        Returns:
            None
        """
        try:
            self.history_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Error saving history: {e}")

    def add_daily_metric(self, metrics):
        """Upsert a daily metric snapshot for the current calendar day.

        If an entry for today already exists it is replaced. The history is
        then trimmed to the last 90 days (sorted descending by date).

        Args:
            metrics (dict): Metric values for today. Recognised keys:
                health_score (int/float), errors_24h (int), policy_hits (int),
                context_usage (float), tokens_used (int), daemons_running (int),
                daemons_total (int). Missing keys default to 0 (or 8 for
                daemons_total).

        Returns:
            None
        """
        history = self.load_history()
        today = datetime.now().strftime('%Y-%m-%d')

        # Check if today's entry already exists
        existing_index = None
        for i, entry in enumerate(history['daily_metrics']):
            if entry.get('date') == today:
                existing_index = i
                break

        metric_entry = {
            'date': today,
            'timestamp': datetime.now().isoformat(),
            'health_score': metrics.get('health_score', 0),
            'errors_24h': metrics.get('errors_24h', 0),
            'policy_hits': metrics.get('policy_hits', 0),
            'context_usage': metrics.get('context_usage', 0),
            'tokens_used': metrics.get('tokens_used', 0),
            'daemons_running': metrics.get('daemons_running', 0),
            'daemons_total': metrics.get('daemons_total', 8)
        }

        if existing_index is not None:
            # Update existing entry
            history['daily_metrics'][existing_index] = metric_entry
        else:
            # Add new entry
            history['daily_metrics'].append(metric_entry)

        # Keep only last 90 days
        history['daily_metrics'] = sorted(
            history['daily_metrics'],
            key=lambda x: x['date'],
            reverse=True
        )[:90]

        history['last_updated'] = datetime.now().isoformat()
        self.save_history(history)

    def get_last_n_days(self, days=7):
        """Return the most recent N daily metric entries in chronological order.

        Sorts all stored entries by date descending, takes the first N, then
        reverses to return oldest-first (suitable for time-series charts).

        Args:
            days (int): Number of days to return. Defaults to 7.

        Returns:
            list[dict]: Up to ``days`` metric entries, oldest first.
        """
        history = self.load_history()
        metrics = history.get('daily_metrics', [])

        # Sort by date descending
        metrics = sorted(metrics, key=lambda x: x['date'], reverse=True)

        # Get last N days
        last_n = metrics[:days]

        # Reverse to get chronological order
        return list(reversed(last_n))

    def get_chart_data(self, days=7):
        """Return metric arrays formatted for Chart.js time-series charts.

        Retrieves the last N days of metrics and restructures them into
        parallel arrays keyed by metric name, suitable for direct use as
        Chart.js dataset ``data`` values.

        Args:
            days (int): Number of days to include. Defaults to 7.

        Returns:
            dict: Chart data with keys:
                dates (list[str]): ISO date strings ('YYYY-MM-DD'), oldest first.
                health_scores (list[int]): Health score values (0-100).
                errors (list[int]): Error counts (clamped >= 0).
                policy_hits (list[int]): Policy hit counts (clamped >= 0).
                context_usage (list[float]): Context usage % (clamped 0-100).
                tokens_used (list[int]): Token usage counts (clamped >= 0).
        """
        metrics = self.get_last_n_days(days)

        if not metrics:
            # Return empty data structure
            return {
                'dates': [],
                'health_scores': [],
                'errors': [],
                'policy_hits': [],
                'context_usage': [],
                'tokens_used': []
            }

        # Reverse the list to show oldest to newest (left to right on chart)
        metrics_ascending = list(reversed(metrics))

        return {
            'dates': [m['date'] for m in metrics_ascending],
            'health_scores': [max(0, m.get('health_score', 0)) for m in metrics_ascending],
            'errors': [max(0, m.get('errors_24h', 0)) for m in metrics_ascending],
            'policy_hits': [max(0, m.get('policy_hits', 0)) for m in metrics_ascending],
            'context_usage': [max(0, min(100, m.get('context_usage', 0))) for m in metrics_ascending],
            'tokens_used': [max(0, m.get('tokens_used', 0)) for m in metrics_ascending]
        }

    def get_summary_stats(self, days=7):
        """Compute aggregate summary statistics over the last N days.

        Args:
            days (int): Lookback window in days. Defaults to 7.

        Returns:
            dict: Summary statistics with keys:
                avg_health_score (float): Mean health score over the period.
                total_errors (int): Cumulative error count.
                total_policy_hits (int): Cumulative policy hit count.
                avg_context_usage (float): Mean context usage percentage.
                total_tokens (int): Cumulative token usage.
                min_health_score (int): Lowest recorded health score.
                max_health_score (int): Highest recorded health score.
            Returns zero-filled dict when no history is available.
        """
        metrics = self.get_last_n_days(days)

        if not metrics:
            return {
                'avg_health_score': 0,
                'total_errors': 0,
                'total_policy_hits': 0,
                'avg_context_usage': 0,
                'total_tokens': 0,
                'min_health_score': 0,
                'max_health_score': 0
            }

        health_scores = [m.get('health_score', 0) for m in metrics]
        errors = [m.get('errors_24h', 0) for m in metrics]
        policy_hits = [m.get('policy_hits', 0) for m in metrics]
        context_usage = [m.get('context_usage', 0) for m in metrics]
        tokens = [m.get('tokens_used', 0) for m in metrics]

        return {
            'avg_health_score': round(sum(health_scores) / len(health_scores), 1) if health_scores else 0,
            'total_errors': sum(errors),
            'total_policy_hits': sum(policy_hits),
            'avg_context_usage': round(sum(context_usage) / len(context_usage), 1) if context_usage else 0,
            'total_tokens': sum(tokens),
            'min_health_score': min(health_scores) if health_scores else 0,
            'max_health_score': max(health_scores) if health_scores else 0,
            'trend': self._calculate_trend(health_scores)
        }

    def _calculate_trend(self, values):
        """Calculate trend direction (up/down/stable)"""
        if len(values) < 2:
            return 'stable'

        # Compare first half vs second half
        mid = len(values) // 2
        first_half_avg = sum(values[:mid]) / len(values[:mid]) if mid > 0 else 0
        second_half_avg = sum(values[mid:]) / len(values[mid:]) if len(values[mid:]) > 0 else 0

        diff = second_half_avg - first_half_avg

        if diff > 5:
            return 'up'
        elif diff < -5:
            return 'down'
        else:
            return 'stable'
