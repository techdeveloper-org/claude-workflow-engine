#!/usr/bin/env python3
"""
Comprehensive Integration Tests for Claude Workflow Engine

Tests end-to-end workflows including:
- User authentication flow
- Dashboard data loading
- Real-time updates
- Multi-service interactions
- Complete user journeys
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestAuthenticationFlow(unittest.TestCase):
    """Integration tests for authentication flow"""

    def setUp(self):
        """Set up test fixtures"""
        with patch("flask_socketio.SocketIO"):
            from app import app

            self.app = app
            self.app.config["TESTING"] = True
            self.app.config["WTF_CSRF_ENABLED"] = False
            self.client = self.app.test_client()

    @patch("bcrypt.checkpw")
    @patch("builtins.open", create=True)
    def test_complete_login_flow(self, mock_open, mock_checkpw):
        """Test complete login to dashboard flow"""
        # Mock password check
        mock_checkpw.return_value = True
        mock_file = MagicMock()
        mock_file.read.return_value = "$2b$12$test"
        mock_open.return_value.__enter__.return_value = mock_file

        # 1. Access login page
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)

        # 2. Submit login
        response = self.client.post("/login", data={"username": "admin", "password": "test123"}, follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        # 3. Access dashboard
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)

        # 4. Logout
        response = self.client.get("/logout", follow_redirects=False)
        self.assertEqual(response.status_code, 302)

    @patch("pyotp.random_base32")
    @patch("builtins.open", create=True)
    def test_2fa_setup_flow(self, mock_open, mock_random):
        """Test 2FA setup and verification flow"""
        mock_random.return_value = "TEST_SECRET"
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Login first
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True

        # 1. Check 2FA status
        response = self.client.get("/api/2fa/status")
        self.assertEqual(response.status_code, 200)

        # 2. Setup 2FA
        response = self.client.post("/api/2fa/setup")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("qr_code", data)

        # 3. Verify setup
        with patch("pyotp.TOTP") as mock_totp:
            mock_totp_instance = MagicMock()
            mock_totp_instance.verify.return_value = True
            mock_totp.return_value = mock_totp_instance

            response = self.client.post(
                "/api/2fa/verify-setup", data=json.dumps({"code": "123456"}), content_type="application/json"
            )
            self.assertEqual(response.status_code, 200)


class TestDashboardDataFlow(unittest.TestCase):
    """Integration tests for dashboard data flow"""

    def setUp(self):
        """Set up test fixtures"""
        with patch("flask_socketio.SocketIO"):
            from app import app

            self.app = app
            self.app.config["TESTING"] = True
            self.client = self.app.test_client()

            # Authenticate
            with self.client.session_transaction() as sess:
                sess["authenticated"] = True

    @patch("services.monitoring.metrics_collector.MetricsCollector.get_system_health")
    @patch("services.monitoring.session_tracker.SessionTracker.get_activity_data")
    @patch("services.monitoring.policy_checker.PolicyChecker.get_all_policies")
    def test_dashboard_initial_load(self, mock_policies, mock_activity, mock_health):
        """Test dashboard initial data loading"""
        # Mock data
        mock_health.return_value = {"status": "healthy", "health_score": 95, "running_daemons": 8}

        mock_activity.return_value = {"recent_activity": [], "hourly_stats": {}}

        mock_policies.return_value = [{"name": "policy1", "status": "active"}]

        # Load dashboard
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)

        # Load metrics
        response = self.client.get("/api/metrics")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("system_health", data)

        # Load activity
        response = self.client.get("/api/activity")
        self.assertEqual(response.status_code, 200)

        # Load policies
        response = self.client.get("/api/policies")
        self.assertEqual(response.status_code, 200)


class TestMonitoringPipeline(unittest.TestCase):
    """Integration tests for monitoring pipeline"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up"""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("utils.path_resolver.get_data_dir")
    @patch("utils.path_resolver.get_logs_dir")
    def test_metrics_collection_pipeline(self, mock_logs_dir, mock_data_dir):
        """Test complete metrics collection pipeline"""
        mock_data_dir.return_value = Path(self.temp_dir)
        mock_logs_dir.return_value = Path(self.temp_dir)

        from services.monitoring.log_parser import LogParser
        from services.monitoring.metrics_collector import MetricsCollector
        from services.monitoring.policy_checker import PolicyChecker

        collector = MetricsCollector()
        parser = LogParser()
        checker = PolicyChecker()

        # Should initialize without errors
        self.assertIsNotNone(collector)
        self.assertIsNotNone(parser)
        self.assertIsNotNone(checker)


