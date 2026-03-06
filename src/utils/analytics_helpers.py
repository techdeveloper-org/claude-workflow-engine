"""
Analytics Helper Utilities for Claude Insight.

Provides calculation and analysis functions used across the application:
- Trend calculations (direction, percentage change)
- Policy effectiveness analysis
- Daemon uptime calculations
- Peak hour/day analysis from historical data
- Metric aggregations and statistics

These helpers are extracted to avoid duplication and provide reusable
analysis logic across dashboard, analytics, and API routes.
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
from collections import defaultdict


def calculate_trend(current_value, previous_value):
    """
    Calculate trend between two values.

    Args:
        current_value (float): Current metric value
        previous_value (float): Previous metric value

    Returns:
        dict: Trend data with direction ('up', 'down', 'flat') and percentage change
    """
    if previous_value == 0:
        percentage = 0 if current_value == 0 else 100
    else:
        percentage = round(((current_value - previous_value) / previous_value) * 100, 1)

    if percentage > 0:
        direction = 'up'
    elif percentage < 0:
        direction = 'down'
    else:
        direction = 'flat'

    return {
        'direction': direction,
        'percentage': abs(percentage),
        'value': percentage
    }


def calculate_policy_effectiveness(total_executions, successful_executions):
    """
    Calculate policy effectiveness as percentage.

    Args:
        total_executions (int): Total policy execution count
        successful_executions (int): Number of successful executions

    Returns:
        dict: Effectiveness metrics with percentage and success rate
    """
    if total_executions == 0:
        return {
            'effectiveness': 0,
            'success_rate': 0,
            'total_executions': 0,
            'successful': 0,
            'failed': 0
        }

    effectiveness = round((successful_executions / total_executions) * 100, 1)

    return {
        'effectiveness': effectiveness,
        'success_rate': effectiveness,
        'total_executions': total_executions,
        'successful': successful_executions,
        'failed': total_executions - successful_executions
    }


def calculate_daemon_uptime(start_time, end_time=None):
    """
    Calculate daemon uptime duration.

    Args:
        start_time (str): ISO format start timestamp
        end_time (str, optional): ISO format end timestamp, defaults to now

    Returns:
        dict: Uptime data with duration, percentage availability
    """
    try:
        if isinstance(start_time, str):
            start = datetime.fromisoformat(start_time)
        else:
            start = start_time

        if end_time:
            if isinstance(end_time, str):
                end = datetime.fromisoformat(end_time)
            else:
                end = end_time
        else:
            end = datetime.now()

        duration = end - start
        hours = duration.total_seconds() / 3600
        uptime_percent = min(100, round((hours / 24) * 100, 1))

        return {
            'duration_hours': round(hours, 2),
            'duration_days': round(hours / 24, 2),
            'uptime_percentage': uptime_percent,
            'start_time': start.isoformat(),
            'end_time': end.isoformat()
        }
    except Exception as e:
        return {
            'error': str(e),
            'uptime_percentage': 0
        }


def calculate_peak_hours(log_file_path, days=7):
    """
    Calculate peak usage hours from metrics logs.

    Args:
        log_file_path (str): Path to metrics log file (JSONL format)
        days (int): Number of days to analyze

    Returns:
        dict: Peak hour, busiest day, and busiest period
    """
    try:
        hourly_counts = defaultdict(int)
        daily_counts = defaultdict(int)
        cutoff_date = datetime.now() - timedelta(days=days)

        log_path = Path(log_file_path)
        if not log_path.exists():
            return {
                'peak_hour': 'N/A',
                'peak_day': 'N/A',
                'busiest_period': 'N/A'
            }

        with open(log_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    timestamp_str = entry.get('timestamp', '')
                    if timestamp_str:
                        ts = datetime.fromisoformat(timestamp_str)
                        if ts >= cutoff_date:
                            hourly_counts[ts.hour] += 1
                            daily_counts[ts.strftime('%A')] += 1
                except Exception:
                    continue

        if not hourly_counts:
            return {
                'peak_hour': 'N/A',
                'peak_day': 'N/A',
                'busiest_period': 'N/A'
            }

        peak_hour = max(hourly_counts, key=hourly_counts.get)
        peak_day = max(daily_counts, key=daily_counts.get)

        # Determine busiest period
        if peak_hour < 6:
            period = 'Night'
        elif peak_hour < 12:
            period = 'Morning'
        elif peak_hour < 18:
            period = 'Afternoon'
        else:
            period = 'Evening'

        return {
            'peak_hour': f'{peak_hour:02d}:00',
            'peak_day': peak_day,
            'busiest_period': period,
            'hourly_distribution': dict(hourly_counts),
            'daily_distribution': dict(daily_counts)
        }
    except Exception as e:
        return {
            'error': str(e),
            'peak_hour': 'N/A',
            'peak_day': 'N/A',
            'busiest_period': 'N/A'
        }


def aggregate_metrics(metrics_list, aggregation_type='avg'):
    """
    Aggregate a list of metrics.

    Args:
        metrics_list (list): List of numeric metric values
        aggregation_type (str): Type of aggregation ('avg', 'sum', 'min', 'max')

    Returns:
        float: Aggregated metric value
    """
    if not metrics_list:
        return 0

    if aggregation_type == 'avg':
        return round(sum(metrics_list) / len(metrics_list), 2)
    elif aggregation_type == 'sum':
        return sum(metrics_list)
    elif aggregation_type == 'min':
        return min(metrics_list)
    elif aggregation_type == 'max':
        return max(metrics_list)
    else:
        return round(sum(metrics_list) / len(metrics_list), 2)  # Default to average


def calculate_compliance_rate(passed_policies, total_policies):
    """
    Calculate compliance rate percentage.

    Args:
        passed_policies (int): Number of policies that passed
        total_policies (int): Total number of policies

    Returns:
        dict: Compliance metrics with percentage and details
    """
    if total_policies == 0:
        return {
            'compliance_rate': 0,
            'passed': 0,
            'total': 0,
            'failed': 0
        }

    rate = round((passed_policies / total_policies) * 100, 1)

    return {
        'compliance_rate': rate,
        'passed': passed_policies,
        'total': total_policies,
        'failed': total_policies - passed_policies
    }


def calculate_cost_savings(before_cost, after_cost):
    """
    Calculate cost savings between two periods.

    Args:
        before_cost (float): Cost before optimization
        after_cost (float): Cost after optimization

    Returns:
        dict: Savings metrics with amount and percentage
    """
    savings = before_cost - after_cost
    if before_cost == 0:
        percent = 0
    else:
        percent = round((savings / before_cost) * 100, 1)

    return {
        'before': before_cost,
        'after': after_cost,
        'savings': savings,
        'savings_percent': percent,
        'roi': round((savings / max(1, before_cost)) * 100, 1)
    }


def format_duration(milliseconds):
    """
    Format milliseconds into human-readable duration.

    Args:
        milliseconds (int): Duration in milliseconds

    Returns:
        str: Formatted duration string (e.g., "1h 23m 45s")
    """
    seconds = milliseconds / 1000
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    hours = int(minutes // 60)
    minutes = int(minutes % 60)

    if hours > 0:
        return f'{hours}h {minutes}m {seconds}s'
    elif minutes > 0:
        return f'{minutes}m {seconds}s'
    else:
        return f'{seconds}s'


def percentile(data, percentile_value):
    """
    Calculate percentile value from sorted list.

    Args:
        data (list): Sorted list of numeric values
        percentile_value (int): Percentile to calculate (0-100)

    Returns:
        float: Value at specified percentile
    """
    if not data:
        return 0

    sorted_data = sorted(data)
    index = int((percentile_value / 100) * len(sorted_data))
    return sorted_data[min(index, len(sorted_data) - 1)]
