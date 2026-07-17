"""Small deterministic normalization algorithms used by the H2 compiler."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit


class NormalizationValueError(ValueError):
    pass


def stable_hash(*parts: object, length: int = 20) -> str:
    encoded = "\x00".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def stable_token(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).strip().lower()
    token = re.sub(r"[^a-z0-9._-]+", "-", normalized).strip("-._")
    return token or stable_hash(value, length=12)


def normalize_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise NormalizationValueError("source origin must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise NormalizationValueError("source origin must not contain credentials")
    host = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port else ""
    path = _normalize_path(parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(
        (parsed.scheme.lower(), f"{host}{port}", path if path != "/" else "", "", "")
    )


def _normalize_path(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\\", "/"))
    segments = value.split("/")
    normalized: list[str] = []
    for segment in segments:
        if segment in {"", "."}:
            continue
        decoded = unquote(segment)
        if decoded in {".", ".."} or "/" in decoded or "\\" in decoded:
            raise NormalizationValueError(
                "URL path contains traversal or encoded separators"
            )
        if any(ord(character) < 32 for character in decoded):
            raise NormalizationValueError("URL path contains control characters")
        normalized.append(segment)
    return "/" + "/".join(normalized)


def normalize_route_path(value: str, origin: str, trailing_slash: str) -> str:
    absolute = urljoin(origin.rstrip("/") + "/", value)
    parsed = urlsplit(absolute)
    source = urlsplit(origin)
    if (parsed.scheme.lower(), parsed.hostname, parsed.port) != (
        source.scheme.lower(),
        source.hostname,
        source.port,
    ):
        raise NormalizationValueError("route URL is outside the source origin")
    path = _normalize_path(parsed.path)
    if path == "/":
        return path
    if trailing_slash == "always":
        return path.rstrip("/") + "/"
    return path.rstrip("/")


def absolute_url(origin: str, route_path: str) -> str:
    return urljoin(origin.rstrip("/") + "/", route_path.lstrip("/"))


def normalize_internal_url(
    value: str,
    origin: str,
    trailing_slash: str,
) -> str | None:
    parsed = urlsplit(urljoin(origin.rstrip("/") + "/", value))
    source = urlsplit(origin)
    if (parsed.scheme.lower(), parsed.hostname, parsed.port) != (
        source.scheme.lower(),
        source.hostname,
        source.port,
    ):
        return None
    return normalize_route_path(parsed.path, origin, trailing_slash)


def output_path(route_path: str) -> str:
    if route_path == "/":
        return "index.html"
    return route_path.strip("/") + "/index.html"


def normalize_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip().strip("/")
    if not normalized or normalized in {".", ".."}:
        raise NormalizationValueError("content slug is empty or unsafe")
    if (
        "/" in normalized
        or "\\" in normalized
        or any(ord(char) < 32 for char in normalized)
    ):
        raise NormalizationValueError(
            "content slug contains path separators or controls"
        )
    return normalized


def normalize_gmt_datetime(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate.replace(" ", "T"))
    except ValueError as exc:
        raise NormalizationValueError("date is not ISO-compatible") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
