"""
Claude Credentials Routes for Claude Insight Dashboard.

Provides Flask Blueprint routes for managing Anthropic API credentials and
controlling automatic session tracking. All credential data is stored and
retrieved via ClaudeCredentialsManager which encrypts the API key at rest.

Routes:
    GET  /claude-credentials                    - Credentials management UI
    POST /api/claude/credentials/save           - Save/update API key
    POST /api/claude/credentials/test           - Test API connectivity
    POST /api/claude/credentials/delete         - Remove stored credentials
    GET  /api/claude/credentials/status         - Current credential status
    POST /api/claude/auto-tracking/enable       - Enable auto session tracking
    POST /api/claude/auto-tracking/disable      - Disable auto session tracking
    GET  /api/claude/auto-tracking/status       - Auto-tracking status
    POST /api/claude/sessions/sync              - Manually trigger session sync
    GET  /api/claude/login-info                 - Anthropic login helper URLs
"""

from flask import Blueprint, request, jsonify, render_template, session
from services.claude_integration import (
    credentials_manager,
    ClaudeAPIClient,
    auto_tracker,
    login_helper
)

claude_creds_bp = Blueprint('claude_credentials', __name__)


@claude_creds_bp.route('/claude-credentials')
def credentials_page():
    """Render the Claude credentials management page.

    HTTP Method: GET
    Route: /claude-credentials

    Retrieves the current credential status and auto-tracking state, then
    renders the credentials template with that context.

    Returns:
        str: Rendered HTML for the claude_credentials.html template.
    """
    has_creds = credentials_manager.has_credentials()
    credentials = credentials_manager.get_credentials() if has_creds else None
    tracking_status = auto_tracker.get_tracking_status()

    return render_template('claude_credentials.html',
                         has_credentials=has_creds,
                         credentials=credentials,
                         tracking_status=tracking_status,
                         setup_instructions=login_helper.get_setup_instructions())

@claude_creds_bp.route('/api/claude/credentials/save', methods=['POST'])
def save_credentials():
    """
    Save Anthropic API credentials
    ---
    parameters:
      - name: api_key
        in: body
        required: true
        schema:
          type: object
          properties:
            api_key:
              type: string
            user_email:
              type: string
    responses:
      200:
        description: Credentials saved successfully
      400:
        description: Invalid input
    """
    try:
        data = request.get_json()
        api_key = data.get('api_key', '').strip()
        user_email = data.get('user_email', '').strip()

        if not api_key:
            return jsonify({
                'success': False,
                'message': 'API key is required'
            }), 400

        # Validate API key format
        if not api_key.startswith('sk-ant-'):
            return jsonify({
                'success': False,
                'message': 'Invalid API key format. Anthropic keys start with "sk-ant-"'
            }), 400

        # Test connection
        client = ClaudeAPIClient(api_key)
        test_result = client.test_connection()

        if not test_result['success']:
            return jsonify({
                'success': False,
                'message': f"API key test failed: {test_result['message']}"
            }), 400

        # Save credentials
        credentials_manager.save_api_key(api_key, user_email)

        return jsonify({
            'success': True,
            'message': 'Credentials saved successfully!',
            'test_result': test_result
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error saving credentials: {str(e)}'
        }), 500

@claude_creds_bp.route('/api/claude/credentials/test', methods=['POST'])
def test_credentials():
    """
    Test Claude API connection
    ---
    responses:
      200:
        description: Connection test result
    """
    try:
        client = ClaudeAPIClient()

        if not client.api_key:
            return jsonify({
                'success': False,
                'message': 'No API key configured. Please add your Anthropic API key first.'
            }), 400

        test_result = client.test_connection()

        return jsonify(test_result), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Test failed: {str(e)}'
        }), 500

@claude_creds_bp.route('/api/claude/credentials/delete', methods=['POST'])
def delete_credentials():
    """
    Delete stored credentials
    ---
    responses:
      200:
        description: Credentials deleted
    """
    try:
        credentials_manager.delete_credentials()

        return jsonify({
            'success': True,
            'message': 'Credentials deleted successfully'
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error deleting credentials: {str(e)}'
        }), 500

@claude_creds_bp.route('/api/claude/credentials/status', methods=['GET'])
def credentials_status():
    """
    Get credentials status
    ---
    responses:
      200:
        description: Credentials status
    """
    try:
        has_creds = credentials_manager.has_credentials()
        credentials = credentials_manager.get_credentials() if has_creds else None

        if has_creds and credentials:
            client = ClaudeAPIClient()
            account_info = client.get_account_info()

            return jsonify({
                'has_credentials': True,
                'user_email': credentials.get('user_email'),
                'saved_at': credentials.get('saved_at'),
                'api_key_masked': account_info.get('api_key_masked'),
                'api_key_valid': account_info.get('api_key_valid')
            }), 200
        else:
            return jsonify({
                'has_credentials': False
            }), 200

    except Exception as e:
        return jsonify({
            'error': str(e),
            'has_credentials': False
        }), 500

@claude_creds_bp.route('/api/claude/auto-tracking/enable', methods=['POST'])
def enable_auto_tracking():
    """
    Enable automatic session tracking
    ---
    parameters:
      - name: interval_minutes
        in: body
        schema:
          type: object
          properties:
            interval_minutes:
              type: integer
              default: 5
    responses:
      200:
        description: Auto-tracking enabled
    """
    try:
        data = request.get_json() or {}
        interval = data.get('interval_minutes', 5)

        config = auto_tracker.enable_auto_tracking(interval)

        return jsonify({
            'success': True,
            'message': 'Auto-tracking enabled',
            'config': config
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error enabling auto-tracking: {str(e)}'
        }), 500

@claude_creds_bp.route('/api/claude/auto-tracking/disable', methods=['POST'])
def disable_auto_tracking():
    """
    Disable automatic session tracking
    ---
    responses:
      200:
        description: Auto-tracking disabled
    """
    try:
        config = auto_tracker.disable_auto_tracking()

        return jsonify({
            'success': True,
            'message': 'Auto-tracking disabled',
            'config': config
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error disabling auto-tracking: {str(e)}'
        }), 500

@claude_creds_bp.route('/api/claude/auto-tracking/status', methods=['GET'])
def auto_tracking_status():
    """
    Get auto-tracking status
    ---
    responses:
      200:
        description: Auto-tracking status
    """
    try:
        status = auto_tracker.get_tracking_status()

        return jsonify(status), 200

    except Exception as e:
        return jsonify({
            'error': str(e),
            'enabled': False
        }), 500

@claude_creds_bp.route('/api/claude/sessions/sync', methods=['POST'])
def sync_sessions():
    """
    Manually sync sessions
    ---
    responses:
      200:
        description: Sessions synced
    """
    try:
        result = auto_tracker.sync_sessions()

        return jsonify(result), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Sync failed: {str(e)}'
        }), 500

@claude_creds_bp.route('/api/claude/login-info', methods=['GET'])
def login_info():
    """
    Get Anthropic login information
    ---
    responses:
      200:
        description: Login information and instructions
    """
    try:
        return jsonify({
            'console_url': login_helper.get_login_url(),
            'api_keys_url': login_helper.get_api_keys_url(),
            'setup_instructions': login_helper.get_setup_instructions()
        }), 200

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500
