"""
Predictive Analytics and Forecasting Engine for Claude Insight.

Uses statistical methods for time-series forecasting of system health metrics
such as health score, error count, context usage, response time, API cost,
and API call counts.

Forecasting algorithms provided:
    linear_regression_forecast       -- OLS linear trend projection.
    exponential_smoothing_forecast   -- Single exponential smoothing with trend.
    moving_average_forecast          -- Moving average projection with trend.
    seasonal_forecast                -- Deseasonalized + reseasonalized forecast.

Data is persisted to JSON files under data/forecasts/:
    forecasts.json    -- Generated forecast records.
    predictions.json  -- Per-metric prediction state.
    models.json       -- Stored model parameters.

Classes:
    PredictiveAnalytics: Forecasting engine for system metrics using statistical methods.
"""
import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add path resolver for portable paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.path_resolver import get_data_dir, get_logs_dir
from collections import deque


class PredictiveAnalytics:
    """Forecast system metrics using statistical time-series algorithms.

    Maintains per-metric in-memory ring buffers and persists forecasts,
    predictions, and model parameters to JSON files under data/forecasts/.

    Attributes:
        data_dir (Path): Directory for forecast data files (data/forecasts/).
        forecasts_file (Path): Path to forecasts.json.
        predictions_file (Path): Path to predictions.json.
        models_file (Path): Path to models.json.
        metric_buffers (dict): Map of metric name to deque(maxlen=1000) for
            'health_score', 'error_count', 'context_usage', 'response_time',
            'cost', and 'api_calls'.
    """

    def __init__(self):
        """Initialize PredictiveAnalytics, create data directory, and ensure data files exist."""
        self.data_dir = get_data_dir() / 'forecasts'
        self.forecasts_file = self.data_dir / 'forecasts.json'
        self.predictions_file = self.data_dir / 'predictions.json'
        self.models_file = self.data_dir / 'models.json'

        # In-memory buffers for forecasting
        self.metric_buffers = {
            'health_score': deque(maxlen=1000),
            'error_count': deque(maxlen=1000),
            'context_usage': deque(maxlen=1000),
            'response_time': deque(maxlen=1000),
            'cost': deque(maxlen=1000),
            'api_calls': deque(maxlen=1000)
        }

        self.ensure_data_files()

    def ensure_data_files(self):
        """Create data_dir and initialize forecast JSON files with empty structures if absent."""
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)

        if not self.forecasts_file.exists():
            self.forecasts_file.write_text(json.dumps({
                'forecasts': [],
                'last_updated': datetime.now().isoformat()
            }))

        if not self.predictions_file.exists():
            self.predictions_file.write_text(json.dumps({
                'predictions': {},
                'last_updated': datetime.now().isoformat()
            }))

        if not self.models_file.exists():
            self.models_file.write_text(json.dumps({
                'models': {},
                'last_trained': None
            }))

    def load_forecasts(self):
        """Load the forecasts dictionary from forecasts.json.

        Returns:
            dict: Data with keys forecasts (list) and last_updated (str or None).
                Returns empty structure on read errors.
        """
        try:
            return json.loads(self.forecasts_file.read_text())
        except Exception as e:
            print(f"Error loading forecasts: {e}")
            return {'forecasts': [], 'last_updated': None}

    def save_forecasts(self, data):
        """Write the forecasts dictionary to forecasts.json and update last_updated.

        Args:
            data (dict): Forecasts data to persist.
        """
        try:
            data['last_updated'] = datetime.now().isoformat()
            self.forecasts_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Error saving forecasts: {e}")

    def load_predictions(self):
        """Load predictions data"""
        try:
            return json.loads(self.predictions_file.read_text())
        except Exception as e:
            print(f"Error loading predictions: {e}")
            return {'predictions': {}, 'last_updated': None}

    def save_predictions(self, data):
        """Write the predictions dictionary to predictions.json and update last_updated.

        Args:
            data (dict): Predictions data to persist.
        """
        try:
            data['last_updated'] = datetime.now().isoformat()
            self.predictions_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Error saving predictions: {e}")

    def add_metric_point(self, metric_name, value, timestamp=None):
        """Append a metric data point to the in-memory buffer for the given metric.

        Args:
            metric_name (str): Metric key - one of 'health_score', 'error_count',
                'context_usage', 'response_time', 'cost', or 'api_calls'.
            value (float): The metric value to record.
            timestamp (str or None): ISO timestamp string. Defaults to current time.
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()

        if metric_name in self.metric_buffers:
            self.metric_buffers[metric_name].append({
                'value': value,
                'timestamp': timestamp
            })

    def linear_regression_forecast(self, values, periods=10):
        """Forecast future values using OLS linear regression.

        Fits a linear trend line to the input values and extrapolates
        it ``periods`` steps into the future. Also computes R-squared.

        Args:
            values (list[float]): Historical time-series values (at least 3 required).
            periods (int): Number of future periods to forecast. Defaults to 10.

        Returns:
            tuple[list[float], float, float]: (forecasted_values, slope, r_squared).
                Returns ([], 0, 0) when fewer than 3 values are provided.
        """
        if len(values) < 3:
            return [], 0, 0

        n = len(values)
        x = np.arange(n)
        y = np.array(values)

        # Calculate slope and intercept
        x_mean = np.mean(x)
        y_mean = np.mean(y)

        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2)

        if denominator == 0:
            return [y_mean] * periods, 0, y_mean

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # Forecast future values
        future_x = np.arange(n, n + periods)
        forecasts = slope * future_x + intercept

        # Calculate R-squared
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y_mean) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        return forecasts.tolist(), slope, r_squared

    def exponential_smoothing_forecast(self, values, periods=10, alpha=0.3):
        """Forecast future values using single exponential smoothing with trend.

        Applies exponential smoothing to the history and extrapolates using
        the trend (last_smoothed - second_last_smoothed) * step.

        Args:
            values (list[float]): Historical time-series values (at least 2 required).
            periods (int): Number of future periods to forecast. Defaults to 10.
            alpha (float): Smoothing factor (0 < alpha <= 1). Defaults to 0.3.

        Returns:
            list[float]: Forecasted values for the next ``periods`` steps.
        """
        if len(values) < 2:
            return [values[-1] if values else 0] * periods

        # Apply exponential smoothing
        smoothed = [values[0]]
        for i in range(1, len(values)):
            smoothed.append(alpha * values[i] + (1 - alpha) * smoothed[-1])

        # Forecast using last smoothed value and trend
        last_smoothed = smoothed[-1]
        if len(smoothed) >= 2:
            trend = smoothed[-1] - smoothed[-2]
        else:
            trend = 0

        forecasts = []
        for i in range(periods):
            forecast = last_smoothed + trend * (i + 1)
            forecasts.append(forecast)

        return forecasts

    def moving_average_forecast(self, values, periods=10, window=5):
        """Forecast future values using a moving average with trend projection.

        Computes a convolution-based moving average and extrapolates using
        the last MA trend step.

        Args:
            values (list[float]): Historical time-series values.
            periods (int): Number of future periods to forecast. Defaults to 10.
            window (int): Rolling window size for the moving average. Defaults to 5.

        Returns:
            list[float]: Forecasted values for the next ``periods`` steps.
        """
        if len(values) < window:
            avg = np.mean(values) if values else 0
            return [avg] * periods

        # Calculate moving average
        ma = np.convolve(values, np.ones(window)/window, mode='valid')
        last_ma = ma[-1]

        # Calculate trend from last few moving averages
        if len(ma) >= 2:
            trend = ma[-1] - ma[-2]
        else:
            trend = 0

        forecasts = []
        for i in range(periods):
            forecast = last_ma + trend * (i + 1)
            forecasts.append(forecast)

        return forecasts

    def seasonal_forecast(self, values, periods=10, season_length=24):
        """Forecast future values accounting for seasonal patterns.

        Deseasonalizes the input using multiplicative seasonal indices,
        applies exponential smoothing to the deseasonalized trend, then
        reseasonalizes the forecast. Falls back to exponential smoothing
        when insufficient data for seasonal analysis (< 2 full seasons).

        Args:
            values (list[float]): Historical time-series values.
            periods (int): Number of future periods to forecast. Defaults to 10.
            season_length (int): Length of one seasonal cycle. Defaults to 24 (hourly).

        Returns:
            list[float]: Reseasonalized forecasted values for the next ``periods`` steps.
        """
        if len(values) < season_length * 2:
            # Not enough data for seasonal analysis
            return self.exponential_smoothing_forecast(values, periods)

        # Calculate seasonal indices
        n_seasons = len(values) // season_length
        seasonal_avg = np.zeros(season_length)

        for i in range(season_length):
            season_values = [values[i + j * season_length]
                           for j in range(n_seasons)
                           if i + j * season_length < len(values)]
            seasonal_avg[i] = np.mean(season_values) if season_values else 0

        overall_avg = np.mean(seasonal_avg) if len(seasonal_avg) > 0 else 1
        seasonal_indices = seasonal_avg / overall_avg if overall_avg != 0 else np.ones(season_length)

        # Deseasonalize data
        deseasonalized = []
        for i, val in enumerate(values):
            season_idx = i % season_length
            deseasonalized.append(val / seasonal_indices[season_idx] if seasonal_indices[season_idx] != 0 else val)

        # Forecast deseasonalized trend
        trend_forecast = self.exponential_smoothing_forecast(deseasonalized, periods)

        # Reseasonalize forecasts
        forecasts = []
        for i, trend_val in enumerate(trend_forecast):
            season_idx = (len(values) + i) % season_length
            forecasts.append(trend_val * seasonal_indices[season_idx])

        return forecasts

    def ensemble_forecast(self, values, periods=10, method='weighted'):
        """
        Ensemble forecast combining multiple methods
        """
        if len(values) < 3:
            avg = np.mean(values) if values else 0
            return [avg] * periods, {'confidence': 0.0, 'methods': {}}

        # Get forecasts from different methods
        lr_forecast, slope, r_squared = self.linear_regression_forecast(values, periods)
        es_forecast = self.exponential_smoothing_forecast(values, periods)
        ma_forecast = self.moving_average_forecast(values, periods)

        # Calculate weights based on historical accuracy
        weights = {
            'linear': max(0, r_squared) if r_squared else 0.3,
            'exponential': 0.4,
            'moving_average': 0.3
        }

        # Normalize weights
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {k: v/total_weight for k, v in weights.items()}
        else:
            weights = {'linear': 0.33, 'exponential': 0.33, 'moving_average': 0.34}

        # Combine forecasts
        ensemble = []
        for i in range(periods):
            combined = (
                weights['linear'] * lr_forecast[i] +
                weights['exponential'] * es_forecast[i] +
                weights['moving_average'] * ma_forecast[i]
            )
            ensemble.append(combined)

        # Calculate confidence based on forecast agreement
        confidence = self.calculate_forecast_confidence(
            lr_forecast, es_forecast, ma_forecast
        )

        methods_detail = {
            'linear_regression': {'values': lr_forecast, 'weight': weights['linear'], 'r_squared': r_squared},
            'exponential_smoothing': {'values': es_forecast, 'weight': weights['exponential']},
            'moving_average': {'values': ma_forecast, 'weight': weights['moving_average']}
        }

        return ensemble, {'confidence': confidence, 'methods': methods_detail, 'weights': weights}

    def calculate_forecast_confidence(self, *forecasts):
        """
        Calculate confidence based on agreement between forecasts
        """
        if not forecasts or len(forecasts) < 2:
            return 0.5

        # Calculate coefficient of variation for each period
        cv_values = []
        for i in range(len(forecasts[0])):
            period_values = [f[i] for f in forecasts if i < len(f)]
            if len(period_values) < 2:
                continue

            mean = np.mean(period_values)
            std = np.std(period_values)

            if mean != 0:
                cv = std / abs(mean)
                cv_values.append(cv)

        if not cv_values:
            return 0.5

        # Lower CV = higher confidence
        avg_cv = np.mean(cv_values)
        confidence = 1 / (1 + avg_cv)  # Maps to 0-1 range

        return min(1.0, max(0.0, confidence))

    def forecast_metric(self, metric_name, periods=24, method='ensemble'):
        """
        Forecast a specific metric for n periods ahead
        """
        if metric_name not in self.metric_buffers:
            return {
                'success': False,
                'message': f'Unknown metric: {metric_name}'
            }

        data_points = list(self.metric_buffers[metric_name])
        if len(data_points) < 3:
            return {
                'success': False,
                'message': 'Insufficient data for forecasting (need at least 3 points)'
            }

        values = [point['value'] for point in data_points]

        # Generate forecast
        if method == 'ensemble':
            forecasts, details = self.ensemble_forecast(values, periods)
        elif method == 'linear':
            forecasts, slope, r_squared = self.linear_regression_forecast(values, periods)
            details = {'confidence': r_squared, 'slope': slope}
        elif method == 'exponential':
            forecasts = self.exponential_smoothing_forecast(values, periods)
            details = {'confidence': 0.7}
        elif method == 'moving_average':
            forecasts = self.moving_average_forecast(values, periods)
            details = {'confidence': 0.6}
        elif method == 'seasonal':
            forecasts = self.seasonal_forecast(values, periods)
            details = {'confidence': 0.75}
        else:
            forecasts, details = self.ensemble_forecast(values, periods)

        # Calculate confidence intervals
        recent_values = values[-min(50, len(values)):]
        std_dev = np.std(recent_values) if len(recent_values) > 1 else 0

        confidence_intervals = []
        for i, forecast in enumerate(forecasts):
            # Wider intervals for further predictions
            interval_width = std_dev * (1 + i * 0.1)
            confidence_intervals.append({
                'lower': forecast - interval_width,
                'upper': forecast + interval_width
            })

        # Generate timestamps for forecast periods
        last_timestamp = datetime.fromisoformat(data_points[-1]['timestamp'])
        forecast_timestamps = []
        for i in range(periods):
            forecast_timestamps.append((last_timestamp + timedelta(hours=i+1)).isoformat())

        return {
            'success': True,
            'metric': metric_name,
            'method': method,
            'periods': periods,
            'forecasts': forecasts,
            'confidence_intervals': confidence_intervals,
            'timestamps': forecast_timestamps,
            'details': details,
            'historical': {
                'values': values[-50:],  # Last 50 points
                'timestamps': [p['timestamp'] for p in data_points[-50:]]
            }
        }

    def predict_capacity_breach(self, metric_name, threshold, horizon=168):
        """
        Predict when a metric will breach a threshold (capacity planning)
        horizon: hours to look ahead (default 1 week)
        """
        forecast_result = self.forecast_metric(metric_name, periods=horizon, method='ensemble')

        if not forecast_result['success']:
            return {
                'success': False,
                'message': forecast_result['message']
            }

        forecasts = forecast_result['forecasts']
        timestamps = forecast_result['timestamps']

        # Find first breach
        breach_point = None
        breach_time = None
        breach_value = None

        for i, (forecast, timestamp) in enumerate(zip(forecasts, timestamps)):
            if forecast > threshold:
                breach_point = i
                breach_time = timestamp
                breach_value = forecast
                break

        if breach_point is None:
            return {
                'success': True,
                'will_breach': False,
                'message': f'No breach predicted within {horizon} hours',
                'metric': metric_name,
                'threshold': threshold,
                'max_predicted': max(forecasts),
                'horizon_hours': horizon
            }

        hours_until_breach = breach_point + 1

        return {
            'success': True,
            'will_breach': True,
            'metric': metric_name,
            'threshold': threshold,
            'breach_time': breach_time,
            'breach_value': breach_value,
            'hours_until_breach': hours_until_breach,
            'urgency': 'critical' if hours_until_breach < 24 else 'high' if hours_until_breach < 72 else 'medium',
            'recommendation': self.get_breach_recommendation(metric_name, hours_until_breach)
        }

    def get_breach_recommendation(self, metric_name, hours_until):
        """Get recommendation based on predicted breach"""
        recommendations = {
            'context_usage': 'Consider context cleanup or starting a new session',
            'error_count': 'Investigate error patterns and implement fixes',
            'response_time': 'Check system resources and optimize queries',
            'cost': 'Review API usage and consider cost optimization strategies'
        }

        base_rec = recommendations.get(metric_name, 'Monitor the situation closely')

        if hours_until < 24:
            return f'URGENT: {base_rec} within 24 hours'
        elif hours_until < 72:
            return f'SOON: {base_rec} within 3 days'
        else:
            return f'Plan ahead: {base_rec} within the week'

    def generate_forecast_insights(self):
        """Generate insights from forecasting data"""
        insights = []

        for metric_name in ['health_score', 'error_count', 'context_usage', 'cost']:
            forecast_result = self.forecast_metric(metric_name, periods=24)

            if not forecast_result['success']:
                continue

            forecasts = forecast_result['forecasts']
            historical = forecast_result['historical']['values']

            # Trend analysis
            if len(forecasts) >= 12:
                early_avg = np.mean(forecasts[:6])
                late_avg = np.mean(forecasts[-6:])
                trend_change = ((late_avg - early_avg) / early_avg * 100) if early_avg != 0 else 0

                if abs(trend_change) > 10:
                    direction = 'increase' if trend_change > 0 else 'decrease'
                    insights.append({
                        'type': 'trend',
                        'metric': metric_name,
                        'priority': 'high' if abs(trend_change) > 25 else 'medium',
                        'message': f'{metric_name.replace("_", " ").title()} predicted to {direction} by {abs(trend_change):.1f}% in next 24 hours',
                        'recommendation': f'Monitor {metric_name} closely for next 24 hours'
                    })

            # Capacity breach predictions
            thresholds = {
                'context_usage': 85,
                'error_count': 50,
                'health_score': 60  # Breach if goes below
            }

            if metric_name in thresholds:
                if metric_name == 'health_score':
                    # Invert logic for health score
                    breach_result = self.predict_capacity_breach(metric_name, thresholds[metric_name], horizon=168)
                    if breach_result['success'] and breach_result.get('will_breach'):
                        insights.append({
                            'type': 'capacity_warning',
                            'metric': metric_name,
                            'priority': breach_result['urgency'],
                            'message': f'{metric_name.replace("_", " ").title()} predicted to drop below {thresholds[metric_name]}',
                            'recommendation': breach_result['recommendation']
                        })
                else:
                    breach_result = self.predict_capacity_breach(metric_name, thresholds[metric_name], horizon=168)
                    if breach_result['success'] and breach_result.get('will_breach'):
                        insights.append({
                            'type': 'capacity_warning',
                            'metric': metric_name,
                            'priority': breach_result['urgency'],
                            'message': f'{metric_name.replace("_", " ").title()} predicted to exceed {thresholds[metric_name]} in {breach_result["hours_until_breach"]} hours',
                            'recommendation': breach_result['recommendation']
                        })

        return {
            'total_insights': len(insights),
            'insights': insights,
            'generated_at': datetime.now().isoformat()
        }

    def get_forecast_summary(self):
        """Get summary of all active forecasts"""
        summary = {
            'metrics': {},
            'overall_health': 'good',
            'critical_predictions': 0,
            'generated_at': datetime.now().isoformat()
        }

        for metric_name in ['health_score', 'error_count', 'context_usage', 'cost', 'response_time']:
            forecast_result = self.forecast_metric(metric_name, periods=24, method='ensemble')

            if not forecast_result['success']:
                continue

            forecasts = forecast_result['forecasts']
            confidence = forecast_result['details'].get('confidence', 0.5)

            summary['metrics'][metric_name] = {
                'current': forecast_result['historical']['values'][-1] if forecast_result['historical']['values'] else 0,
                'predicted_24h': forecasts[-1] if forecasts else 0,
                'trend': 'increasing' if forecasts[-1] > forecasts[0] else 'decreasing' if forecasts[-1] < forecasts[0] else 'stable',
                'confidence': confidence,
                'forecasts': forecasts[:24]  # Next 24 hours
            }

        return summary
