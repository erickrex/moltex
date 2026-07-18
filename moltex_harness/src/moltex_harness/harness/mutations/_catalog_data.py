"""Reviewed H6 mutation declarations, separate from mutation mechanics."""

from __future__ import annotations

from typing import Literal, cast

from ..models import MutationDefinition


def definitions() -> tuple[MutationDefinition, ...]:
    rows = (
        ("route.delete-output", "Delete expected built route", "route.expected-output", "baseline", "built-output", ()),
        ("content.remove-marker", "Remove required content marker", "content.required-marker", "baseline", "built-output", ()),
        ("link.break-internal", "Link to a missing local route", "link.internal-target", "migration", "built-output", ()),
        ("asset.delete-local", "Delete a required local asset", "asset.local-exists", "baseline", "built-output", ("asset.checksum",)),
        ("asset.corrupt-bytes", "Corrupt immutable asset bytes", "asset.checksum", "baseline", "built-output", ()),
        ("nav.change-target", "Change primary navigation target", "navigation.contract", "migration", "source", ()),
        ("seo.empty-title", "Empty a required rendered title", "seo.required-title", "migration", "built-output", ()),
        ("seo.wrong-canonical", "Set a foreign canonical", "seo.canonical", "migration", "built-output", ()),
        ("redirect.create-loop", "Create a two-rule redirect loop", "redirect.no-loop", "migration", "contract", ("redirect.contract",)),
        ("capability.remove-disposition", "Remove a capability disposition", "capability.disposition", "migration", "contract", ()),
        ("parity.duplicate-row", "Duplicate a parity subject", "parity.unique-subject", "parity", "contract", ()),
        ("task.false-complete", "Claim task completion without evidence", "task.completion-evidence", "parity", "planning", ()),
        ("browser.console-error", "Emit a severe browser console message", "browser.console", "parity", "built-output", (), True),
        ("a11y.remove-name", "Remove primary navigation accessible name", "a11y.accessible-name", "parity", "built-output", ("a11y.landmarks",), True),
    )
    return tuple(
        MutationDefinition(
            mutation_id=row[0],
            description=row[1],
            check_id=row[2],
            level=cast(Literal["baseline", "migration", "parity"], row[3]),
            layer=cast(
                Literal["source", "built-output", "contract", "planning"],
                row[4],
            ),
            allowed_cascades=row[5],
            requires_browser=bool(row[6]) if len(row) > 6 else False,
        )
        for row in rows
    )
