"""Tests for src.utils.url_validation — SSRF-prevention checks."""

from unittest.mock import patch

from src.utils.url_validation import validate_webhook_url


# Helper: build a getaddrinfo return value for a single IPv4 address.
def _addrinfo(ip: str):
    return [(2, 1, 6, "", (ip, 0))]


# ── Private / internal range rejections ──────────────────────────


@patch("src.utils.url_validation.socket.getaddrinfo")
def test_rejects_private_10x(mock_getaddrinfo):
    mock_getaddrinfo.return_value = _addrinfo("10.0.0.1")
    valid, msg = validate_webhook_url("https://example.com/hook")
    assert valid is False
    assert "blocked" in msg.lower()


@patch("src.utils.url_validation.socket.getaddrinfo")
def test_rejects_private_172x(mock_getaddrinfo):
    mock_getaddrinfo.return_value = _addrinfo("172.16.0.1")
    valid, msg = validate_webhook_url("https://example.com/hook")
    assert valid is False
    assert "blocked" in msg.lower()


@patch("src.utils.url_validation.socket.getaddrinfo")
def test_rejects_private_192x(mock_getaddrinfo):
    mock_getaddrinfo.return_value = _addrinfo("192.168.1.1")
    valid, msg = validate_webhook_url("https://example.com/hook")
    assert valid is False
    assert "blocked" in msg.lower()


@patch("src.utils.url_validation.socket.getaddrinfo")
def test_rejects_loopback(mock_getaddrinfo):
    mock_getaddrinfo.return_value = _addrinfo("127.0.0.1")
    valid, msg = validate_webhook_url("https://example.com/hook")
    assert valid is False
    assert "blocked" in msg.lower()


@patch("src.utils.url_validation.socket.getaddrinfo")
def test_rejects_metadata_endpoint(mock_getaddrinfo):
    mock_getaddrinfo.return_value = _addrinfo("169.254.169.254")
    valid, msg = validate_webhook_url("http://169.254.169.254/latest/meta-data/")
    assert valid is False
    assert "blocked" in msg.lower()


# ── Scheme validation ────────────────────────────────────────────


def test_rejects_file_scheme():
    valid, msg = validate_webhook_url("file:///etc/passwd")
    assert valid is False
    assert "scheme" in msg.lower()


# ── Happy path ───────────────────────────────────────────────────


@patch("src.utils.url_validation.socket.getaddrinfo")
def test_accepts_public_https_url(mock_getaddrinfo):
    mock_getaddrinfo.return_value = _addrinfo("93.184.216.34")
    valid, msg = validate_webhook_url("https://example.com/webhook")
    assert valid is True
    assert msg == ""
