"""
API Routes Blueprint for Claude Insight.

Provides comprehensive JSON API endpoints for:
- Metrics: System health, context usage, token tracking
- Policies: Policy execution, compliance, effectiveness
- Logs: Log analysis, error tracking, activity history
- 2FA: Two-factor authentication setup and verification
- Dashboards: Dashboard persistence and management
- Plugins: Plugin lifecycle management
- Notifications: Alert channels and routing
- Exports: Data export in CSV, Excel, PDF formats

All routes return JSON unless explicitly handling file downloads.
Authentication required for most endpoints via login_required decorator.
"""

from flask import Blueprint, jsonify, request, send_file
from functools import wraps
from datetime import datetime, timedelta
import json
import csv
import io
from pathlib import Path

# Create blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')


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
# METRICS API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/metrics', methods=['GET'])
@login_required
def get_metrics():
    """Get current system health metrics with caching."""
    try:
        from services.monitoring.cache_manager import get_cache
        from services.monitoring.metrics_collector import MetricsCollector

        cache = get_cache()
        cached_metrics = cache.get('system_metrics')

        if cached_metrics is not None:
            return jsonify(cached_metrics)

        collector = MetricsCollector()
        metrics = collector.get_system_health()
        cache.set('system_metrics', metrics, ttl=15)

        return jsonify(metrics)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# NOTE: /activity endpoint is defined in app.py line 1314 (api_activity)
# This blueprint route has been removed to avoid duplication
# The app.py route takes precedence and is properly tested


