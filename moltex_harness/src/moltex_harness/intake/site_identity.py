"""Cross-runtime derivation and validation of source-site workspace identity."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from moltex_harness.models import SiteIdentity


def derive_site_identity(origin: str, site_name: str = "") -> SiteIdentity:
    """Match the exporter algorithm without trusting a path from the archive."""

    try:
        parsed = urlsplit(origin.strip())
        domain = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError as error:
        raise ValueError("Site origin must contain a valid domain") from error
    if not domain:
        raise ValueError("Site origin must contain a valid domain")
    seed = domain
    if port is not None:
        seed += f"-{port}"
    if parsed.path and parsed.path != "/":
        seed += "-" + parsed.path.strip("/")
    workspace_slug = re.sub(r"[^a-z0-9]+", "-", seed.lower())[:100].strip("-")
    if not workspace_slug:
        raise ValueError("Site origin cannot produce a safe workspace name")
    return SiteIdentity(
        site_name=site_name.strip() or domain,
        domain=domain,
        workspace_slug=workspace_slug,
    )


def verify_site_identity(origin: str, identity: SiteIdentity) -> SiteIdentity:
    """Reject an identity that disagrees with its signed public origin."""

    expected = derive_site_identity(origin, identity.site_name)
    if identity.domain != expected.domain:
        raise ValueError("site_identity.domain does not match site_origin")
    if identity.workspace_slug != expected.workspace_slug:
        raise ValueError("site_identity.workspace_slug does not match site_origin")
    return identity
