"""Secrets validation and rotation hint system.

Validates that all required environment variables are set at pipeline startup.
Provides optional AWS Secrets Manager integration via boto3 (optional dep).

Usage:
    from scripts.langgraph_engine.secrets_manager import validate_secrets
    validate_secrets()  # raises SecretsMissingError if required keys absent
"""

import logging
import os
import threading
from datetime import date, datetime

logger = logging.getLogger(__name__)

# Required secrets: pipeline cannot start without these
REQUIRED_SECRETS = ["ANTHROPIC_API_KEY", "GITHUB_TOKEN"]

# Optional secrets: warn if present but empty, silently skip if absent
OPTIONAL_SECRETS = ["JIRA_API_TOKEN", "SENTRY_DSN", "DD_API_KEY"]

# Thread lock for load_from_aws_secrets_manager (protects os.environ mutation)
_aws_load_lock = threading.Lock()


class SecretsMissingError(Exception):
    """Raised when one or more required secrets are absent from the environment.

    Attributes:
        missing_keys: List of environment variable names that were not found
                      or were present but empty.
    """

    def __init__(self, missing_keys):
        # type: (list) -> None
        self.missing_keys = missing_keys
        key_list = ", ".join(missing_keys)
        super(SecretsMissingError, self).__init__("Required secrets missing or empty: " + key_list)


def validate_secrets():
    # type: () -> None
    """Check all REQUIRED_SECRETS are present and non-empty in os.environ.

    Also logs WARNING for any OPTIONAL_SECRETS that are explicitly set to
    an empty string (present but blank is likely a misconfiguration).

    Raises:
        SecretsMissingError: If any required key is absent or empty.
    """
    missing = []
    for key in REQUIRED_SECRETS:
        value = os.environ.get(key, "")
        if not value:
            missing.append(key)

    if missing:
        raise SecretsMissingError(missing)

    # Warn about optional secrets that are set but empty
    for key in OPTIONAL_SECRETS:
        if key in os.environ and not os.environ[key]:
            logger.warning(
                "Optional secret %s is set but empty; this may indicate a "
                "misconfiguration. Remove the variable or set a valid value.",
                key,
            )

    logger.debug(
        "Secrets validation passed. Required keys present: %s",
        ", ".join(REQUIRED_SECRETS),
    )


def rotate_key_hint():
    # type: () -> None
    """Emit a WARNING if ANTHROPIC_API_KEY is approaching expiry.

    Reads the ANTHROPIC_KEY_EXPIRY environment variable (ISO date string,
    e.g. '2026-04-15') and logs a warning if the key expires within 7 days.
    Silently does nothing if ANTHROPIC_KEY_EXPIRY is not set or cannot be
    parsed.
    """
    expiry_str = os.environ.get("ANTHROPIC_KEY_EXPIRY", "")
    if not expiry_str:
        return

    try:
        expiry_date = date.fromisoformat(expiry_str)
    except ValueError:
        logger.debug(
            "ANTHROPIC_KEY_EXPIRY value '%s' is not a valid ISO date string; " "skipping rotation hint.",
            expiry_str,
        )
        return

    today = datetime.utcnow().date()
    days_remaining = (expiry_date - today).days

    if days_remaining <= 7:
        logger.warning(
            "ANTHROPIC_API_KEY expires in %d day(s) (on %s), schedule rotation.",
            days_remaining,
            expiry_str,
        )
    else:
        logger.debug(
            "ANTHROPIC_API_KEY expiry check: %d days remaining.",
            days_remaining,
        )


def load_from_aws_secrets_manager(secret_arn=None):
    # type: (str) -> bool
    """Fetch secrets from AWS Secrets Manager and populate os.environ.

    Only executes when boto3 is installed and AWS_SECRET_ARN is set (either
    via the secret_arn argument or the AWS_SECRET_ARN environment variable).
    The secret value must be a JSON object whose keys map directly to
    environment variable names.

    Args:
        secret_arn: AWS Secrets Manager ARN to fetch. If None, reads from
                    the AWS_SECRET_ARN environment variable.

    Returns:
        True if secrets were loaded successfully, False otherwise
        (boto3 unavailable, ARN not configured, or fetch failed).
    """
    try:
        import boto3  # optional dependency
        import botocore.exceptions as botocore_exc
    except ImportError:
        logger.debug("boto3 is not installed; skipping AWS Secrets Manager load.")
        return False

    arn = secret_arn or os.environ.get("AWS_SECRET_ARN", "")
    if not arn:
        logger.debug("AWS_SECRET_ARN not configured; skipping AWS Secrets Manager load.")
        return False

    try:
        import json

        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager")

        response = client.get_secret_value(SecretId=arn)
        secret_string = response.get("SecretString", "")

        if not secret_string:
            logger.warning(
                "AWS Secrets Manager returned an empty SecretString for ARN: %s",
                arn,
            )
            return False

        secret_dict = json.loads(secret_string)

        with _aws_load_lock:
            for env_key, env_value in secret_dict.items():
                if isinstance(env_value, str):
                    os.environ[env_key] = env_value
                else:
                    # Convert non-string values to string for os.environ
                    os.environ[env_key] = str(env_value)

        logger.info(
            "Loaded %d secret(s) from AWS Secrets Manager (ARN: ...%s).",
            len(secret_dict),
            arn[-12:],  # log only the last 12 chars of the ARN for safety
        )
        return True

    except botocore_exc.ClientError as exc:
        logger.error("Failed to fetch secrets from AWS Secrets Manager: %s", exc)
        return False
    except ValueError as exc:
        logger.error("AWS Secrets Manager secret is not valid JSON: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error loading from AWS Secrets Manager: %s", exc)
        return False