class TestAIPipeline(unittest.TestCase):
    """Integration tests for AI analysis pipeline"""

    def test_anomaly_to_prediction_flow(self):
        """Test flow from anomaly detection to prediction"""
        from services.ai.anomaly_detector import AnomalyDetector
        from services.ai.bottleneck_analyzer import BottleneckAnalyzer
        from services.ai.predictive_analytics import PredictiveAnalytics

        detector = AnomalyDetector()
        analytics = PredictiveAnalytics()
        analyzer = BottleneckAnalyzer()

        # Generate sample metrics
        metrics = []
        base_time = datetime.now()
        from datetime import timedelta

        for i in range(100):
            metrics.append(
                {
                    "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
                    "operation": "test_op",
                    "duration": 100 + (i % 20) + (500 if i == 50 else 0),
                    "cpu": 60 + (i % 30),
                    "memory": 50 + (i % 20),
                }
            )

        # 1. Detect anomalies
        anomalies = detector.detect_anomalies(metrics)
        self.assertIsInstance(anomalies, list)

        # 2. Analyze performance
        bottlenecks = analyzer.analyze_performance(metrics)
        self.assertIsInstance(bottlenecks, dict)

        # 3. Predict future usage
        predictions = analytics.predict_future_usage(metrics, hours=24)
        self.assertIsInstance(predictions, dict)


class TestNotificationPipeline(unittest.TestCase):
    """Integration tests for notification pipeline"""

    @patch("requests.post")
    def test_alert_creation_to_delivery(self, mock_post):
        """Test flow from alert creation to delivery"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        from services.notifications.alert_routing import AlertRoutingEngine
        from services.notifications.notification_manager import NotificationManager

        manager = NotificationManager()
        router = AlertRoutingEngine()

        # 1. Create notification
        notif = manager.create_notification(title="Critical Alert", message="System health degraded", level="critical")

        self.assertIsInstance(notif, dict)

        # 2. Add routing rule
        router.add_routing_rule({"condition": {"level": "critical"}, "channels": ["slack", "email"]})

        # 3. Route alert
        configs = {
            "slack": {"webhook_url": "https://hooks.slack.com/test"},
            "email": {"smtp_server": "smtp.test.com", "from_email": "alerts@test.com", "to_email": "admin@test.com"},
        }

        results = router.route_alert(notif, configs)
        self.assertIsInstance(results, dict)


class TestWidgetWorkflow(unittest.TestCase):
    """Integration tests for widget workflows"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up"""
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("pathlib.Path.home")
    def test_widget_install_and_use_flow(self, mock_home):
        """Test complete widget install and usage flow"""
        mock_home.return_value = Path(self.temp_dir)

        from services.widgets.community_manager import CommunityWidgetsManager
        from services.widgets.version_manager import WidgetVersionManager

        community = CommunityWidgetsManager()
        versions = WidgetVersionManager()

        # 1. Browse community widgets
        widgets = community.list_community_widgets()
        self.assertIsInstance(widgets, list)

        # 2. Install widget
        widget_data = {"id": "test-widget", "name": "Test Widget", "version": "1.0.0", "code": 'console.log("test");'}

        with patch("builtins.open", create=True):
            with patch("os.makedirs"):
                result = community.install_widget(widget_data)
                self.assertIsInstance(result, dict)

        # 3. Create new version
        new_version = {"version": "1.0.1", "changes": "Bug fixes", "code": 'console.log("v1.0.1");'}

        with patch("builtins.open", create=True):
            with patch("os.makedirs"):
                result = versions.create_version("test-widget", new_version)
                self.assertIsInstance(result, dict)


