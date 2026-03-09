"""
Configuration Management for Claude Insight.

Provides Flask application configuration classes for development, production,
and testing environments. Also resolves the data directory path with a
three-tier priority: environment variable > ~/.claude/memory > ./data.

Usage::

    from config import get_config, DevelopmentConfig
    config_class = get_config('development')
    app.config.from_object(config_class)
"""

import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent.parent

# Data directory resolution (where dashboard stores its data)
# Priority: env var > ~/.claude/memory (legacy) > ./data (portable)
_data_dir_override = os.environ.get('CLAUDE_INSIGHT_DATA_DIR')
if _data_dir_override:
    MEMORY_SYSTEM_DIR = Path(_data_dir_override)
elif (Path.home() / '.claude' / 'memory').exists():
    MEMORY_SYSTEM_DIR = Path.home() / '.claude' / 'memory'
else:
    MEMORY_SYSTEM_DIR = BASE_DIR / 'data'

# Flask Configuration
class Config:
    """Base Flask application configuration.

    Defines shared settings for all environments including secret key,
    memory system paths, retention policies, alert thresholds, WebSocket
    settings, notification parameters, and AI/ML toggles.

    Attributes:
        SECRET_KEY (str): Flask session signing key. Read from SECRET_KEY env var.
        MEMORY_DIR (Path): Root data directory for memory system files.
        LOGS_DIR (Path): Directory for log files (child of MEMORY_DIR).
        SESSIONS_DIR (Path): Directory for session files (child of MEMORY_DIR).
        DOCS_DIR (Path): Directory for documentation files (child of MEMORY_DIR).
        MEMORY_FILES_DIR (Path): Local storage for uploaded memory files.
        METRICS_RETENTION_DAYS (int): Days to retain metric data (default 30).
        LOG_RETENTION_DAYS (int): Days to retain log files (default 90).
        SESSION_RETENTION_DAYS (int): Days to retain session data (default 180).
        CONTEXT_WARNING_THRESHOLD (int): Context usage % that triggers a warning alert.
        CONTEXT_CRITICAL_THRESHOLD (int): Context usage % that triggers a critical alert.
        CONTEXT_DANGER_THRESHOLD (int): Context usage % that triggers a danger alert.
        TRENDING_WINDOW_HOURS (int): Hours window for trending widget calculation.
        FEATURED_WIDGET_COUNT (int): Maximum number of featured widgets shown.
        SOCKETIO_ASYNC_MODE (str): SocketIO async mode (default 'threading').
        NOTIFICATION_BATCH_SIZE (int): Max notifications per batch.
        NOTIFICATION_RETRY_ATTEMPTS (int): Retry count for failed notification delivery.
        ANOMALY_DETECTION_ENABLED (bool): Toggle AI anomaly detection.
        PREDICTIVE_ANALYTICS_ENABLED (bool): Toggle predictive analytics.
        MODEL_UPDATE_INTERVAL_HOURS (int): How often AI models are retrained.
    """

    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Memory System Paths (MEMORY_SYSTEM_DIR is already the data root -- no double nesting)
    MEMORY_DIR = MEMORY_SYSTEM_DIR
    LOGS_DIR = MEMORY_DIR / 'logs'
    SESSIONS_DIR = MEMORY_DIR / 'sessions'
    DOCS_DIR = MEMORY_DIR / 'docs'

    # File Storage
    MEMORY_FILES_DIR = BASE_DIR / 'memory_files'

    # Monitoring Settings
    METRICS_RETENTION_DAYS = 30
    LOG_RETENTION_DAYS = 90
    SESSION_RETENTION_DAYS = 180

    # Alert Thresholds
    CONTEXT_WARNING_THRESHOLD = 70
    CONTEXT_CRITICAL_THRESHOLD = 85
    CONTEXT_DANGER_THRESHOLD = 90

    # Widget Settings
    TRENDING_WINDOW_HOURS = 24
    FEATURED_WIDGET_COUNT = 10

    # WebSocket Settings
    SOCKETIO_ASYNC_MODE = 'threading'
    SOCKETIO_LOGGER = False
    SOCKETIO_ENGINEIO_LOGGER = False

    # Notification Settings
    NOTIFICATION_BATCH_SIZE = 50
    NOTIFICATION_RETRY_ATTEMPTS = 3

    # AI/ML Settings
    ANOMALY_DETECTION_ENABLED = True
    PREDICTIVE_ANALYTICS_ENABLED = True
    MODEL_UPDATE_INTERVAL_HOURS = 6

    @staticmethod
    def init_app(app):
        """Initialize the Flask application with required directory structure.

        Creates all necessary data directories on disk if they do not already
        exist. Should be called once during application startup.

        Args:
            app: The Flask application instance to initialize.

        Returns:
            None
        """
        # Create necessary directories
        os.makedirs(Config.MEMORY_FILES_DIR, exist_ok=True)
        os.makedirs(Config.LOGS_DIR, exist_ok=True)
        os.makedirs(Config.SESSIONS_DIR, exist_ok=True)
        os.makedirs(Config.DOCS_DIR, exist_ok=True)


class DevelopmentConfig(Config):
    """Development environment configuration.

    Inherits all base settings from Config and enables DEBUG mode.
    Use for local development and manual testing only.

    Attributes:
        DEBUG (bool): True - enables Flask debug mode and reloader.
        TESTING (bool): False - testing mode is off in development.
    """

    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production environment configuration.

    Inherits all base settings from Config with debug and testing disabled.
    Requires the SECRET_KEY environment variable to be set explicitly;
    falls back to None if not provided, which will cause Flask to error.

    Attributes:
        DEBUG (bool): False - disables debug mode for security.
        TESTING (bool): False - disables testing mode.
        SECRET_KEY (str or None): Must be set via SECRET_KEY environment variable.
    """

    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY')


class TestingConfig(Config):
    """Testing environment configuration.

    Inherits all base settings from Config with both DEBUG and TESTING enabled.
    Use for automated test suites (pytest, unittest).

    Attributes:
        DEBUG (bool): True - enables debug output during test runs.
        TESTING (bool): True - enables Flask testing mode (propagates exceptions).
    """

    DEBUG = True
    TESTING = True


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(env=None):
    """Return the configuration class for the specified environment.

    Looks up the environment name in the ``config`` registry and returns the
    corresponding configuration class. If the environment is not recognised,
    the default (development) class is returned.

    Args:
        env (str or None): Environment name - one of 'development',
            'production', 'testing', or 'default'. When None, the value of
            the FLASK_ENV environment variable is used, defaulting to
            'development' if that variable is also unset.

    Returns:
        type: A Config subclass (DevelopmentConfig, ProductionConfig, or
            TestingConfig).
    """
    if env is None:
        env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])
