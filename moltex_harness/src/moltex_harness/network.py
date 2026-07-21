"""Shared outbound public-network policy for untrusted source URLs."""

from __future__ import annotations

import ipaddress
import socket
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit


AddressResolver = Callable[[str, int], Iterable[str]]


@dataclass(frozen=True, slots=True)
class ValidatedPublicUrl:
    url: str
    scheme: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


class PublicNetworkPolicy:
    """Reject non-public destinations before any HTTP or browser request."""

    def __init__(self, resolver: AddressResolver | None = None) -> None:
        self._resolver = resolver or self._resolve

    def require_public(self, url: str) -> ValidatedPublicUrl:
        parsed = self._parse(url)
        hostname = (parsed.hostname or "").rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ValueError(f"Network destination is not public: {url}")
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        values: tuple[str, ...]
        try:
            literal = ipaddress.ip_address(hostname)
            values = (str(literal),)
        except ValueError:
            try:
                values = tuple(dict.fromkeys(self._resolver(hostname, port)))
            except OSError as error:
                raise ValueError(f"Network destination cannot be resolved: {url}") from error
        if not values:
            raise ValueError(f"Network destination cannot be resolved: {url}")
        for value in values:
            address = ipaddress.ip_address(value)
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
                address = address.ipv4_mapped
            if not address.is_global:
                raise ValueError(f"Network destination resolves to a non-public address: {url}")
        return ValidatedPublicUrl(
            url=url,
            scheme=parsed.scheme.lower(),
            hostname=hostname,
            port=port,
            addresses=tuple(sorted(values)),
        )

    @staticmethod
    def origin(url: str) -> tuple[str, str, int]:
        parsed = PublicNetworkPolicy._parse(url)
        scheme = parsed.scheme.lower()
        return (
            scheme,
            (parsed.hostname or "").rstrip(".").lower(),
            parsed.port or (443 if scheme == "https" else 80),
        )

    @staticmethod
    def _parse(url: str) -> SplitResult:
        if not isinstance(url, str) or not url or url != url.strip():
            raise ValueError(f"Network destination must be an absolute public HTTP URL: {url}")
        parsed = urlsplit(url)
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError(f"Network destination has an invalid port: {url}") from error
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError(f"Network destination must be an absolute public HTTP URL: {url}")
        return parsed

    @staticmethod
    def _resolve(hostname: str, port: int) -> tuple[str, ...]:
        return tuple(
            str(result[4][0])
            for result in socket.getaddrinfo(
                hostname, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )
        )


class PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate every HTTP redirect before urllib follows it."""

    def __init__(self, policy: PublicNetworkPolicy) -> None:
        super().__init__()
        self.policy = policy

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.policy.require_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)
