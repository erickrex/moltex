from __future__ import annotations

import pytest

from moltex_harness.intake.site_identity import (
    derive_site_identity,
    verify_site_identity,
)
from moltex_harness.models import SiteIdentity


def test_site_identity_matches_exporter_domain_and_slug_algorithm() -> None:
    identity = derive_site_identity(
        "https://Dev.WPTelescope.com/wordpress/", "WP Telescope"
    )

    assert identity.site_name == "WP Telescope"
    assert identity.domain == "dev.wptelescope.com"
    assert identity.workspace_slug == "dev-wptelescope-com-wordpress"


def test_site_identity_rejects_a_mismatched_workspace_slug() -> None:
    identity = SiteIdentity(
        site_name="WP Telescope",
        domain="dev.wptelescope.com",
        workspace_slug="another-site",
    )

    with pytest.raises(ValueError, match="workspace_slug does not match"):
        verify_site_identity("https://dev.wptelescope.com", identity)


def test_site_identity_rejects_an_origin_without_a_domain() -> None:
    with pytest.raises(ValueError, match="valid domain"):
        derive_site_identity("/relative-only", "Broken")
