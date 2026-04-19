"""
Claude/Anthropic API Integration Service.

Provides credential management, API connectivity testing, and automatic
session tracking for the Claude Insight dashboard. Credentials are
encrypted at rest using Fernet symmetric encryption.

Classes:
    ClaudeCredentialsManager: Securely stores and retrieves Anthropic API keys.
    ClaudeAPIClient: HTTP client for the Anthropic Messages API.
    AutoSessionTracker: Manages automatic session tracking configuration.
    LoginHelper: Provides Anthropic login URL and setup instructions.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from cryptography.fernet import Fernet

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.path_resolver import get_config_dir, get_sessions_dir


class ClaudeCredentialsManager:
    """Manage Anthropic API credentials securely with Fernet encryption.

    Stores the API key in an encrypted file (claude_credentials.enc) in the
    application config directory. The symmetric encryption key is stored in a
    separate file (.encryption_key) with restrictive file permissions (0o600).

    Attributes:
        config_dir (Path): Config directory resolved by PathResolver.
        credentials_file (Path): Encrypted credentials file path.
        key_file (Path): Fernet encryption key file path.
        cipher (Fernet): Initialized Fernet cipher instance for encrypt/decrypt.
    """

    def __init__(self):
        """Initialize ClaudeCredentialsManager and set up Fernet encryption.

        Creates the config directory if needed, generates a new encryption key
        on first run (stored at .encryption_key with 0o600 permissions), and
        loads the cipher for subsequent operations.
        """
        self.config_dir = get_config_dir()
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.credentials_file = self.config_dir / "claude_credentials.enc"
        self.key_file = self.config_dir / ".encryption_key"

        # Initialize encryption
        self._init_encryption()

    def _init_encryption(self):
        """Initialize the Fernet encryption cipher.

        Generates a new key if .encryption_key does not exist (first run) with
        file permissions set to 0o600 (owner read/write only). Loads the key
        and creates the Fernet cipher instance.

        Returns:
            None
        """
        if not self.key_file.exists():
            # Generate new key
            key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(key)
            # Set file permissions (owner only)
            os.chmod(self.key_file, 0o600)

        with open(self.key_file, "rb") as f:
            self.cipher = Fernet(f.read())

    def save_api_key(self, api_key, user_email=None):
        """Encrypt and persist the Anthropic API key to disk.

        Stores the key along with optional user email, a timestamp, and
        status='active' in a JSON blob that is Fernet-encrypted before
        being written. File permissions are set to 0o600.

        Args:
            api_key (str): Anthropic API key (should start with 'sk-ant-').
            user_email (str or None): Associated user email address. Optional.

        Returns:
            bool: True on success.
        """
        credentials = {
            "api_key": api_key,
            "user_email": user_email,
            "saved_at": datetime.now().isoformat(),
            "status": "active",
        }

        # Encrypt credentials
        encrypted_data = self.cipher.encrypt(json.dumps(credentials).encode())

        with open(self.credentials_file, "wb") as f:
            f.write(encrypted_data)

        # Set file permissions
        os.chmod(self.credentials_file, 0o600)

        return True

    def get_api_key(self):
        """Decrypt and return the stored API key.

        Returns:
            str or None: The decrypted Anthropic API key string, or None if
                the credentials file does not exist or cannot be decrypted.
        """
        if not self.credentials_file.exists():
            return None

        try:
            with open(self.credentials_file, "rb") as f:
                encrypted_data = f.read()

            decrypted_data = self.cipher.decrypt(encrypted_data)
            credentials = json.loads(decrypted_data.decode())

            return credentials.get("api_key")
        except (IOError, json.JSONDecodeError, KeyError, ValueError):
            return None

    def get_credentials(self):
        """Decrypt and return the full credentials dictionary.

        Returns:
            dict or None: Credentials dict with keys api_key, user_email,
                saved_at, status; or None on failure.
        """
        if not self.credentials_file.exists():
            return None

        try:
            with open(self.credentials_file, "rb") as f:
                encrypted_data = f.read()

            decrypted_data = self.cipher.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except (IOError, json.JSONDecodeError, ValueError):
            return None

    def delete_credentials(self):
        """Delete the encrypted credentials file from disk.

        Returns:
            bool: True always (whether the file existed or not).
        """
        if self.credentials_file.exists():
            self.credentials_file.unlink()
        return True

    def has_credentials(self):
        """Check whether encrypted credentials are stored on disk.

        Returns:
            bool: True if the credentials file exists, False otherwise.
        """
        return self.credentials_file.exists()


class ClaudeAPIClient:
    """HTTP client for the Anthropic Messages API.

    Provides connectivity testing and masked API key display. Automatically
    loads the stored API key via ClaudeCredentialsManager if no key is
    provided at construction time.

    Attributes:
        api_key (str or None): Anthropic API key in use.
        base_url (str): Anthropic API base URL.
        headers (dict): Default HTTP request headers including x-api-key.
    """

    def __init__(self, api_key=None):
        """Initialize ClaudeAPIClient.

        Args:
            api_key (str or None): Explicit API key. If None, the key is
                loaded from ClaudeCredentialsManager.
        """
        self.api_key = api_key or self._get_stored_api_key()
        self.base_url = "https://api.anthropic.com/v1"
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _get_stored_api_key(self):
        """Load the API key from ClaudeCredentialsManager.

        Returns:
            str or None: The stored API key, or None if no credentials exist.
        """
        manager = ClaudeCredentialsManager()
        return manager.get_api_key()

    def test_connection(self):
        """Test connectivity to the Anthropic Messages API.

        Sends a minimal 10-token request to claude-3-haiku-20240307 to verify
        that the API key is valid and the service is reachable.

        Returns:
            dict: Result with keys:
                success (bool): True if HTTP 200 was received.
                message (str): Human-readable status message.
                model (str): Model name used for the test (on success).
                error (str): Raw error body or exception message (on failure).
        """
        try:
            # Test with a simple message
            response = requests.post(
                f"{self.base_url}/messages",
                headers=self.headers,
                json={
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
                timeout=10,
            )

            if response.status_code == 200:
                return {"success": True, "message": "API connection successful!", "model": "claude-3-haiku-20240307"}
            else:
                return {"success": False, "message": f"API error: {response.status_code}", "error": response.text}
        except Exception as e:
            return {"success": False, "message": f"Connection failed: {str(e)}", "error": str(e)}

    def get_account_info(self):
        """Return account information including API key validity and masked key.

        Note: The Anthropic API does not yet provide an account info endpoint.
        This is a placeholder that tests connectivity and masks the key for safe
        display.

        Returns:
            dict: With keys:
                api_key_valid (bool): True if test_connection() succeeds.
                api_key_masked (str or None): Partially masked key for display.
        """
        # Note: Anthropic API doesn't have account info endpoint yet
        # This is a placeholder for future implementation
        return {
            "api_key_valid": self.test_connection()["success"],
            "api_key_masked": self._mask_api_key(self.api_key) if self.api_key else None,
        }

    def _mask_api_key(self, api_key):
        """Return a masked version of the API key safe for display.

        Shows the first 8 and last 4 characters with '...' in between.

        Args:
            api_key (str): The full API key string.

        Returns:
            str: Masked key (e.g. 'sk-ant-a...1234'), or '***' if the key
                is too short or None.
        """
        if not api_key or len(api_key) < 10:
            return "***"
        return f"{api_key[:8]}...{api_key[-4:]}"


class AutoSessionTracker:
    """Manage automatic Claude session tracking configuration.

    Reads and writes an auto_tracking.json config file to toggle session
    syncing and record last sync timestamps. Actual session syncing from the
    Anthropic API is a placeholder pending API endpoint availability.

    Attributes:
        sessions_dir (Path): Sessions directory resolved by PathResolver.
        auto_tracking_config (Path): Path to auto_tracking.json config file.
    """

    def __init__(self):
        """Initialize AutoSessionTracker with resolved directory paths."""
        self.sessions_dir = get_sessions_dir()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.auto_tracking_config = get_config_dir() / "auto_tracking.json"

    def enable_auto_tracking(self, interval_minutes=5):
        """Enable automatic session tracking and persist the configuration.

        Args:
            interval_minutes (int): Polling interval in minutes. Defaults to 5.

        Returns:
            dict: The written config dict with keys:
                enabled (bool): True.
                interval_minutes (int): The configured interval.
                last_sync (None): Reset to None on enable.
                enabled_at (str): ISO timestamp when enabled.
        """
        config = {
            "enabled": True,
            "interval_minutes": interval_minutes,
            "last_sync": None,
            "enabled_at": datetime.now().isoformat(),
        }

        with open(self.auto_tracking_config, "w") as f:
            json.dump(config, f, indent=2)

        return config

    def disable_auto_tracking(self):
        """Disable automatic session tracking and persist the configuration.

        Returns:
            dict: The written config dict with keys:
                enabled (bool): False.
                disabled_at (str): ISO timestamp when disabled.
        """
        config = {"enabled": False, "disabled_at": datetime.now().isoformat()}

        with open(self.auto_tracking_config, "w") as f:
            json.dump(config, f, indent=2)

        return config

    def get_tracking_status(self):
        """Read and return the current auto-tracking configuration.

        Returns:
            dict: Config dict with at minimum an 'enabled' (bool) key.
                Returns ``{'enabled': False}`` if the config file does not
                exist or cannot be parsed.
        """
        if not self.auto_tracking_config.exists():
            return {"enabled": False}

        try:
            with open(self.auto_tracking_config, "r") as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            return {"enabled": False}

    def sync_sessions(self):
        """Trigger a manual session sync from the Anthropic API.

        Note: This is a placeholder implementation. The Anthropic API does not
        yet provide a session history endpoint. When called, updates the
        last_sync timestamp in the tracking config to simulate a sync.

        Returns:
            dict: With keys:
                success (bool): True if an API key is configured.
                message (str): Human-readable status.
                synced_at (str): ISO timestamp of the sync (on success).
        """
        # Check if API key is available
        manager = ClaudeCredentialsManager()
        api_key = manager.get_api_key()

        if not api_key:
            return {"success": False, "message": "No API key configured"}

        # Update last sync time
        config = self.get_tracking_status()
        config["last_sync"] = datetime.now().isoformat()

        with open(self.auto_tracking_config, "w") as f:
            json.dump(config, f, indent=2)

        return {"success": True, "message": "Sessions synced successfully", "synced_at": config["last_sync"]}


class AnthropicLoginHelper:
    """Provide Anthropic console login URLs and onboarding setup instructions.

    Used by the credentials page to guide users through obtaining and
    configuring their Anthropic API key.

    Attributes:
        anthropic_console_url (str): Root Anthropic console URL.
        api_keys_url (str): Direct URL to the API keys settings page.
    """

    def __init__(self):
        """Initialize AnthropicLoginHelper with Anthropic console URLs."""
        self.anthropic_console_url = "https://console.anthropic.com"
        self.api_keys_url = f"{self.anthropic_console_url}/settings/keys"

    def get_login_url(self):
        """Return the Anthropic console login URL.

        Returns:
            str: URL string for https://console.anthropic.com.
        """
        return self.anthropic_console_url

    def get_api_keys_url(self):
        """Return the Anthropic API keys settings page URL.

        Returns:
            str: URL string for the API keys settings page.
        """
        return self.api_keys_url

    def get_setup_instructions(self):
        """Return a structured step-by-step API key setup guide.

        Returns:
            dict: Setup guide with keys:
                steps (list[dict]): Ordered setup steps, each with:
                    step (int): Step number.
                    title (str): Short step title.
                    description (str): Detailed instruction text.
                    url (str, optional): Relevant URL for the step.
                    important (bool, optional): Flag for critical steps.
                notes (list[str]): Additional guidance notes.
        """
        return {
            "steps": [
                {
                    "step": 1,
                    "title": "Login to Anthropic Console",
                    "description": "Go to console.anthropic.com and login with your account",
                    "url": self.anthropic_console_url,
                },
                {
                    "step": 2,
                    "title": "Navigate to API Keys",
                    "description": 'Click on "Settings" -> "API Keys"',
                    "url": self.api_keys_url,
                },
                {
                    "step": 3,
                    "title": "Create New API Key",
                    "description": 'Click "Create Key" button and give it a name (e.g., "Claude Insight")',
                    "url": self.api_keys_url,
                },
                {
                    "step": 4,
                    "title": "Copy API Key",
                    "description": 'Copy the generated API key (starts with "sk-ant-")',
                    "important": True,
                },
                {
                    "step": 5,
                    "title": "Add to Claude Insight",
                    "description": 'Paste the API key in Claude Insight settings and click "Save"',
                    "important": True,
                },
            ],
            "notes": [
                "[WARN] Never share your API key with anyone",
                "[lock] API key is stored encrypted on your machine",
                "[OK] You can revoke the key anytime from Anthropic Console",
                "[hint] One API key is enough for all Claude Insight features",
            ],
        }


# Global instances
credentials_manager = ClaudeCredentialsManager()
auto_tracker = AutoSessionTracker()
login_helper = AnthropicLoginHelper()
