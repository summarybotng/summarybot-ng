"""
Google Directory API Client for Group Membership.

ADR-050: Supports service account with domain-wide delegation to check
user group membership for authorization decisions.

Security requirements:
- Service account credentials are optional (graceful degradation)
- Results are cached with configurable TTL
- All API errors are handled gracefully
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class GroupMembershipCache:
    """Thread-safe cache for group membership lookups with TTL."""

    def __init__(self, ttl_seconds: int = 300):
        """Initialize cache with configurable TTL.

        Args:
            ttl_seconds: Time-to-live for cache entries (default 5 minutes)
        """
        self._ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[List[str], datetime]] = {}
        self._lock = threading.Lock()

    def get(self, user_email: str) -> Optional[List[str]]:
        """Get cached groups for a user if not expired.

        Args:
            user_email: Email address of the user

        Returns:
            List of group emails if cached and not expired, None otherwise
        """
        with self._lock:
            entry = self._cache.get(user_email.lower())
            if entry is None:
                return None

            groups, cached_at = entry
            if datetime.utcnow() - cached_at > timedelta(seconds=self._ttl_seconds):
                # Entry expired, remove it
                del self._cache[user_email.lower()]
                return None

            return groups

    def set(self, user_email: str, groups: List[str]) -> None:
        """Cache groups for a user.

        Args:
            user_email: Email address of the user
            groups: List of group emails the user belongs to
        """
        with self._lock:
            self._cache[user_email.lower()] = (groups, datetime.utcnow())

    def invalidate(self, user_email: str) -> None:
        """Invalidate cache entry for a user.

        Args:
            user_email: Email address of the user
        """
        with self._lock:
            self._cache.pop(user_email.lower(), None)

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        """Return number of cached entries."""
        with self._lock:
            return len(self._cache)


class GoogleDirectoryClient:
    """Client for Google Directory API group membership lookups.

    Supports service account with domain-wide delegation. If not configured,
    all methods return empty results (graceful degradation).

    Environment variables:
        GOOGLE_SERVICE_ACCOUNT_JSON: JSON string of service account credentials
        GOOGLE_ADMIN_EMAIL: Admin email for impersonation (required for domain-wide delegation)
        GOOGLE_DIRECTORY_CACHE_TTL: Cache TTL in seconds (default 300)
    """

    def __init__(
        self,
        service_account_json: Optional[str] = None,
        admin_email: Optional[str] = None,
        cache_ttl_seconds: int = 300,
    ):
        """Initialize the Google Directory client.

        Args:
            service_account_json: JSON string of service account credentials
            admin_email: Admin email for impersonation (domain-wide delegation)
            cache_ttl_seconds: Cache TTL in seconds (default 5 minutes)
        """
        self._service_account_json = service_account_json
        self._admin_email = admin_email
        self._cache = GroupMembershipCache(ttl_seconds=cache_ttl_seconds)
        self._service: Optional[object] = None
        self._initialized = False
        self._init_error: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def is_configured(self) -> bool:
        """Check if service account is configured."""
        return bool(self._service_account_json and self._admin_email)

    def _initialize_service(self) -> bool:
        """Initialize the Directory API service.

        Returns:
            True if initialization succeeded, False otherwise
        """
        if self._initialized:
            return self._service is not None

        with self._lock:
            # Double-check after acquiring lock
            if self._initialized:
                return self._service is not None

            self._initialized = True

            if not self.is_configured:
                logger.info("Google Directory API not configured (missing credentials or admin email)")
                return False

            try:
                from google.oauth2 import service_account
                from googleapiclient.discovery import build

                # Parse service account credentials
                try:
                    credentials_info = json.loads(self._service_account_json)
                except json.JSONDecodeError as e:
                    self._init_error = f"Invalid service account JSON: {e}"
                    logger.error(self._init_error)
                    return False

                # Create credentials with domain-wide delegation
                scopes = [
                    "https://www.googleapis.com/auth/admin.directory.group.readonly",
                    "https://www.googleapis.com/auth/admin.directory.group.member.readonly",
                ]

                credentials = service_account.Credentials.from_service_account_info(
                    credentials_info,
                    scopes=scopes,
                )

                # Impersonate admin user for domain-wide delegation
                delegated_credentials = credentials.with_subject(self._admin_email)

                # Build the Directory API service
                self._service = build(
                    "admin",
                    "directory_v1",
                    credentials=delegated_credentials,
                    cache_discovery=False,
                )

                logger.info(f"Google Directory API initialized with admin: {self._admin_email}")
                return True

            except ImportError as e:
                self._init_error = f"Missing required packages: {e}. Install google-auth and google-api-python-client."
                logger.warning(self._init_error)
                return False

            except Exception as e:
                self._init_error = f"Failed to initialize Google Directory API: {e}"
                logger.error(self._init_error)
                return False

    def get_user_groups(self, user_email: str) -> List[str]:
        """Get all groups a user belongs to.

        Args:
            user_email: Email address of the user

        Returns:
            List of group email addresses the user is a member of.
            Returns empty list if not configured or on error.
        """
        if not user_email:
            return []

        # Normalize email
        user_email = user_email.lower().strip()

        # Check cache first
        cached_groups = self._cache.get(user_email)
        if cached_groups is not None:
            logger.debug(f"Cache hit for user groups: {user_email}")
            return cached_groups

        # Initialize service if needed
        if not self._initialize_service():
            # Not configured or initialization failed - graceful degradation
            return []

        try:
            groups = []
            page_token = None

            while True:
                # List groups the user is a member of
                request = self._service.groups().list(
                    userKey=user_email,
                    pageToken=page_token,
                    maxResults=200,  # Max allowed by API
                )
                response = request.execute()

                for group in response.get("groups", []):
                    group_email = group.get("email", "").lower()
                    if group_email:
                        groups.append(group_email)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            # Cache the results
            self._cache.set(user_email, groups)

            logger.debug(f"Fetched {len(groups)} groups for user: {user_email}")
            return groups

        except Exception as e:
            # Log error but don't fail - graceful degradation
            logger.warning(f"Error fetching groups for {user_email}: {e}")
            # Cache empty result to avoid hammering API on repeated failures
            self._cache.set(user_email, [])
            return []

    def is_user_in_group(self, user_email: str, group_email: str) -> bool:
        """Check if a user belongs to a specific group.

        Args:
            user_email: Email address of the user
            group_email: Email address of the group to check

        Returns:
            True if the user is a member of the group, False otherwise.
            Returns False if not configured or on error.
        """
        if not user_email or not group_email:
            return False

        # Normalize emails
        user_email = user_email.lower().strip()
        group_email = group_email.lower().strip()

        # Get all groups and check membership
        user_groups = self.get_user_groups(user_email)
        return group_email in user_groups

    def is_user_in_any_group(self, user_email: str, group_emails: List[str]) -> bool:
        """Check if a user belongs to any of the specified groups.

        Args:
            user_email: Email address of the user
            group_emails: List of group email addresses to check

        Returns:
            True if the user is a member of at least one group, False otherwise.
        """
        if not user_email or not group_emails:
            return False

        # Normalize
        normalized_groups = {g.lower().strip() for g in group_emails if g}

        user_groups = self.get_user_groups(user_email)
        return bool(normalized_groups.intersection(user_groups))

    def invalidate_cache(self, user_email: str) -> None:
        """Invalidate cached groups for a user.

        Useful when you know a user's group membership has changed.

        Args:
            user_email: Email address of the user
        """
        self._cache.invalidate(user_email)

    def clear_cache(self) -> None:
        """Clear all cached group membership data."""
        self._cache.clear()
        logger.info("Google Directory cache cleared")

    @property
    def cache_size(self) -> int:
        """Return number of cached entries."""
        return self._cache.size

    @property
    def initialization_error(self) -> Optional[str]:
        """Return initialization error message if any."""
        return self._init_error


# Global instance
_google_directory_client: Optional[GoogleDirectoryClient] = None


def get_google_directory_client() -> GoogleDirectoryClient:
    """Get or create the global Google Directory client.

    The client is configured from environment variables:
        - GOOGLE_SERVICE_ACCOUNT_JSON: Service account credentials JSON
        - GOOGLE_ADMIN_EMAIL: Admin email for impersonation
        - GOOGLE_DIRECTORY_CACHE_TTL: Cache TTL in seconds (default 300)

    Returns:
        GoogleDirectoryClient instance (may not be configured if env vars missing)
    """
    global _google_directory_client

    if _google_directory_client is None:
        service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        admin_email = os.getenv("GOOGLE_ADMIN_EMAIL")
        cache_ttl = int(os.getenv("GOOGLE_DIRECTORY_CACHE_TTL", "300"))

        _google_directory_client = GoogleDirectoryClient(
            service_account_json=service_account_json,
            admin_email=admin_email,
            cache_ttl_seconds=cache_ttl,
        )

        if _google_directory_client.is_configured:
            logger.info("Google Directory client configured with service account")
        else:
            logger.info(
                "Google Directory client not configured (GOOGLE_SERVICE_ACCOUNT_JSON "
                "and/or GOOGLE_ADMIN_EMAIL not set) - group lookups will return empty"
            )

    return _google_directory_client


def initialize_google_directory() -> None:
    """Initialize Google Directory client at startup.

    Call this during application startup to eagerly initialize the client
    and catch configuration errors early.
    """
    client = get_google_directory_client()

    if client.is_configured:
        # Trigger initialization to catch errors early
        client._initialize_service()

        if client.initialization_error:
            logger.error(f"Google Directory initialization error: {client.initialization_error}")
        else:
            logger.info("Google Directory client initialized successfully")
