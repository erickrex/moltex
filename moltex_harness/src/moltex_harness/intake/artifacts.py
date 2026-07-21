"""Canonical harness consumers and explicit diagnostic-only export evidence."""

from __future__ import annotations


CAPABILITY_CONSUMERS: dict[str, str] = {
    "forms_config.json": "capability-compiler:forms",
    "geodirectory.json": "capability-compiler:geodirectory",
    "integration_manifest.json": "capability-compiler:integrations",
    "plugins/plugins_fingerprint.json": "capability-compiler:dynamic-plugins",
    "shortcodes_inventory.json": "capability-compiler:shortcodes",
    "widgets.json": "capability-compiler:widgets",
}

CAPABILITY_ARTIFACTS = tuple(sorted(CAPABILITY_CONSUMERS))

# These artifacts remain bounded source diagnostics. They are intentionally not loaded
# as RawSourceEvidence.capabilities until a canonical consumer exists.
DIAGNOSTIC_ARTIFACTS = frozenset(
    {
        "acf_field_groups.json",
        "block_patterns.json",
        "blocks_usage.json",
        "hooks_registry.json",
        "plugin_behaviors.json",
        "plugins/blocks.json",
        "plugins/custom_post_types.json",
        "plugins/database_tables.json",
        "plugins/shortcodes.json",
        "plugins/taxonomies.json",
        "theme/theme_mods.json",
    }
)
