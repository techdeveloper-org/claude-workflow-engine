"""Claude Insight - Main Package.

Claude Insight is a real-time monitoring dashboard for the Claude Memory System.
It tracks 3-Level Architecture execution, policy enforcement, session analytics,
and provides a web UI to visualize Claude Code behavior across sessions.

Modules:
    app        -- Flask application factory, routes, and SocketIO configuration
    config     -- Application and security configuration
    auth       -- Authentication and user management
    models     -- Data models
    routes     -- URL route handlers (blueprints)
    services   -- Business logic layer (monitoring, AI analytics, notifications)
    utils      -- Shared helper utilities

Usage::

    from src.app import create_app
    app = create_app('development')
    app.run()
"""

__version__ = "4.6.0"
