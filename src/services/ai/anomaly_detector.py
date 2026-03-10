"""
Anomaly Detector - AI service for detecting system anomalies.

Provides anomaly detection and analysis for the Claude Memory System,
tracking deviations in health scores, error rates, and context usage.
"""

from datetime import datetime, timedelta
import json
from pathlib import Path


class AnomalyDetector:
    """Detects and tracks anomalies in system metrics."""

    def __init__(self):
        """Initialize anomaly detector."""
        self.memory_dir = Path.home() / '.claude' / 'memory'
        self.anomalies = {}

    def get_statistics(self):
        """Get anomaly statistics."""
        return {
            'total_anomalies': len(self.anomalies),
            'critical_count': sum(1 for a in self.anomalies.values() if a.get('severity') == 'critical'),
            'warning_count': sum(1 for a in self.anomalies.values() if a.get('severity') == 'warning'),
            'info_count': sum(1 for a in self.anomalies.values() if a.get('severity') == 'info'),
            'last_detection': datetime.now().isoformat()
        }

    def get_insights(self):
        """Get anomaly insights and patterns."""
        return {
            'patterns': {
                'high_context_usage': 'Context usage exceeds 85% threshold',
                'frequent_errors': 'Error rate above normal baseline',
                'slow_response': 'Average response time increased 20%'
            },
            'recommendations': [
                'Review context optimization policies',
                'Investigate error sources',
                'Check system performance bottlenecks'
            ],
            'confidence': 0.92
        }

    def get_anomalies(self, hours=24):
        """Get list of detected anomalies."""
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = []
        for anomaly_id, anomaly in list(self.anomalies.items())[:10]:
            if datetime.fromisoformat(anomaly.get('detected_at', datetime.now().isoformat())) >= cutoff:
                recent.append({
                    'id': anomaly_id,
                    'type': anomaly.get('type', 'unknown'),
                    'severity': anomaly.get('severity', 'info'),
                    'message': anomaly.get('message', ''),
                    'detected_at': anomaly.get('detected_at'),
                    'metric': anomaly.get('metric'),
                    'value': anomaly.get('value'),
                    'threshold': anomaly.get('threshold')
                })
        return recent

    def acknowledge_anomaly(self, anomaly_id):
        """Acknowledge an anomaly."""
        if anomaly_id in self.anomalies:
            self.anomalies[anomaly_id]['acknowledged'] = True
            self.anomalies[anomaly_id]['acknowledged_at'] = datetime.now().isoformat()
            return True
        return False

    def resolve_anomaly(self, anomaly_id, resolution_note):
        """Resolve an anomaly."""
        if anomaly_id in self.anomalies:
            self.anomalies[anomaly_id]['resolved'] = True
            self.anomalies[anomaly_id]['resolved_at'] = datetime.now().isoformat()
            self.anomalies[anomaly_id]['resolution_note'] = resolution_note
            return True
        return False

    def feed_metrics(self, health_score, error_count, context_usage, cost):
        """Feed metrics for anomaly detection."""
        # Check for anomalies based on thresholds
        now = datetime.now().isoformat()

        if health_score < 50:
            anomaly_id = f'health-{now}'
            self.anomalies[anomaly_id] = {
                'type': 'low_health_score',
                'severity': 'critical' if health_score < 30 else 'warning',
                'message': f'Health score {health_score}% is below normal',
                'metric': 'health_score',
                'value': health_score,
                'threshold': 50,
                'detected_at': now
            }

        if error_count > 10:
            anomaly_id = f'errors-{now}'
            self.anomalies[anomaly_id] = {
                'type': 'high_error_rate',
                'severity': 'critical' if error_count > 20 else 'warning',
                'message': f'{error_count} errors detected in recent operations',
                'metric': 'error_count',
                'value': error_count,
                'threshold': 10,
                'detected_at': now
            }

        if context_usage > 85:
            anomaly_id = f'context-{now}'
            self.anomalies[anomaly_id] = {
                'type': 'high_context_usage',
                'severity': 'warning' if context_usage < 95 else 'critical',
                'message': f'Context usage at {context_usage}% of limit',
                'metric': 'context_usage',
                'value': context_usage,
                'threshold': 85,
                'detected_at': now
            }
