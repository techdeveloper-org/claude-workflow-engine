"""
User Model for Authentication and Authorization.

Defines the User domain object used throughout the Claude Insight monitoring
dashboard. Handles serialization to/from dictionary format, role-based
permission checks, and basic user lifecycle management (last login tracking).

Classes:
    User: Represents an authenticated user with a role and preferences.
"""

from datetime import datetime
from typing import Dict, List, Optional


class User:
    """Represents an authenticated user of the Claude Insight dashboard.

    Stores identity, role, preferences, and lifecycle timestamps. Provides
    helpers for serialization, deserialization, and role-based permission checks.

    Attributes:
        user_id (str): Unique UUID-based identifier auto-generated on creation.
        username (str): Unique login name for the user.
        email (str): User email address.
        role (str): Access role - one of 'admin', 'developer', or 'user'.
        created_at (datetime): Timestamp when the account was created.
        last_login (datetime or None): Timestamp of the most recent login.
        preferences (dict): Arbitrary user preference key-value pairs.
        is_active (bool): Whether the account is active and can log in.
    """

    def __init__(
        self,
        username: str,
        email: str,
        user_id: Optional[str] = None,
        role: str = 'user',
        created_at: Optional[datetime] = None,
        last_login: Optional[datetime] = None,
        preferences: Optional[Dict] = None,
        is_active: bool = True
    ):
        """Initialize a User instance.

        Args:
            username (str): Unique login name.
            email (str): User email address.
            user_id (str or None): Explicit UUID string. If None, a new UUID
                is generated automatically.
            role (str): Access role. Defaults to 'user'. Accepted values are
                'admin', 'developer', and 'user'.
            created_at (datetime or None): Account creation timestamp. Defaults
                to the current UTC time if not provided.
            last_login (datetime or None): Last login timestamp. Defaults to None.
            preferences (dict or None): User preference dictionary. Defaults to
                an empty dict if not provided.
            is_active (bool): Whether the account is enabled. Defaults to True.
        """
        self.user_id = user_id or self._generate_id()
        self.username = username
        self.email = email
        self.role = role
        self.created_at = created_at or datetime.now()
        self.last_login = last_login
        self.preferences = preferences or {}
        self.is_active = is_active

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique UUID string for a new user.

        Returns:
            str: A UUID4 string (e.g. '550e8400-e29b-41d4-a716-446655440000').
        """
        import uuid
        return str(uuid.uuid4())

    def to_dict(self) -> Dict:
        """Serialize the User instance to a JSON-compatible dictionary.

        Datetime fields are converted to ISO 8601 strings. None datetimes
        are serialized as None.

        Returns:
            Dict: Dictionary with keys user_id, username, email, role,
                created_at, last_login, preferences, and is_active.
        """
        return {
            'user_id': self.user_id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'preferences': self.preferences,
            'is_active': self.is_active
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'User':
        """Deserialize a User from a dictionary (e.g. loaded from JSON storage).

        ISO 8601 datetime strings for created_at and last_login are parsed back
        to datetime objects. Missing optional fields are filled with safe defaults.

        Args:
            data (Dict): Dictionary containing at least 'username' and 'email'
                keys. Optional keys: user_id, role, created_at, last_login,
                preferences, is_active.

        Returns:
            User: A fully initialized User instance.
        """
        created_at = datetime.fromisoformat(data['created_at']) if data.get('created_at') else None
        last_login = datetime.fromisoformat(data['last_login']) if data.get('last_login') else None

        return cls(
            user_id=data.get('user_id'),
            username=data['username'],
            email=data['email'],
            role=data.get('role', 'user'),
            created_at=created_at,
            last_login=last_login,
            preferences=data.get('preferences', {}),
            is_active=data.get('is_active', True)
        )

    def update_last_login(self):
        """Set last_login to the current local datetime.

        Should be called immediately after a successful authentication to
        keep the last-login audit trail accurate.

        Returns:
            None
        """
        self.last_login = datetime.now()

    def has_permission(self, permission: str) -> bool:
        """Check whether the user's role grants the requested permission.

        Permission resolution is role-based:
        - 'admin': read, write, delete, manage_users, configure_system
        - 'developer': read, write, create_widgets
        - 'user': read

        Args:
            permission (str): The permission string to check (e.g. 'read',
                'write', 'delete', 'manage_users', 'configure_system',
                'create_widgets').

        Returns:
            bool: True if the user's role includes the requested permission,
                False otherwise.
        """
        # Role-based permissions
        permissions_map = {
            'admin': ['read', 'write', 'delete', 'manage_users', 'configure_system'],
            'developer': ['read', 'write', 'create_widgets'],
            'user': ['read']
        }
        return permission in permissions_map.get(self.role, [])

    def __repr__(self):
        """Return an unambiguous string representation of the User.

        Returns:
            str: String in the format '<User username (role)>'.
        """
        return f"<User {self.username} ({self.role})>"