@api_bp.route('/policies', methods=['GET'])
@login_required
def get_policies():
    """Get all active policies with execution statistics."""
    try:
        from services.monitoring.individual_policy_tracker import POLICY_REGISTRY

        policies = []
        for policy_name, policy_data in POLICY_REGISTRY.items():
            policies.append({
                'name': policy_name,
                'level': policy_data.get('level'),
                'status': policy_data.get('status', 'active'),
                'description': policy_data.get('description', ''),
                'last_executed': policy_data.get('last_executed')
            })

        return jsonify({
            'policies': policies,
            'total': len(policies),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/policy-hits', methods=['GET'])
@login_required
def get_policy_hits():
    """Get policy hit statistics and trends."""
    try:
        days = request.args.get('days', 7, type=int)
        start_date = datetime.now() - timedelta(days=days)

        # Load policy hits from log files
        log_dir = Path.home() / '.claude' / 'memory' / 'logs'
        hits_data = {'total': 0, 'by_policy': {}, 'by_day': {}}

        if log_dir.exists():
            policy_log = log_dir / 'policy-hits.log'
            if policy_log.exists():
                with open(policy_log, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            hit_date = datetime.fromisoformat(entry.get('timestamp', ''))
                            if hit_date >= start_date:
                                hits_data['total'] += 1
                                policy = entry.get('policy', 'unknown')
                                hits_data['by_policy'][policy] = hits_data['by_policy'].get(policy, 0) + 1
                        except Exception:
                            continue

        return jsonify(hits_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# LOGS API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/logs/analyze', methods=['POST'])
@login_required
def analyze_logs():
    """Analyze logs for patterns, errors, and anomalies."""
    try:
        data = request.get_json()
        query = data.get('query', '')
        limit = data.get('limit', 100)

        from services.monitoring.log_parser import LogParser
        parser = LogParser()
        results = parser.search_logs(query, limit=limit)

        return jsonify({
            'results': results,
            'query': query,
            'count': len(results)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/log-files', methods=['GET'])
@login_required
def get_log_files():
    """List available log files."""
    try:
        log_dir = Path.home() / '.claude' / 'memory' / 'logs'
        files = []

        if log_dir.exists():
            for log_file in log_dir.glob('*.log'):
                stat = log_file.stat()
                files.append({
                    'name': log_file.name,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'path': str(log_file)
                })

        return jsonify({'log_files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# 2FA API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/2fa/status', methods=['GET'])
@login_required
def check_2fa_status():
    """Check if user has 2FA enabled."""
    try:
        username = request.args.get('user', 'default')
        credentials_file = Path.home() / '.claude' / 'claude_credentials.json'

        if not credentials_file.exists():
            return jsonify({'enabled': False})

        with open(credentials_file, 'r') as f:
            creds = json.load(f)
            user_creds = creds.get(username, {})

        return jsonify({
            'enabled': user_creds.get('2fa_enabled', False),
            'backup_codes_count': len(user_creds.get('backup_codes', []))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/2fa/setup', methods=['POST'])
@login_required
def setup_2fa():
    """Start 2FA setup process and generate QR code."""
    try:
        import pyotp
        import qrcode
        import base64

        username = request.json.get('username', 'default')

        # Generate secret
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)

        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp.provisioning_uri(name=username, issuer_name='Claude Insight'))
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        qr_base64 = base64.b64encode(buf.getvalue()).decode()

        return jsonify({
            'secret': secret,
            'qr_code': f'data:image/png;base64,{qr_base64}',
            'backup_codes': [pyotp.random_base32()[:8] for _ in range(10)]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/2fa/verify-setup', methods=['POST'])
@login_required
def verify_2fa_setup():
    """Verify 2FA setup with TOTP code."""
    try:
        import pyotp

        data = request.get_json()
        secret = data.get('secret')
        code = data.get('code')
        username = data.get('username', 'default')
        backup_codes = data.get('backup_codes', [])

        totp = pyotp.TOTP(secret)

        if not totp.verify(code):
            return jsonify({'success': False, 'error': 'Invalid verification code'}), 400

        # Save to credentials file
        credentials_file = Path.home() / '.claude' / 'claude_credentials.json'
        credentials_file.parent.mkdir(parents=True, exist_ok=True)

        creds = {}
        if credentials_file.exists():
            with open(credentials_file, 'r') as f:
                creds = json.load(f)

        creds[username] = {
            '2fa_enabled': True,
            '2fa_secret': secret,
            'backup_codes': backup_codes,
            'created_at': datetime.now().isoformat()
        }

        with open(credentials_file, 'w') as f:
            json.dump(creds, f, indent=2)

        return jsonify({'success': True, 'message': '2FA setup complete'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/2fa/verify-login', methods=['POST'])
@login_required
def verify_2fa_login():
    """Verify TOTP code during login."""
    try:
        import pyotp

        data = request.get_json()
        code = data.get('code')
        username = data.get('username', 'default')

        credentials_file = Path.home() / '.claude' / 'claude_credentials.json'

        if not credentials_file.exists():
            return jsonify({'success': False, 'error': 'No 2FA configured'}), 400

        with open(credentials_file, 'r') as f:
            creds = json.load(f)

        user_creds = creds.get(username, {})
        secret = user_creds.get('2fa_secret')

        if not secret:
            return jsonify({'success': False, 'error': 'No 2FA configured'}), 400

        totp = pyotp.TOTP(secret)

        if not totp.verify(code):
            return jsonify({'success': False, 'error': 'Invalid verification code'}), 400

        return jsonify({'success': True, 'message': 'Verification successful'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    """Disable 2FA for current user."""
    try:
        username = request.json.get('username', 'default')
        credentials_file = Path.home() / '.claude' / 'claude_credentials.json'

        if credentials_file.exists():
            with open(credentials_file, 'r') as f:
                creds = json.load(f)

            if username in creds:
                creds[username]['2fa_enabled'] = False
                with open(credentials_file, 'w') as f:
                    json.dump(creds, f, indent=2)

        return jsonify({'success': True, 'message': '2FA disabled'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/2fa/activity', methods=['GET'])
@login_required
def get_2fa_activity():
    """Get 2FA activity log."""
    try:
        username = request.args.get('user', 'default')

        activity_file = Path.home() / '.claude' / 'memory' / 'logs' / '2fa-activity.log'
        activities = []

        if activity_file.exists():
            with open(activity_file, 'r') as f:
                for line in f:
                    try:
                        activities.append(json.loads(line.strip()))
                    except Exception:
                        continue

        return jsonify({
            'activities': activities[-50:],  # Last 50
            'username': username
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/dashboards/save', methods=['POST'])
@login_required
def save_dashboard():
    """Save a custom dashboard configuration."""
    try:
        data = request.get_json()
        dashboard_id = data.get('id', 'custom')
        config = data.get('config', {})

        dashboards_dir = Path.home() / '.claude' / 'memory' / 'dashboards'
        dashboards_dir.mkdir(parents=True, exist_ok=True)

        dashboard_file = dashboards_dir / f'{dashboard_id}.json'
        with open(dashboard_file, 'w') as f:
            json.dump({
                'id': dashboard_id,
                'config': config,
                'created': datetime.now().isoformat(),
                'updated': datetime.now().isoformat()
            }, f, indent=2)

        return jsonify({'success': True, 'id': dashboard_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/dashboards/list', methods=['GET'])
@login_required
def list_dashboards():
    """List all saved dashboards."""
    try:
        dashboards_dir = Path.home() / '.claude' / 'memory' / 'dashboards'
        dashboards = []

        if dashboards_dir.exists():
            for dashboard_file in dashboards_dir.glob('*.json'):
                with open(dashboard_file, 'r') as f:
                    dashboard = json.load(f)
                    dashboards.append(dashboard)

        return jsonify({'dashboards': dashboards})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/dashboards/<dashboard_id>', methods=['GET'])
@login_required
def get_dashboard(dashboard_id):
    """Get a specific dashboard configuration."""
    try:
        dashboards_dir = Path.home() / '.claude' / 'memory' / 'dashboards'
        dashboard_file = dashboards_dir / f'{dashboard_id}.json'

        if not dashboard_file.exists():
            return jsonify({'error': 'Dashboard not found'}), 404

        with open(dashboard_file, 'r') as f:
            dashboard = json.load(f)

        return jsonify(dashboard)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/dashboards/<dashboard_id>', methods=['DELETE'])
@login_required
def delete_dashboard(dashboard_id):
    """Delete a dashboard."""
    try:
        dashboards_dir = Path.home() / '.claude' / 'memory' / 'dashboards'
        dashboard_file = dashboards_dir / f'{dashboard_id}.json'

        if dashboard_file.exists():
            dashboard_file.unlink()

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/dashboards/current', methods=['GET'])
@login_required
def get_current_dashboard():
    """Get the current active dashboard."""
    try:
        from flask import session

        dashboard_id = session.get('current_dashboard', 'default')

        dashboards_dir = Path.home() / '.claude' / 'memory' / 'dashboards'
        dashboard_file = dashboards_dir / f'{dashboard_id}.json'

        if dashboard_file.exists():
            with open(dashboard_file, 'r') as f:
                dashboard = json.load(f)
            return jsonify(dashboard)

        return jsonify({'id': 'default', 'config': {}})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/export/csv/<data_type>', methods=['GET'])
@login_required
def export_csv(data_type):
    """Export data to CSV format."""
    try:
        if data_type == 'sessions':
            from utils.history_tracker import HistoryTracker
            tracker = HistoryTracker()
            sessions = tracker.get_all_sessions()
        elif data_type == 'policies':
            from services.monitoring.individual_policy_tracker import POLICY_REGISTRY
            sessions = list(POLICY_REGISTRY.items())
        else:
            return jsonify({'error': 'Invalid export type'}), 400

        output = io.StringIO()
        writer = csv.writer(output)

        if data_type == 'sessions' and sessions:
            writer.writerow(['Session ID', 'Start Time', 'Duration', 'Metrics'])
            for session_data in sessions:
                writer.writerow([
                    session_data.get('id'),
                    session_data.get('start_time'),
                    session_data.get('duration'),
                    json.dumps(session_data.get('metrics', {}))
                ])

        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{data_type}-export.csv'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/session/end', methods=['POST'])
@login_required
def end_session():
    """End the current Claude session."""
    try:
        from flask import session
        session_id = session.get('session_id')

        # Mark session as ended
        sessions_dir = Path.home() / '.claude' / 'memory' / 'sessions'
        if sessions_dir.exists():
            for session_file in sessions_dir.glob('*.json'):
                with open(session_file, 'r') as f:
                    session_data = json.load(f)

                if session_data.get('session_id') == session_id:
                    session_data['ended'] = datetime.now().isoformat()
                    with open(session_file, 'w') as f:
                        json.dump(session_data, f, indent=2)
                    break

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
