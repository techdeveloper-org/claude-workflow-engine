"""AI Services - Anomaly detection, predictive analytics.

Provides AI-powered analysis modules that process data collected by the
monitoring services and surface actionable insights in the dashboard.

Exported classes:
    BottleneckAnalyzer -- Identifies performance bottlenecks in hook
                          execution chains by analysing timing data from
                          the metrics JSONL log. Highlights which policy
                          steps consume the most time across sessions.

Planned additions:
    AnomalyDetector    -- Statistical outlier detection for unusual tool
                          usage patterns or unexpected enforcement rates.
    PredictiveModels   -- Forecast context-window exhaustion based on
                          current session velocity.

Usage::

    from src.services.ai import BottleneckAnalyzer
    analyzer = BottleneckAnalyzer()
    report = analyzer.analyze()
"""

from .bottleneck_analyzer import BottleneckAnalyzer
from .anomaly_detector import AnomalyDetector
from .predictive_analytics import PredictiveAnalytics

__all__ = ['BottleneckAnalyzer', 'AnomalyDetector', 'PredictiveAnalytics']
