"""URL validation utilities to prevent SSRF attacks."""

import ipaddress
import socket
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_BLOCKED_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_webhook_url(url: str) -> tuple[bool, str]:
    """Validate a webhook URL is safe to make requests to.

    Checks that the URL:
    - Uses http or https scheme
    - Has a valid hostname
    - Does not resolve to private/internal IP ranges

    Returns:
        Tuple of (is_valid, error_message). error_message is empty when valid.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"

    if parsed.scheme not in ("http", "https"):
        return False, f"URL scheme must be http or https, got: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL has no hostname"

    # Resolve hostname to IP(s) and check against blocked ranges
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False, f"Cannot resolve hostname: {hostname}"

    for _, _, _, _, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        for blocked in _BLOCKED_RANGES:
            if ip in blocked:
                return False, f"URL resolves to blocked IP range: {blocked}"

    return True, ""
