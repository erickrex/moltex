"""Compile an accepted bundle and source evidence into an Astro 5 baseline."""

from __future__ import annotations

import html
import hashlib
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from moltex_harness.contracts import CompilationService, ContractStore, ContractVerifier
from moltex_harness.conversion import (
    ContentConverter,
    FrontmatterNormalizer,
    UrlRewriter,
    classify_failure,
)
from moltex_harness.intake.archive import ArchiveLimits, SafeArchive
from moltex_harness.intake.serialization import deterministic_json, write_json
from moltex_harness.models import BaselineCompilationReport
from moltex_harness.visuals import CaptureBackend, SourceVisualService

from .media import AssetMaterializer, MediaFetcher
from .toolchain import NODE_VERSION, NPM_VERSION

if TYPE_CHECKING:
    from moltex_harness.pipeline.context import PipelineContext


TEMPLATES = Path(__file__).parent / "templates"
FailureClassification = Literal["permanent", "blocked", "transient", "harness"]

BASELINE_STYLES = """
:root {
  --moltex-color-0: #0f57fb;
  --moltex-color-1: #21252f;
  --moltex-color-2: #313c4d;
  --moltex-color-3: #484c50;
  --moltex-color-4: #f3f7ff;
  --moltex-color-5: #ffffff;
  --moltex-color-6: #243673;
  --moltex-color-7: #fbfcff;
  --moltex-color-8: #bfd1ff;
  --nv-dark-bg: #172235;
  --nv-site-bg: #f7f5f0;
  --nv-text-dark-bg: #ffffff;
  --nv-text-color: #172235;
  --nv-primary-accent: #a16d42;
  --nv-secondary-accent: #6d7b61;
  --nv-c-1: #d9b995;
  --nv-c-2: #57606d;
  color: var(--moltex-color-3);
  font-family: "Work Sans", Inter, ui-sans-serif, system-ui, sans-serif;
  font-size: 17px;
  line-height: 1.6;
}
* { box-sizing: border-box; }
html { background: var(--moltex-color-4); scroll-behavior: smooth; }
body { margin: 0; min-width: 320px; background: var(--moltex-color-4); color: var(--moltex-color-3); }
a { color: inherit; }
img { display: block; max-width: 100%; height: auto; }
figure { margin: 0; }
h1, h2, h3, h4, h5, h6 { color: var(--moltex-color-1); font-family: Poppins, "Trebuchet MS", ui-sans-serif, sans-serif; line-height: 1.2; }
.skip { position: fixed; left: -10000px; top: 1rem; z-index: 100; }
.skip:focus { left: 1rem; background: white; padding: .75rem 1rem; color: #111; }
.visually-hidden { position: absolute !important; width: 1px !important; height: 1px !important; overflow: hidden !important; clip: rect(0 0 0 0) !important; white-space: nowrap !important; }
.site-header { position: absolute; inset: 0 0 auto; z-index: 20; color: white; }
.site-header__inner { width: min(1200px, calc(100% - 3rem)); min-height: 88px; margin: auto; display: flex; align-items: center; justify-content: space-between; gap: 2rem; }
.site-brand { color: inherit; font-family: Poppins, "Trebuchet MS", sans-serif; font-size: 1.25rem; font-weight: 700; text-decoration: none; }
.site-header nav > ul { display: flex; align-items: center; gap: 1.75rem; margin: 0; padding: 0; list-style: none; }
.site-header nav ul ul { position: absolute; margin: 0; padding: .75rem; list-style: none; background: var(--moltex-color-5); color: var(--moltex-color-1); box-shadow: 0 12px 30px rgb(33 37 47 / 18%); }
.site-header nav a { color: inherit; font-weight: 600; text-decoration: none; }
.site-header nav a:hover, .site-header nav a:focus-visible { text-decoration: underline; text-underline-offset: .35em; }
main { width: 100%; min-height: 70vh; }
.route-content { width: 100%; margin: 0; }
.route-title { width: min(1200px, calc(100% - 3rem)); margin: 0 auto; padding: 9rem 0 3rem; font-size: clamp(2.25rem, 5vw, 4rem); }
.content { width: 100%; overflow: clip; }
.content > .moltex-block-root { width: 100%; }
.moltex-block-root > .moltex-container { margin-right: auto; margin-left: auto; }
.moltex-block {
  --moltex-display: block; --moltex-lg-display: var(--moltex-display); --moltex-md-display: var(--moltex-lg-display); --moltex-sm-display: var(--moltex-md-display);
  --moltex-grid-columns: none; --moltex-lg-grid-columns: var(--moltex-grid-columns); --moltex-md-grid-columns: var(--moltex-lg-grid-columns); --moltex-sm-grid-columns: var(--moltex-md-grid-columns);
  --moltex-flex-direction: row; --moltex-lg-flex-direction: var(--moltex-flex-direction); --moltex-md-flex-direction: var(--moltex-lg-flex-direction); --moltex-sm-flex-direction: var(--moltex-md-flex-direction);
  --moltex-flex-wrap: nowrap; --moltex-lg-flex-wrap: var(--moltex-flex-wrap); --moltex-md-flex-wrap: var(--moltex-lg-flex-wrap); --moltex-sm-flex-wrap: var(--moltex-md-flex-wrap);
  --moltex-justify: normal; --moltex-lg-justify: var(--moltex-justify); --moltex-md-justify: var(--moltex-lg-justify); --moltex-sm-justify: var(--moltex-md-justify);
  --moltex-align: normal; --moltex-lg-align: var(--moltex-align); --moltex-md-align: var(--moltex-lg-align); --moltex-sm-align: var(--moltex-md-align);
  --moltex-gap: 0; --moltex-lg-gap: var(--moltex-gap); --moltex-md-gap: var(--moltex-lg-gap); --moltex-sm-gap: var(--moltex-md-gap);
  --moltex-width: auto; --moltex-lg-width: var(--moltex-width); --moltex-md-width: var(--moltex-lg-width); --moltex-sm-width: var(--moltex-md-width);
  --moltex-max-width: none; --moltex-lg-max-width: var(--moltex-max-width); --moltex-md-max-width: var(--moltex-lg-max-width); --moltex-sm-max-width: var(--moltex-md-max-width);
  --moltex-min-height: 0; --moltex-lg-min-height: var(--moltex-min-height); --moltex-md-min-height: var(--moltex-lg-min-height); --moltex-sm-min-height: var(--moltex-md-min-height);
  --moltex-height: auto; --moltex-lg-height: var(--moltex-height); --moltex-md-height: var(--moltex-lg-height); --moltex-sm-height: var(--moltex-md-height);
  --moltex-padding-top: 0; --moltex-lg-padding-top: var(--moltex-padding-top); --moltex-md-padding-top: var(--moltex-lg-padding-top); --moltex-sm-padding-top: var(--moltex-md-padding-top);
  --moltex-padding-right: 0; --moltex-lg-padding-right: var(--moltex-padding-right); --moltex-md-padding-right: var(--moltex-lg-padding-right); --moltex-sm-padding-right: var(--moltex-md-padding-right);
  --moltex-padding-bottom: 0; --moltex-lg-padding-bottom: var(--moltex-padding-bottom); --moltex-md-padding-bottom: var(--moltex-lg-padding-bottom); --moltex-sm-padding-bottom: var(--moltex-md-padding-bottom);
  --moltex-padding-left: 0; --moltex-lg-padding-left: var(--moltex-padding-left); --moltex-md-padding-left: var(--moltex-lg-padding-left); --moltex-sm-padding-left: var(--moltex-md-padding-left);
  --moltex-margin-top: 0; --moltex-lg-margin-top: var(--moltex-margin-top); --moltex-md-margin-top: var(--moltex-lg-margin-top); --moltex-sm-margin-top: var(--moltex-md-margin-top);
  --moltex-margin-right: 0; --moltex-lg-margin-right: var(--moltex-margin-right); --moltex-md-margin-right: var(--moltex-lg-margin-right); --moltex-sm-margin-right: var(--moltex-md-margin-right);
  --moltex-margin-bottom: 0; --moltex-lg-margin-bottom: var(--moltex-margin-bottom); --moltex-md-margin-bottom: var(--moltex-lg-margin-bottom); --moltex-sm-margin-bottom: var(--moltex-md-margin-bottom);
  --moltex-margin-left: 0; --moltex-lg-margin-left: var(--moltex-margin-left); --moltex-md-margin-left: var(--moltex-lg-margin-left); --moltex-sm-margin-left: var(--moltex-md-margin-left);
  --moltex-background-color: transparent; --moltex-lg-background-color: var(--moltex-background-color); --moltex-md-background-color: var(--moltex-lg-background-color); --moltex-sm-background-color: var(--moltex-md-background-color);
  --moltex-background-image: none; --moltex-lg-background-image: var(--moltex-background-image); --moltex-md-background-image: var(--moltex-lg-background-image); --moltex-sm-background-image: var(--moltex-md-background-image);
  --moltex-background-position: center; --moltex-lg-background-position: var(--moltex-background-position); --moltex-md-background-position: var(--moltex-lg-background-position); --moltex-sm-background-position: var(--moltex-md-background-position);
  --moltex-background-size: cover; --moltex-lg-background-size: var(--moltex-background-size); --moltex-md-background-size: var(--moltex-lg-background-size); --moltex-sm-background-size: var(--moltex-md-background-size);
  --moltex-border-width: 0; --moltex-lg-border-width: var(--moltex-border-width); --moltex-md-border-width: var(--moltex-lg-border-width); --moltex-sm-border-width: var(--moltex-md-border-width);
  --moltex-border-style: solid; --moltex-lg-border-style: var(--moltex-border-style); --moltex-md-border-style: var(--moltex-lg-border-style); --moltex-sm-border-style: var(--moltex-md-border-style);
  --moltex-border-color: transparent; --moltex-lg-border-color: var(--moltex-border-color); --moltex-md-border-color: var(--moltex-lg-border-color); --moltex-sm-border-color: var(--moltex-md-border-color);
  --moltex-border-radius: 0; --moltex-lg-border-radius: var(--moltex-border-radius); --moltex-md-border-radius: var(--moltex-lg-border-radius); --moltex-sm-border-radius: var(--moltex-md-border-radius);
  --moltex-color: inherit; --moltex-lg-color: var(--moltex-color); --moltex-md-color: var(--moltex-lg-color); --moltex-sm-color: var(--moltex-md-color);
  --moltex-font-size: inherit; --moltex-lg-font-size: var(--moltex-font-size); --moltex-md-font-size: var(--moltex-lg-font-size); --moltex-sm-font-size: var(--moltex-md-font-size);
  --moltex-font-family: inherit; --moltex-lg-font-family: var(--moltex-font-family); --moltex-md-font-family: var(--moltex-lg-font-family); --moltex-sm-font-family: var(--moltex-md-font-family);
  --moltex-font-weight: inherit; --moltex-lg-font-weight: var(--moltex-font-weight); --moltex-md-font-weight: var(--moltex-lg-font-weight); --moltex-sm-font-weight: var(--moltex-md-font-weight);
  --moltex-line-height: inherit; --moltex-lg-line-height: var(--moltex-line-height); --moltex-md-line-height: var(--moltex-lg-line-height); --moltex-sm-line-height: var(--moltex-md-line-height);
  box-sizing: border-box;
  display: var(--moltex-lg-display, var(--moltex-display, block));
  grid-template-columns: var(--moltex-lg-grid-columns, var(--moltex-grid-columns, none));
  flex-direction: var(--moltex-lg-flex-direction, var(--moltex-flex-direction, row));
  flex-wrap: var(--moltex-lg-flex-wrap, var(--moltex-flex-wrap, nowrap));
  justify-content: var(--moltex-lg-justify, var(--moltex-justify, normal));
  align-items: var(--moltex-lg-align, var(--moltex-align, normal));
  gap: var(--moltex-lg-gap, var(--moltex-gap, 0));
  width: var(--moltex-lg-width, var(--moltex-width, auto));
  max-width: var(--moltex-lg-max-width, var(--moltex-max-width, none));
  min-height: var(--moltex-lg-min-height, var(--moltex-min-height, 0));
  height: var(--moltex-lg-height, var(--moltex-height, auto));
  padding-top: var(--moltex-lg-padding-top, var(--moltex-padding-top, 0));
  padding-right: var(--moltex-lg-padding-right, var(--moltex-padding-right, 0));
  padding-bottom: var(--moltex-lg-padding-bottom, var(--moltex-padding-bottom, 0));
  padding-left: var(--moltex-lg-padding-left, var(--moltex-padding-left, 0));
  margin-top: var(--moltex-lg-margin-top, var(--moltex-margin-top, 0));
  margin-right: var(--moltex-lg-margin-right, var(--moltex-margin-right, 0));
  margin-bottom: var(--moltex-lg-margin-bottom, var(--moltex-margin-bottom, 0));
  margin-left: var(--moltex-lg-margin-left, var(--moltex-margin-left, 0));
  border-width: var(--moltex-lg-border-width, var(--moltex-border-width, 0));
  border-style: var(--moltex-lg-border-style, var(--moltex-border-style, solid));
  border-color: var(--moltex-lg-border-color, var(--moltex-border-color, transparent));
  border-radius: var(--moltex-lg-border-radius, var(--moltex-border-radius, 0));
  background-color: var(--moltex-lg-background-color, var(--moltex-background-color, transparent));
  background-image: var(--moltex-lg-background-image, var(--moltex-background-image, none));
  background-position: var(--moltex-lg-background-position, var(--moltex-background-position, center));
  background-size: var(--moltex-lg-background-size, var(--moltex-background-size, cover));
  background-repeat: no-repeat;
  color: var(--moltex-lg-color, var(--moltex-color, inherit));
  font-family: var(--moltex-lg-font-family, var(--moltex-font-family, inherit));
  font-size: var(--moltex-lg-font-size, var(--moltex-font-size, inherit));
  font-weight: var(--moltex-lg-font-weight, var(--moltex-font-weight, inherit));
  line-height: var(--moltex-lg-line-height, var(--moltex-line-height, inherit));
}
.moltex-buttons { align-items: center; }
.moltex-button { display: inline-flex; align-items: center; justify-content: center; width: auto; min-height: 48px; padding: .75em 2em; border-radius: 3px; background: var(--moltex-lg-background-color, var(--moltex-background-color, var(--moltex-color-0))); color: var(--moltex-lg-color, var(--moltex-color, white)); font-weight: 600; text-decoration: none; transition: transform .2s ease, opacity .2s ease; }
.moltex-button:hover, .moltex-button:focus-visible { opacity: .9; transform: translateY(-1px); }
.moltex-icon { display: inline-grid; width: 1.75em; height: 1.75em; place-items: center; color: var(--moltex-color-0); }
.moltex-placeholder, .moltex-dynamic-block { width: min(1200px, calc(100% - 3rem)); margin: 1rem auto; border: 2px dashed #9b6b00; padding: 1rem; background: #fff8dc; color: #4d3500; }
.moltex-media-placeholder { display: block; min-height: 16rem; background: linear-gradient(135deg, #dbe3f3, #eef3fb 45%, #cbd7e9); }
.listing-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: 1.5rem; width: min(1200px, calc(100% - 3rem)); margin: 4rem auto; }
.listing-card { border: 1px solid #dbe3f3; border-radius: .5rem; padding: 1.5rem; background: white; }
.typed-fields { width: min(1200px, calc(100% - 3rem)); margin: 3rem auto; }
.site-footer { padding: 3rem max(1.5rem, calc((100% - 1200px) / 2)); background: var(--moltex-color-1); color: white; }

/* Safe utility treatment for paired Gutenberg blocks that ship rendered HTML. */
.relative { position: relative; } .absolute { position: absolute; } .inset-0 { inset: 0; }
.flex { display: flex; } .grid { display: grid; } .flex-col { flex-direction: column; } .flex-row { flex-direction: row; } .flex-wrap { flex-wrap: wrap; }
.items-center { align-items: center; } .items-start { align-items: flex-start; } .items-stretch { align-items: stretch; }
.justify-center { justify-content: center; } .justify-between { justify-content: space-between; }
.w-full { width: 100%; } .h-full { height: 100%; } .object-cover { object-fit: cover; }
.mx-auto { margin-inline: auto; } .text-center { text-align: center; } .uppercase { text-transform: uppercase; }
.font-semibold { font-weight: 600; } .font-bold { font-weight: 700; } .opacity-30 { opacity: .3; } .opacity-80 { opacity: .8; } .opacity-90 { opacity: .9; }
.max-w-2xl { max-width: 42rem; } .max-w-3xl { max-width: 48rem; } .max-w-5xl { max-width: 64rem; } .max-w-6xl { max-width: 72rem; }
.gap-2 { gap: .5rem; } .gap-3 { gap: .75rem; } .gap-4 { gap: 1rem; } .gap-5 { gap: 1.25rem; } .gap-6 { gap: 1.5rem; } .gap-10 { gap: 2.5rem; } .gap-12 { gap: 3rem; } .gap-16 { gap: 4rem; }
.p-8 { padding: 2rem; } .px-6 { padding-inline: 1.5rem; } .px-8 { padding-inline: 2rem; } .py-4 { padding-block: 1rem; } .py-12 { padding-block: 3rem; } .py-20 { padding-block: 5rem; } .py-24 { padding-block: 6rem; } .py-32 { padding-block: 8rem; } .py-40 { padding-block: 10rem; }
.mb-12 { margin-bottom: 3rem; } .mt-1 { margin-top: .25rem; } .mt-2 { margin-top: .5rem; } .mt-4 { margin-top: 1rem; }
.text-xs { font-size: .75rem; } .text-sm { font-size: .875rem; } .text-lg { font-size: 1.125rem; } .text-xl { font-size: 1.25rem; } .text-5xl { font-size: 3rem; }
[class*="bg-[var(--nv-dark-bg)]"] { background: var(--nv-dark-bg); }
[class*="bg-[var(--nv-site-bg)]"] { background: var(--nv-site-bg); }
[class*="text-[var(--nv-text-dark-bg)]"] { color: var(--nv-text-dark-bg); }
[class*="text-[var(--nv-text-color)]"] { color: var(--nv-text-color); }
[class*="text-[var(--nv-primary-accent)]"] { color: var(--nv-primary-accent); }
.wp-block-columns { display: flex; gap: 2rem; } .wp-block-column { flex: 1 1 0; }
.wp-block-gallery { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: 1rem; }
.wp-block-media-text { display: grid; grid-template-columns: 1fr 1fr; align-items: center; gap: 2rem; }

@media (max-width: 976px) {
  .site-header__inner { min-height: 76px; }
  .site-header nav > ul { gap: 1rem; }
  .moltex-block {
    display: var(--moltex-md-display, var(--moltex-lg-display, var(--moltex-display, block)));
    grid-template-columns: var(--moltex-md-grid-columns, var(--moltex-lg-grid-columns, var(--moltex-grid-columns, none)));
    flex-direction: var(--moltex-md-flex-direction, var(--moltex-lg-flex-direction, var(--moltex-flex-direction, row)));
    flex-wrap: var(--moltex-md-flex-wrap, var(--moltex-lg-flex-wrap, var(--moltex-flex-wrap, nowrap)));
    justify-content: var(--moltex-md-justify, var(--moltex-lg-justify, var(--moltex-justify, normal)));
    align-items: var(--moltex-md-align, var(--moltex-lg-align, var(--moltex-align, normal)));
    gap: var(--moltex-md-gap, var(--moltex-lg-gap, var(--moltex-gap, 0)));
    width: var(--moltex-md-width, var(--moltex-lg-width, var(--moltex-width, auto)));
    max-width: var(--moltex-md-max-width, var(--moltex-lg-max-width, var(--moltex-max-width, none)));
    padding: var(--moltex-md-padding-top, var(--moltex-lg-padding-top, var(--moltex-padding-top, 0))) var(--moltex-md-padding-right, var(--moltex-lg-padding-right, var(--moltex-padding-right, 0))) var(--moltex-md-padding-bottom, var(--moltex-lg-padding-bottom, var(--moltex-padding-bottom, 0))) var(--moltex-md-padding-left, var(--moltex-lg-padding-left, var(--moltex-padding-left, 0)));
    margin: var(--moltex-md-margin-top, var(--moltex-lg-margin-top, var(--moltex-margin-top, 0))) var(--moltex-md-margin-right, var(--moltex-lg-margin-right, var(--moltex-margin-right, 0))) var(--moltex-md-margin-bottom, var(--moltex-lg-margin-bottom, var(--moltex-margin-bottom, 0))) var(--moltex-md-margin-left, var(--moltex-lg-margin-left, var(--moltex-margin-left, 0)));
    font-size: var(--moltex-md-font-size, var(--moltex-lg-font-size, var(--moltex-font-size, inherit)));
  }
  .md\\:flex-row { flex-direction: row; } .md\\:grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 767px) {
  .site-header__inner { width: calc(100% - 2rem); align-items: flex-start; flex-direction: column; justify-content: center; gap: .35rem; }
  .site-header nav > ul { flex-wrap: wrap; gap: .35rem 1rem; font-size: .85rem; }
  .moltex-block {
    display: var(--moltex-sm-display, var(--moltex-md-display, var(--moltex-display, block)));
    grid-template-columns: var(--moltex-sm-grid-columns, var(--moltex-md-grid-columns, var(--moltex-grid-columns, none)));
    flex-direction: var(--moltex-sm-flex-direction, var(--moltex-md-flex-direction, var(--moltex-flex-direction, row)));
    flex-wrap: var(--moltex-sm-flex-wrap, var(--moltex-md-flex-wrap, var(--moltex-flex-wrap, nowrap)));
    justify-content: var(--moltex-sm-justify, var(--moltex-md-justify, var(--moltex-justify, normal)));
    align-items: var(--moltex-sm-align, var(--moltex-md-align, var(--moltex-align, normal)));
    gap: var(--moltex-sm-gap, var(--moltex-md-gap, var(--moltex-gap, 0)));
    width: var(--moltex-sm-width, var(--moltex-md-width, var(--moltex-width, auto)));
    max-width: var(--moltex-sm-max-width, var(--moltex-md-max-width, var(--moltex-max-width, none)));
    padding: var(--moltex-sm-padding-top, var(--moltex-md-padding-top, var(--moltex-padding-top, 0))) var(--moltex-sm-padding-right, var(--moltex-md-padding-right, var(--moltex-padding-right, 0))) var(--moltex-sm-padding-bottom, var(--moltex-md-padding-bottom, var(--moltex-padding-bottom, 0))) var(--moltex-sm-padding-left, var(--moltex-md-padding-left, var(--moltex-padding-left, 0)));
    margin: var(--moltex-sm-margin-top, var(--moltex-md-margin-top, var(--moltex-margin-top, 0))) var(--moltex-sm-margin-right, var(--moltex-md-margin-right, var(--moltex-margin-right, 0))) var(--moltex-sm-margin-bottom, var(--moltex-md-margin-bottom, var(--moltex-margin-bottom, 0))) var(--moltex-sm-margin-left, var(--moltex-md-margin-left, var(--moltex-margin-left, 0)));
    font-size: var(--moltex-sm-font-size, var(--moltex-md-font-size, var(--moltex-font-size, inherit)));
  }
  .wp-block-columns, .wp-block-media-text { grid-template-columns: 1fr; flex-direction: column; }
}
""".strip() + "\n"