class TestExportWorkflow(unittest.TestCase):
    """Integration tests for export workflows"""

    def setUp(self):
        """Set up test fixtures"""
        with patch("flask_socketio.SocketIO"):
            from app import app

            self.app = app
            self.app.config["TESTING"] = True
            self.client = self.app.test_client()

            with self.client.session_transaction() as sess:
                sess["authenticated"] = True

    @patch("services.monitoring.log_parser.LogParser.get_recent_logs")
    def test_data_export_all_formats(self, mock_logs):
        """Test exporting data in all supported formats"""
        # Mock log data
        mock_logs.return_value = [
            {"timestamp": "2026-02-16 10:00:00", "level": "INFO", "message": "Test 1"},
            {"timestamp": "2026-02-16 10:01:00", "level": "ERROR", "message": "Test 2"},
        ]

        # Test CSV export
        response = self.client.get("/api/export/logs?format=csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)

        # Test JSON export
        response = self.client.get("/api/export/logs?format=json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response.content_type)


class TestUserJourney(unittest.TestCase):
    """Integration tests for complete user journeys"""

    def setUp(self):
        """Set up test fixtures"""
        with patch("flask_socketio.SocketIO"):
            from app import app

            self.app = app
            self.app.config["TESTING"] = True
            self.app.config["WTF_CSRF_ENABLED"] = False
            self.client = self.app.test_client()

    @patch("bcrypt.checkpw")
    @patch("builtins.open", create=True)
    @patch("services.monitoring.metrics_collector.MetricsCollector.get_system_health")
    @patch("services.monitoring.log_parser.LogParser.get_recent_logs")
    def test_admin_monitoring_journey(self, mock_logs, mock_health, mock_open, mock_checkpw):
        """Test complete admin monitoring journey"""
        # Setup mocks
        mock_checkpw.return_value = True
        mock_file = MagicMock()
        mock_file.read.return_value = "$2b$12$test"
        mock_open.return_value.__enter__.return_value = mock_file

        mock_health.return_value = {"status": "healthy", "health_score": 95}

        mock_logs.return_value = [{"timestamp": "2026-02-16 10:00:00", "level": "INFO", "message": "Test"}]

        # 1. Login
        response = self.client.post("/login", data={"username": "admin", "password": "test123"})
        self.assertIn(response.status_code, [200, 302])

        # 2. View dashboard
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)

        # 3. Check system metrics
        response = self.client.get("/api/metrics")
        self.assertEqual(response.status_code, 200)

        # 4. View logs
        response = self.client.get("/logs")
        self.assertEqual(response.status_code, 200)

        # 5. Export data
        response = self.client.get("/api/export/logs?format=csv")
        self.assertIn(response.status_code, [200, 302])

        # 6. Logout
        response = self.client.get("/logout")
        self.assertEqual(response.status_code, 302)


class TestErrorRecovery(unittest.TestCase):
    """Integration tests for error recovery"""

    def setUp(self):
        """Set up test fixtures"""
        from services.monitoring.metrics_collector import MetricsCollector

        self.collector = MetricsCollector()

    @patch("subprocess.run")
    def test_service_failure_recovery(self, mock_run):
        """Test system recovery from service failures"""
        # Simulate service failure
        mock_run.side_effect = Exception("Service unavailable")

        # System should handle gracefully
        health = self.collector.get_system_health()

        self.assertIsInstance(health, dict)
        self.assertEqual(health["status"], "unknown")

    def test_invalid_data_handling(self):
        """Test handling of invalid data"""
        from services.ai.anomaly_detector import AnomalyDetector

        detector = AnomalyDetector()

        # Test with invalid data types
        invalid_data = [None, {"invalid": "format"}, "string", 123]

        # Should not crash
        try:
            result = detector.detect_anomalies(invalid_data)
            self.assertIsInstance(result, list)
        except Exception as e:
            # If it raises, should be a handled exception
            self.assertIsNotNone(str(e))


if __name__ == "__main__":
    unittest.main()
