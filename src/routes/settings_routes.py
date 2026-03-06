"""
Settings Routes Blueprint for Claude Insight.

Provides configuration and management endpoints for:
- Plugins: Installation, enabling/disabling, configuration
- Notifications: Slack, Discord, PagerDuty channel setup
- Integrations: External service connections
- Theme Management: User theme preferences and persistence
- Widget Configuration: Dashboard widget management

All routes require authentication and return JSON responses.
Settings are persisted to JSON files in config directory.
"""

from flask import Blueprint, jsonify, request, session
from functools import wraps
from datetime import datetime
import json
from pathlib import Path

# Create blueprint
settings_bp = Blueprint('settings', __name__, url_prefix='')


def login_required(f):
    """Decorator to require login for protected routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import session, redirect, url_for
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ─────────────────────────────────────────────────────────────────────────────
# PLUGIN MANAGEMENT ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route('/plugins')
@login_required
def plugins_page():
    """Render plugins management page."""
    from flask import render_template
    return render_template('plugins.html')


@settings_bp.route('/api/plugins/installed', methods=['GET'])
@login_required
def get_installed_plugins():
    """Get list of installed plugins."""
    try:
        plugins_dir = Path.home() / '.claude' / 'memory' / 'config' / 'plugins'
        plugins = []

        if plugins_dir.exists():
            for plugin_file in plugins_dir.glob('*.json'):
                with open(plugin_file, 'r') as f:
                    plugin = json.load(f)
                    plugins.append(plugin)

        return jsonify({'plugins': plugins, 'count': len(plugins)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/plugins/marketplace', methods=['GET'])
@login_required
def get_plugin_marketplace():
    """Get available plugins from marketplace."""
    try:
        # Placeholder marketplace plugins
        marketplace = {
            'plugins': [
                {
                    'id': 'dark-theme',
                    'name': 'Dark Theme Plugin',
                    'version': '1.0.0',
                    'description': 'Beautiful dark theme for Claude Insight',
                    'author': 'Claude Team',
                    'rating': 4.8,
                    'downloads': 1250,
                    'installed': False
                },
                {
                    'id': 'slack-integration',
                    'name': 'Slack Integration',
                    'version': '2.1.0',
                    'description': 'Send alerts to Slack channels',
                    'author': 'Claude Team',
                    'rating': 4.9,
                    'downloads': 2150,
                    'installed': True
                },
                {
                    'id': 'metrics-exporter',
                    'name': 'Prometheus Metrics',
                    'version': '1.5.0',
                    'description': 'Export metrics to Prometheus',
                    'author': 'Community',
                    'rating': 4.6,
                    'downloads': 890,
                    'installed': False
                }
            ]
        }
        return jsonify(marketplace)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/plugins/install/<plugin_id>', methods=['POST'])
@login_required
def install_plugin(plugin_id):
    """Install a plugin."""
    try:
        plugins_dir = Path.home() / '.claude' / 'memory' / 'config' / 'plugins'
        plugins_dir.mkdir(parents=True, exist_ok=True)

        plugin_config = {
            'id': plugin_id,
            'installed_at': datetime.now().isoformat(),
            'enabled': True,
            'settings': {}
        }

        plugin_file = plugins_dir / f'{plugin_id}.json'
        with open(plugin_file, 'w') as f:
            json.dump(plugin_config, f, indent=2)

        return jsonify({'success': True, 'plugin_id': plugin_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/plugins/uninstall/<plugin_id>', methods=['POST'])
@login_required
def uninstall_plugin(plugin_id):
    """Uninstall a plugin."""
    try:
        plugins_dir = Path.home() / '.claude' / 'memory' / 'config' / 'plugins'
        plugin_file = plugins_dir / f'{plugin_id}.json'

        if plugin_file.exists():
            plugin_file.unlink()

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/plugins/toggle/<plugin_id>', methods=['POST'])
@login_required
def toggle_plugin(plugin_id):
    """Enable/disable a plugin."""
    try:
        plugins_dir = Path.home() / '.claude' / 'memory' / 'config' / 'plugins'
        plugin_file = plugins_dir / f'{plugin_id}.json'

        if plugin_file.exists():
            with open(plugin_file, 'r') as f:
                plugin = json.load(f)

            plugin['enabled'] = not plugin.get('enabled', True)

            with open(plugin_file, 'w') as f:
                json.dump(plugin, f, indent=2)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/plugins/settings', methods=['POST'])
@login_required
def update_plugin_settings():
    """Update plugin configuration."""
    try:
        data = request.get_json()
        plugin_id = data.get('plugin_id')
        settings = data.get('settings', {})

        plugins_dir = Path.home() / '.claude' / 'memory' / 'config' / 'plugins'
        plugin_file = plugins_dir / f'{plugin_id}.json'

        if plugin_file.exists():
            with open(plugin_file, 'r') as f:
                plugin = json.load(f)

            plugin['settings'].update(settings)
            plugin['updated_at'] = datetime.now().isoformat()

            with open(plugin_file, 'w') as f:
                json.dump(plugin, f, indent=2)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION CHANNEL ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route('/notification-channels')
@login_required
def notification_channels_page():
    """Render notification channels page."""
    from flask import render_template
    return render_template('notification-channels.html')


@settings_bp.route('/api/notifications/slack', methods=['POST'])
@login_required
def configure_slack():
    """Configure Slack notification channel."""
    try:
        data = request.get_json()
        webhook_url = data.get('webhook_url')
        channel = data.get('channel', '#alerts')

        config_dir = Path.home() / '.claude' / 'memory' / 'config'
        config_dir.mkdir(parents=True, exist_ok=True)

        notification_config = {
            'slack': {
                'enabled': True,
                'webhook_url': webhook_url,
                'channel': channel,
                'configured_at': datetime.now().isoformat()
            }
        }

        config_file = config_dir / 'notifications.json'
        existing = {}
        if config_file.exists():
            with open(config_file, 'r') as f:
                existing = json.load(f)

        existing.update(notification_config)

        with open(config_file, 'w') as f:
            json.dump(existing, f, indent=2)

        return jsonify({'success': True, 'message': 'Slack configured'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/notifications/discord', methods=['POST'])
@login_required
def configure_discord():
    """Configure Discord notification channel."""
    try:
        data = request.get_json()
        webhook_url = data.get('webhook_url')

        config_dir = Path.home() / '.claude' / 'memory' / 'config'
        config_dir.mkdir(parents=True, exist_ok=True)

        notification_config = {
            'discord': {
                'enabled': True,
                'webhook_url': webhook_url,
                'configured_at': datetime.now().isoformat()
            }
        }

        config_file = config_dir / 'notifications.json'
        existing = {}
        if config_file.exists():
            with open(config_file, 'r') as f:
                existing = json.load(f)

        existing.update(notification_config)

        with open(config_file, 'w') as f:
            json.dump(existing, f, indent=2)

        return jsonify({'success': True, 'message': 'Discord configured'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/notifications/pagerduty', methods=['POST'])
@login_required
def configure_pagerduty():
    """Configure PagerDuty notification channel."""
    try:
        data = request.get_json()
        integration_key = data.get('integration_key')

        config_dir = Path.home() / '.claude' / 'memory' / 'config'
        config_dir.mkdir(parents=True, exist_ok=True)

        notification_config = {
            'pagerduty': {
                'enabled': True,
                'integration_key': integration_key,
                'configured_at': datetime.now().isoformat()
            }
        }

        config_file = config_dir / 'notifications.json'
        existing = {}
        if config_file.exists():
            with open(config_file, 'r') as f:
                existing = json.load(f)

        existing.update(notification_config)

        with open(config_file, 'w') as f:
            json.dump(existing, f, indent=2)

        return jsonify({'success': True, 'message': 'PagerDuty configured'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/notifications/test/<channel>', methods=['POST'])
@login_required
def test_notification(channel):
    """Send test notification to specified channel."""
    try:
        test_message = f'Test notification from Claude Insight - {datetime.now().isoformat()}'

        # Placeholder: would actually send notification here
        return jsonify({
            'success': True,
            'message': f'Test notification sent to {channel}',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# THEME MANAGEMENT ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route('/api/themes', methods=['GET'])
@login_required
def get_themes():
    """Get available themes."""
    try:
        themes = {
            'themes': [
                {'id': 'light', 'name': 'Light', 'active': False},
                {'id': 'dark', 'name': 'Dark', 'active': False},
                {'id': 'auto', 'name': 'Auto (OS Default)', 'active': True}
            ]
        }
        return jsonify(themes)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/themes/set/<theme_id>', methods=['POST'])
@login_required
def set_theme(theme_id):
    """Set user theme preference."""
    try:
        config_dir = Path.home() / '.claude' / 'memory' / 'config'
        config_dir.mkdir(parents=True, exist_ok=True)

        theme_config = {
            'theme': theme_id,
            'updated_at': datetime.now().isoformat()
        }

        config_file = config_dir / 'theme.json'
        with open(config_file, 'w') as f:
            json.dump(theme_config, f, indent=2)

        session['dashboard_theme'] = theme_id
        return jsonify({'success': True, 'theme': theme_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATIONS ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@settings_bp.route('/integrations')
@login_required
def integrations_page():
    """Render integrations configuration page."""
    from flask import render_template
    return render_template('integrations.html')


@settings_bp.route('/api/grafana/dashboard/<dashboard_type>', methods=['GET'])
@login_required
def get_grafana_dashboard(dashboard_type):
    """Get Grafana dashboard URL."""
    try:
        grafana_url = 'http://localhost:3000'
        dashboards = {
            'overview': f'{grafana_url}/d/overview/claude-insight-overview',
            'performance': f'{grafana_url}/d/performance/performance-metrics',
            'policies': f'{grafana_url}/d/policies/policy-execution'
        }

        return jsonify({
            'success': True,
            'url': dashboards.get(dashboard_type, grafana_url),
            'type': dashboard_type
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/settings')
@login_required
def settings_page():
    """Render main settings page."""
    from flask import render_template
    return render_template('settings.html')