@dataclass(frozen=True, slots=True)
class BaselineOutcome:
    report: BaselineCompilationReport
    exit_code: int


class BaselineService:
    def __init__(
        self,
        *,
        media_fetcher: MediaFetcher | None = None,
        capture_backend: CaptureBackend | None = None,
    ) -> None:
        self.media_fetcher = media_fetcher
        self.capture_backend = capture_backend

    def compile_archive(
        self,
        archive: Path,
        output: Path,
        source_visuals: Path | None = None,
        *,
        prepared: PipelineContext | None = None,
    ) -> BaselineOutcome:
        if output.exists() and any(output.iterdir()):
            return self._failure(
                output,
                None,
                "output_not_empty",
                "Baseline output directory must be empty",
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="moltex-h3-") as temporary:
            root = Path(temporary)
            if prepared is None:
                contracts_dir = root / "contracts"
                h2 = CompilationService().compile_archive(archive, contracts_dir)
                if h2.exit_code:
                    return self._failure(
                        output,
                        h2.report.get("bundle_id"),
                        "h2_failed",
                        h2.report["message"],
                    )
                contracts, _ = ContractStore().load(contracts_dir)
                extraction = root / "bundle"
            else:
                contracts_dir = prepared.contracts_dir
                contracts = prepared.contracts
                extraction = prepared.extracted_bundle
            verification = ContractVerifier().verify(contracts_dir)
            if verification.status != "pass":
                return self._failure(
                    output,
                    verification.bundle_id,
                    "h2_verification_failed",
                    verification.errors[0],
                )
            if contracts.site_spec.static_eligibility == "ineligible":
                return self._failure(
                    output,
                    contracts.source_manifest.bundle_id,
                    "static_ineligible",
                    "Source readiness marks this site ineligible for complete static migration",
                    "blocked",
                )
            workspace = root / "workspace"
            try:
                if prepared is None:
                    safe_archive = SafeArchive(
                        archive, extraction, ArchiveLimits()
                    )
                    safe_archive.prepare()
                workspace.mkdir(parents=True)
                shutil.copytree(contracts_dir, workspace / ".moltex" / "contracts")
                visual_destination = (
                    workspace / ".moltex" / "evidence" / "source-visuals"
                )
                visuals = SourceVisualService()
                if source_visuals is None:
                    captured = root / "source-visuals"
                    visuals.capture(contracts_dir, captured, self.capture_backend)
                    source_visuals = captured
                visual_receipt = visuals.verify_and_copy(
                    contracts_dir, source_visuals, visual_destination
                )
                omitted_route_ids = {
                    item.route_contract_id
                    for item in visual_receipt.route_availability
                    if item.disposition == "omitted"
                }
                omitted_content = {
                    route.content_record_id
                    for route in contracts.routes
                    if route.contract_id in omitted_route_ids
                    and route.content_record_id is not None
                }
                omitted_source_ids = {
                    record.source_id
                    for record in contracts.content_records
                    if record.record_id in omitted_content
                }
                omitted_content_keys = omitted_content | omitted_source_ids
                materialized_assets = self._materializable_assets(
                    contracts.assets,
                    omitted_content_keys,
                )
                receipts = AssetMaterializer(self.media_fetcher).materialize(
                    materialized_assets, extraction, workspace
                )
                write_json(workspace / ".moltex" / "receipts" / "assets.json", receipts)
                conversion_receipts = self._generate(
                    workspace, contracts, omitted_route_ids
                )
                self._write_expectations(
                    workspace,
                    contracts,
                    receipts,
                    conversion_receipts,
                    visual_receipt,
                    omitted_route_ids,
                )
            except Exception as error:
                classification: FailureClassification = classify_failure(error).value
                return self._failure(
                    output,
                    contracts.source_manifest.bundle_id,
                    f"baseline_{classification}",
                    str(error),
                    classification,
                )
            if output.exists():
                output.rmdir()
            shutil.move(str(workspace), output)
        report = BaselineCompilationReport(
            status="compiled",
            bundle_id=contracts.source_manifest.bundle_id,
            code="baseline_compiled",
            message="H3 Astro baseline compiled successfully",
            counts={
                "content": len(conversion_receipts),
                "routes": sum(
                    1
                    for route in contracts.routes
                    if route.public and route.contract_id not in omitted_route_ids
                ),
                "assets": len(receipts),
                "visuals": len(visual_receipt.evidence),
                "omitted_routes": len(omitted_route_ids),
            },
            outputs={
                "workspace": ".",
                "conversion_receipts": ".moltex/receipts/conversion.json",
                "asset_receipts": ".moltex/receipts/assets.json",
                "source_visuals": ".moltex/evidence/source-visuals/capture-receipt.json",
            },
        )
        write_json(
            output / ".moltex" / "reports" / "baseline-compilation-report.json", report
        )
        return BaselineOutcome(report, 0)

    @staticmethod
    def _materializable_assets(
        assets: Any,
        omitted_content_keys: set[str],
    ) -> tuple[Any, ...]:
        """Keep unresolved assets contractual without treating them as downloadable."""
        return tuple(
            asset
            for asset in assets
            if not asset.needs_decision
            and (
                not asset.referencing_content_ids
                or not set(asset.referencing_content_ids).issubset(
                    omitted_content_keys
                )
            )
        )

    def _generate(
        self,
        workspace: Path,
        contracts: Any,
        omitted_route_ids: set[str],
    ) -> tuple[Any, ...]:
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATES / "package.json", workspace / "package.json")
        shutil.copyfile(
            TEMPLATES / "package-lock.json", workspace / "package-lock.json"
        )
        shutil.copyfile(TEMPLATES / ".node-version", workspace / ".node-version")
        shutil.copyfile(TEMPLATES / ".npmrc", workspace / ".npmrc")
        (workspace / "astro.config.mjs").write_text(
            "import { defineConfig } from 'astro/config';\nexport default defineConfig({ output: 'static', trailingSlash: 'always' });\n",
            encoding="utf-8",
        )
        write_json(
            workspace / "tsconfig.json",
            {
                "extends": "astro/tsconfigs/strict",
                "compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}},
            },
        )
        routes_by_id = {route.contract_id: route for route in contracts.routes}
        included_routes = tuple(
            route
            for route in contracts.routes
            if route.public and route.contract_id not in omitted_route_ids
        )
        included_record_ids = {
            route.content_record_id
            for route in included_routes
            if route.content_record_id is not None
        }
        seo_by_route = {item.route_contract_id: item for item in contracts.seo}
        url_map = {entry.source_url: entry.target_url for entry in contracts.url_map}
        media_map = {
            entry.source_url: entry.target_url for entry in contracts.media_map
        }
        assets_by_id = {asset.asset_id: asset for asset in contracts.assets}
        legacy_bindings: dict[str, dict[str, str | None]] = {}
        for item in contracts.legacy_evidence:
            if item.disposition not in {"decide", "acquire"}:
                continue
            identity_key = "tag" if item.artifact_type == "shortcode" else "name"
            if item.artifact_type not in {"shortcode", "block"}:
                continue
            identity = item.source_identity.get(identity_key)
            if not isinstance(identity, str) or not identity:
                continue
            legacy_bindings[f"{item.artifact_type}:{identity.lower()}"] = {
                "evidence_id": item.source_evidence_id,
                "capability_id": item.capability_id,
                "decision_id": item.decision_id,
            }
        converter = ContentConverter(
            UrlRewriter(contracts.site_spec.source_origin, url_map, media_map),
            legacy_bindings,
        )
        frontmatter = FrontmatterNormalizer()
        content_by_id: dict[str, dict[str, Any]] = {}
        receipts = []
        for record in contracts.content_records:
            if record.record_id not in included_record_ids:
                continue
            receipt = converter.convert(record)
            if any(finding.severity == "error" for finding in receipt.findings):
                raise ValueError(f"Unsafe content conversion: {record.record_id}")
            receipts.append(receipt)
            route = next(
                (
                    item
                    for item in contracts.routes
                    if item.content_record_id == record.record_id
                ),
                None,
            )
            seo = seo_by_route.get(route.contract_id) if route else None
            document = {
                **frontmatter.normalize(record, seo),
                "targetUrl": route.target_url if route else None,
                "excerpt": self._excerpt(receipt.sanitized_html),
                "media": [
                    {
                        "assetId": asset.asset_id,
                        "src": "/"
                        + asset.target_path.removeprefix("public/").lstrip("/"),
                        "alt": asset.alt_text or "",
                        "mimeType": asset.mime_type,
                    }
                    for asset_id in record.required_media_ids
                    if (asset := assets_by_id.get(asset_id)) is not None
                    and not asset.needs_decision
                ],
                "bodyFormat": receipt.body_format,
                "body": receipt.editable_body,
                "renderedHtml": receipt.sanitized_html,
            }
            content_by_id[record.record_id] = document
            safe_name = record.record_id.replace(":", "-") + ".json"
            write_json(workspace / "src" / "content" / "records" / safe_name, document)
        write_json(workspace / ".moltex" / "receipts" / "conversion.json", receipts)
        self._write_shell(workspace, contracts.site_spec.site_name)
        self._write_navigation(workspace, contracts, routes_by_id, omitted_route_ids)
        posts = [
            item["recordId"]
            for item in content_by_id.values()
            if item["contentType"] == "post"
        ]
        geodirectory = [
            item["recordId"]
            for item in content_by_id.values()
            if item["contentType"].startswith("gd_")
        ]
        generated_routes: list[dict[str, Any]] = []
        for route in included_routes:
            record_id = route.content_record_id or route.contract_id
            if record_id not in content_by_id:
                document = {
                    "recordId": record_id,
                    "contentType": "system",
                    "title": route.page_family.replace("_", " ").title(),
                    "renderedHtml": (
                        "<p>This route requires a target implementation.</p>"
                    ),
                    "seo": {},
                    "media": [],
                    "customFields": {},
                }
                content_by_id[record_id] = document
                safe_name = record_id.replace(":", "-") + ".json"
                write_json(
                    workspace / "src" / "content" / "records" / safe_name,
                    document,
                )
            listing_record_ids: list[str] = []
            if route.page_family == "listing":
                listing_record_ids = posts
            route_receipt = next(
                (
                    item
                    for item in receipts
                    if item.record_id == (route.content_record_id or "")
                ),
                None,
            )
            if route_receipt and any(
                disposition.name in {"gd_listings", "gd_loop", "gd_search"}
                for disposition in route_receipt.shortcodes
            ):
                listing_record_ids = geodirectory
            if route.output_path != "404.html":
                generated_routes.append(
                    {
                        "routeId": route.contract_id,
                        "path": self._astro_route_path(route.output_path),
                        "recordId": record_id,
                        "listingRecordIds": listing_record_ids,
                    }
                )
        system_404 = {
            "recordId": "system:404",
            "contentType": "system",
            "title": "Page not found",
            "renderedHtml": "<p>The requested page could not be found.</p>",
            "seo": {"robots": "noindex", "structured_data_hints": []},
            "media": [],
            "customFields": {},
        }
        write_json(
            workspace / "src" / "content" / "records" / "system-404.json",
            system_404,
        )
        write_json(workspace / "src" / "data" / "routes.json", generated_routes)
        self._write_route_templates(workspace)
        self._write_metadata(workspace, contracts, omitted_route_ids)
        self._write_scripts(workspace)
        return tuple(receipts)

    @staticmethod
    def _write_shell(workspace: Path, site_name: str) -> None:
        write_json(workspace / "src" / "data" / "site.json", {"siteName": site_name})
        styles = workspace / "src" / "styles" / "moltex.css"
        styles.parent.mkdir(parents=True, exist_ok=True)
        styles.write_text(BASELINE_STYLES, encoding="utf-8")
        component = workspace / "src" / "components" / "NavigationList.astro"
        component.parent.mkdir(parents=True, exist_ok=True)
        component.write_text(
            "---\nconst { items = [] } = Astro.props;\n---\n"
            "<ul>{items.map((item) => <li><a href={item.href}>{item.label}</a>"
            "{item.children?.length ? <Astro.self items={item.children} /> : null}</li>)}</ul>\n",
            encoding="utf-8",
        )
        layout = workspace / "src" / "layouts" / "BaseLayout.astro"
        layout.parent.mkdir(parents=True, exist_ok=True)
        layout.write_text(
            "---\nimport nav from '../data/navigation.json';\nimport site from '../data/site.json';\nimport NavigationList from '../components/NavigationList.astro';\nimport '../styles/moltex.css';\n"
            "const { title, description = '', canonical = '', robots = 'index,follow', openGraph = {}, structuredDataHints = [] } = Astro.props;\n"
            "const ogItems = Array.isArray(openGraph.items) ? openGraph.items : [openGraph];\n"
            "const ogEntries = ogItems.flatMap((item) => item && (item.property || item.name || item.key) ? [[item.property || item.name || item.key, item.content ?? item.value ?? '']] : Object.entries(item ?? {}).filter(([key]) => key !== 'items'));\n---\n"
            '<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">'
            '<meta name="description" content={description}><meta name="robots" content={robots}><link rel="canonical" href={canonical}>'
            "{ogEntries.map(([property, content]) => <meta property={String(property).startsWith('og:') ? String(property) : `og:${property}`} content={String(content)} />)}"
            '{structuredDataHints.map((hint) => <meta name="moltex:structured-data-hint" content={hint} />)}<title>{title}</title></head>'
            '<body><a class="skip" href="#content">Skip to content</a><header class="site-header"><div class="site-header__inner"><a class="site-brand" href="/">{site.siteName}</a><nav aria-label="Primary"><NavigationList items={nav} /></nav></div></header>'
            '<main id="content"><slot /></main><footer class="site-footer">{site.siteName}</footer></body></html>\n',
            encoding="utf-8",
        )

    @staticmethod
    def _write_navigation(
        workspace: Path,
        contracts: Any,
        routes: dict[str, Any],
        omitted_route_ids: set[str],
    ) -> None:
        navigation_sources = list(contracts.site_spec.global_navigation)
        if navigation_sources:
            menu_sizes: dict[str, int] = {}
            for source in navigation_sources:
                menu_sizes[source.menu_id] = menu_sizes.get(source.menu_id, 0) + 1
            primary_menu_id = max(
                menu_sizes,
                key=lambda menu_id: (menu_sizes[menu_id], menu_id),
            )
            navigation_sources = [
                source
                for source in navigation_sources
                if source.menu_id == primary_menu_id
            ]
        items = {
            item.navigation_id: {
                "id": item.navigation_id,
                "label": item.label,
                "href": (
                    routes[item.route_contract_id].target_url
                    if item.route_contract_id in routes
                    else "#"
                ),
                "order": item.order,
                "children": [],
            }
            for item in navigation_sources
            if item.route_contract_id not in omitted_route_ids
        }
        navigation = []
        for source in navigation_sources:
            if source.navigation_id not in items:
                continue
            target = items[source.navigation_id]
            if source.parent_navigation_id in items:
                items[source.parent_navigation_id]["children"].append(target)
            else:
                navigation.append(target)

        def sort_tree(nodes: list[dict[str, Any]]) -> None:
            nodes.sort(key=lambda node: (node["order"], node["id"]))
            for node in nodes:
                sort_tree(node["children"])

        sort_tree(navigation)
        write_json(workspace / "src" / "data" / "navigation.json", navigation)

    @staticmethod
    def _write_route_templates(workspace: Path) -> None:
        pages = workspace / "src" / "pages"
        pages.mkdir(parents=True, exist_ok=True)
        shared_render = (
            "<BaseLayout title={seo.title ?? record.title} description={seo.description ?? ''} canonical={seo.canonical_url ?? ''} robots={seo.robots ?? 'index,follow'} openGraph={seo.open_graph ?? {}} structuredDataHints={seo.structured_data_hints ?? []}>"
            "<article class=\"route-content\" data-record-id={record.recordId}>{hasRenderedH1 ? <span class=\"visually-hidden\">{record.title}</span> : <h1 class=\"route-title\">{record.title}</h1>}"
            '<div class="content" set:html={record.renderedHtml} />'
            "{typedFields.length ? <dl class=\"typed-fields\">{typedFields.map(([key, value]) => <><dt>{key.replace('geodirectory.', '')}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value ?? '')}</dd></>)}</dl> : null}"
            '{listingItems.length ? <section class="listing-grid" aria-label="Listings">{listingItems.map((item) => <article class="listing-card" data-record-id={item.recordId}><h2>{item.targetUrl ? <a href={item.targetUrl}>{item.title}</a> : item.title}</h2>{item.excerpt ? <p>{item.excerpt}</p> : null}</article>)}</section> : null}'
            "</article></BaseLayout>\n"
        )
        (pages / "[...path].astro").write_text(
            "---\nimport BaseLayout from '../layouts/BaseLayout.astro';\nimport routes from '../data/routes.json';\n"
            "const recordModules = import.meta.glob('../content/records/*.json', { eager: true, import: 'default' });\n"
            "const records = Object.values(recordModules) as any[];\n"
            "export function getStaticPaths() { return routes.map((route) => ({ params: { path: route.path || undefined }, props: route })); }\n"
            "const route = Astro.props;\nconst record = records.find((item) => item.recordId === route.recordId);\n"
            "if (!record) throw new Error(`Missing route record: ${route.recordId}`);\n"
            "const listingItems = route.listingRecordIds.map((id) => records.find((item) => item.recordId === id)).filter(Boolean);\n"
            "const seo = record.seo ?? {};\nconst typedFields = Object.entries(record.customFields ?? {}).filter(([key]) => key.startsWith('geodirectory.'));\n"
            "const hasRenderedH1 = /<h1\\b/i.test(record.renderedHtml ?? '');\n---\n"
            + shared_render,
            encoding="utf-8",
        )
        (pages / "404.astro").write_text(
            "---\nimport BaseLayout from '../layouts/BaseLayout.astro';\nimport record from '../content/records/system-404.json';\n"
            "const listingItems = [];\nconst seo = record.seo ?? {};\nconst typedFields = [];\nconst hasRenderedH1 = false;\n---\n"
            + shared_render,
            encoding="utf-8",
        )

    @staticmethod
    def _astro_route_path(output_path: str) -> str:
        if output_path == "index.html":
            return ""
        if output_path.endswith("/index.html"):
            return output_path.removesuffix("/index.html")
        raise ValueError(
            f"Data-driven routes require an index.html output path: {output_path}"
        )

    @staticmethod
    def _write_metadata(
        workspace: Path, contracts: Any, omitted_route_ids: set[str]
    ) -> None:
        seo_by_route = {item.route_contract_id: item for item in contracts.seo}
        sitemap = [
            route.target_url
            for route in contracts.routes
            if route.public
            and route.contract_id not in omitted_route_ids
            and route.expected_status == 200
            and "noindex"
            not in (
                seo.robots.lower()
                if (seo := seo_by_route.get(route.contract_id))
                else ""
            )
        ]
        write_json(workspace / "src" / "data" / "sitemap.json", sitemap)
        redirects = "\n".join(
            BaselineService._redirect_line(
                item.source_url, item.target_url, item.status_code
            )
            for item in contracts.redirects
            if not item.needs_decision
            and item.target_route_contract_id not in omitted_route_ids
        )
        public = workspace / "public"
        public.mkdir(exist_ok=True)
        (public / "_redirects").write_text(
            redirects + ("\n" if redirects else ""), encoding="utf-8"
        )
        origin = contracts.site_spec.target_canonical_origin.rstrip("/")
        namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
        ET.register_namespace("", namespace)
        urlset = ET.Element(f"{{{namespace}}}urlset")
        for path in sitemap:
            url = ET.SubElement(urlset, f"{{{namespace}}}url")
            ET.SubElement(url, f"{{{namespace}}}loc").text = origin + path
        sitemap_xml = (
            ET.tostring(urlset, encoding="utf-8", xml_declaration=True) + b"\n"
        )
        (public / "sitemap.xml").write_bytes(sitemap_xml)
        (workspace / "src" / "content.config.ts").write_text(
            "import { defineCollection } from 'astro:content';\nimport { glob } from 'astro/loaders';\nexport const collections = { records: defineCollection({ loader: glob({ pattern: '**/*.json', base: './src/content/records' }) }) };\n",
            encoding="utf-8",
        )

    @staticmethod
    def _redirect_line(source: str, target: str, status_code: int) -> str:
        if any(character.isspace() for character in source + target):
            raise ValueError("Redirect URLs must not contain whitespace")
        return f"{source} {target} {status_code}"

    @staticmethod
    def _excerpt(value: str, limit: int = 240) -> str:
        text = html.unescape(re.sub(r"<[^>]+>", " ", value))
        return re.sub(r"\s+", " ", text).strip()[:limit]

    @staticmethod
    def _body_marker(value: str, limit: int = 80) -> str:
        candidates = [
            re.sub(r"\s+", " ", part).strip() for part in re.split(r"<[^>]+>", value)
        ]
        candidates = [part for part in candidates if part]
        return max(candidates, key=len, default="")[:limit]

    @staticmethod
    def _write_expectations(
        workspace: Path,
        contracts: Any,
        receipts: Any,
        conversion_receipts: Any,
        visual_receipt: Any,
        omitted_route_ids: set[str],
    ) -> None:
        conversion_by_id = {
            receipt.record_id: receipt for receipt in conversion_receipts
        }
        plan = contracts.visual_capture_plan
        write_json(
            workspace / ".moltex" / "verification" / "baseline-expectations.json",
            {
                "bundleId": contracts.source_manifest.bundle_id,
                "toolchain": {"node": NODE_VERSION, "npm": NPM_VERSION},
                "sourceOrigin": contracts.site_spec.source_origin,
                "routes": [
                    {
                        "id": route.contract_id,
                        "output": route.output_path,
                        "markers": list(route.required_content_markers),
                        "bodyMarkers": [
                            marker
                            for marker in [
                                BaselineService._body_marker(
                                    conversion_by_id[
                                        route.content_record_id
                                    ].sanitized_html
                                )
                                if route.content_record_id in conversion_by_id
                                else ""
                            ]
                            if marker
                        ],
                    }
                    for route in contracts.routes
                    if route.public and route.contract_id not in omitted_route_ids
                ],
                "assets": [
                    {
                        "id": receipt.asset_id,
                        "path": receipt.target_path.removeprefix("public/"),
                        "sha256": receipt.sha256,
                    }
                    for receipt in receipts
                ],
                "contentRecords": [
                    "src/content/records/"
                    + record.record_id.replace(":", "-")
                    + ".json"
                    for record in contracts.content_records
                    if record.record_id in conversion_by_id
                ],
                "omittedRoutes": [
                    item.model_dump(mode="json")
                    for item in visual_receipt.route_availability
                    if item.disposition == "omitted"
                ],
                "routeAvailability": [
                    item.model_dump(mode="json")
                    for item in visual_receipt.route_availability
                ],
                "visualPlan": {
                    "id": plan.plan_id,
                    "sha256": hashlib.sha256(
                        deterministic_json(plan).encode()
                    ).hexdigest(),
                    "evidence": [
                        {
                            "evidenceId": item.evidence_id,
                            "routeId": item.route_contract_id,
                            "sourceUrl": item.source_url,
                            "finalUrl": item.final_url,
                            "viewport": item.viewport_name,
                            "width": item.width,
                            "height": item.height,
                            "artifact": item.artifact,
                            "bytes": item.bytes,
                            "sha256": item.sha256,
                        }
                        for item in visual_receipt.evidence
                    ],
                },
                "visualReceipt": ".moltex/evidence/source-visuals/capture-receipt.json",
            },
        )

    @staticmethod
    def _write_scripts(workspace: Path) -> None:
        scripts = workspace / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATES / "build.mjs", scripts / "build.mjs")
        shutil.copyfile(
            TEMPLATES / "verify-baseline.mjs", scripts / "verify-baseline.mjs"
        )
        shutil.copyfile(TEMPLATES / "verify.mjs", scripts / "verify.mjs")
        shutil.copyfile(TEMPLATES / "verify-task.mjs", scripts / "verify-task.mjs")
        shutil.copytree(TEMPLATES / "verify-lib", scripts / "verify-lib")
        shutil.copytree(
            TEMPLATES / "verifier-schemas",
            workspace / ".moltex" / "schemas" / "verifier",
        )

    @staticmethod
    def _failure(
        output: Path,
        bundle_id: str | None,
        code: str,
        message: str,
        classification: FailureClassification | None = None,
    ) -> BaselineOutcome:
        report = BaselineCompilationReport(
            status="failed",
            bundle_id=bundle_id,
            code=code,
            message=message,
            classification=classification,
        )
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "baseline-compilation-report.json", report)
        return BaselineOutcome(report, 7)
