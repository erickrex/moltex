"""Typed registry for Gutenberg and plugin block conversion support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


BlockAdapter = Literal["core", "spectra", "atomic-wind", "dynamic", "fallback"]
BlockDispositionKind = Literal[
    "converted", "preserved", "dynamic", "unsupported"
]


@dataclass(frozen=True, slots=True)
class BlockConverterSpec:
    name: str
    adapter: BlockAdapter
    disposition: BlockDispositionKind


class BlockConverterRegistry:
    """Resolve exact converters while keeping unknown fallback policy explicit."""

    def __init__(self, specs: tuple[BlockConverterSpec, ...]) -> None:
        by_name = {spec.name: spec for spec in specs}
        if len(by_name) != len(specs):
            raise ValueError("Block converter registry contains duplicate names")
        if any("/" not in name or name != name.casefold() for name in by_name):
            raise ValueError("Block converter names must be normalized and namespaced")
        self._specs = by_name

    @property
    def specs(self) -> tuple[BlockConverterSpec, ...]:
        return tuple(self._specs[name] for name in sorted(self._specs))

    def resolve(self, name: str, *, self_closing: bool) -> BlockConverterSpec:
        normalized = name.casefold()
        exact = self._specs.get(normalized)
        if exact is not None:
            return exact
        return BlockConverterSpec(
            name=normalized,
            adapter="fallback",
            disposition="unsupported" if self_closing else "preserved",
        )


def default_block_registry(
    *,
    core: frozenset[str],
    dynamic: frozenset[str],
    spectra: frozenset[str],
    atomic_wind: frozenset[str],
) -> BlockConverterRegistry:
    specs = (
        tuple(BlockConverterSpec(name, "core", "converted") for name in core)
        + tuple(BlockConverterSpec(name, "dynamic", "dynamic") for name in dynamic)
        + tuple(BlockConverterSpec(name, "spectra", "converted") for name in spectra)
        + tuple(
            BlockConverterSpec(name, "atomic-wind", "converted")
            for name in atomic_wind
        )
    )
    return BlockConverterRegistry(specs)
