from __future__ import annotations

import urllib.request

import pytest

from moltex_harness.network import PublicNetworkPolicy, PublicRedirectHandler


PUBLIC = "93.184.216.34"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.1.2.3/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://localhost/",
    ],
)
def test_policy_rejects_non_public_literal_destinations(url: str) -> None:
    with pytest.raises(ValueError, match="not public|non-public"):
        PublicNetworkPolicy().require_public(url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user@example.com/",
        "https://user:password@example.com/",
        " https://example.com/",
        "https://example.com:99999/",
    ],
)
def test_policy_rejects_invalid_or_credentialed_urls(url: str) -> None:
    with pytest.raises(ValueError):
        PublicNetworkPolicy(lambda _host, _port: (PUBLIC,)).require_public(url)


def test_policy_accepts_only_when_every_dns_result_is_public() -> None:
    clean = PublicNetworkPolicy(lambda host, port: (PUBLIC,))
    validated = clean.require_public("https://example.com/path")
    assert validated.hostname == "example.com"
    assert validated.port == 443

    rebinding = PublicNetworkPolicy(lambda host, port: (PUBLIC, "127.0.0.1"))
    with pytest.raises(ValueError, match="non-public"):
        rebinding.require_public("https://example.com/path")


def test_redirect_handler_validates_before_following_redirect() -> None:
    policy = PublicNetworkPolicy(lambda host, port: (PUBLIC,))
    handler = PublicRedirectHandler(policy)
    request = urllib.request.Request("https://example.com/")

    with pytest.raises(ValueError, match="non-public"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "http://169.254.169.254/latest/meta-data/",
        )
