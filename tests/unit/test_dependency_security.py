"""Regression tests for security fixes that live in third-party dependencies."""

from pathlib import Path

import certifi
import pytest
from starlette.requests import Request


def _request_with_host(host: str, path: str) -> Request:
    """Build a request whose Host header is attacker-controlled."""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", host.encode())],
        "server": ("testserver", 80),
    }
    return Request(scope)


@pytest.mark.parametrize(
    "host",
    [
        "evil.example/admin?",
        "evil.example/admin#",
        "evil.example/admin/",
    ],
)
def test_forged_host_header_does_not_change_request_path(host: str):
    """A forged Host header must not rewrite request.url.path (BadHost, CVE-2026-48710)."""
    request = _request_with_host(host, "/health")

    assert request.url.path == "/health"


def test_certifi_bundle_excludes_compromised_emsign_root():
    """The emSign ECC Root CA - G3 was removed after the eMudhra key compromise."""
    bundle = Path(certifi.where()).read_text()

    assert "emSign ECC Root CA - G3" not in bundle
