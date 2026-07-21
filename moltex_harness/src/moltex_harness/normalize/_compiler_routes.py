"""Contract compiler implementation component."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit


from moltex_harness.models import (
    RawSourceEvidence,
    RouteContract,
)

from .primitives import (
    normalize_content_title,
    normalize_route_path,
    normalize_slug,
    output_path,
    stable_token,
)

from ._compiler_support import ContractCompilationError, _CompilerSupport, _lineage


class _RouteCompilerMixin(_CompilerSupport):
    def _routes(
        self,
        raw: RawSourceEvidence,
        origin: str,
        trailing: str,
        front_id: str | None,
        posts_id: str | None,
    ) -> list[RouteContract]:
        routes: list[RouteContract] = []
        targets: dict[str, str] = {}
        for item in raw.content:
            if item.status != "publish":
                continue
            source_id = str(item.source_id)
            record_id = (
                f"content:{stable_token(item.content_type)}:{stable_token(source_id)}"
            )
            route_id = (
                f"route:{stable_token(item.content_type)}:{stable_token(source_id)}"
            )
            target = normalize_route_path(item.legacy_permalink, origin, trailing)
            legacy_parts = urlsplit(item.legacy_permalink)
            if target == "/" and legacy_parts.query and source_id != front_id:
                target = normalize_route_path(
                    f"/{normalize_slug(item.slug)}/", origin, trailing
                )
            if source_id == front_id:
                target = "/"
            if target in targets:
                raise ContractCompilationError(
                    "route_collision",
                    f"{route_id} and {targets[target]} normalize to {target}",
                )
            targets[target] = route_id
            family = (
                "home"
                if target == "/"
                else "listing"
                if source_id == posts_id
                else item.content_type
            )
            marker = normalize_content_title(
                item.title, item.slug, item.content_type
            )
            ref = item.evidence
            routes.append(
                RouteContract(
                    contract_id=route_id,
                    source_content_id=source_id,
                    content_record_id=record_id,
                    legacy_url=item.legacy_permalink,
                    target_url=target,
                    page_family=family,
                    output_path=output_path(target),
                    expected_status=200,
                    required_content_markers=(marker,),
                    redirect_required=normalize_route_path(
                        item.legacy_permalink, origin, trailing
                    )
                    != target,
                    seo_contract_id=f"seo:{stable_token(item.content_type)}:{stable_token(source_id)}",
                    public=True,
                    lineage=_lineage(
                        RouteContract,
                        ref,
                        "route-preserve-public-source/1",
                        overrides={
                            "target_url": (
                                (ref,),
                                "route-normalization/1",
                                "preserve_legacy_path",
                            ),
                            "page_family": ((ref,), "route-family/1", family),
                        },
                    ),
                )
            )
        if not any(route.target_url == "/" for route in routes):
            settings = self._artifact(raw, "site_settings.json")
            settings_data = settings.data if isinstance(settings.data, dict) else {}
            core_value = settings_data.get("core")
            core: dict[str, Any] = core_value if isinstance(core_value, dict) else {}
            marker = str(core.get("site_title") or core.get("name") or "Home")
            routes.append(
                RouteContract(
                    contract_id="route:site:home",
                    source_content_id="site:home",
                    content_record_id=None,
                    legacy_url="/",
                    target_url="/",
                    page_family="home",
                    output_path="index.html",
                    expected_status=200,
                    required_content_markers=(marker,),
                    redirect_required=False,
                    seo_contract_id="seo:site:home",
                    public=True,
                    lineage=_lineage(
                        RouteContract,
                        settings.evidence,
                        "posts-index-home-route/1",
                        decision="wordpress_show_on_front_posts",
                    ),
                )
            )
        return routes
