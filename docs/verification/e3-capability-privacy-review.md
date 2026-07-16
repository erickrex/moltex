# Phase E3 Capability and Privacy Review

## Capability disposition

The Golden Path contains one discovered integration, `embed:youtube`, on `/visit/`. It is
not silently dropped. The downstream disposition is to preserve the external video as an
explicit migration decision: use a privacy-enhanced, click-to-load embed when approved, or
replace it with a normal outbound link. The exported integration record carries the target
and detection pattern needed to keep that decision visible.

The fixture plugin also registers and renders a sanitized seasonal schedule as source-site
behavior. The rendered schedule is present in the bounded `/visit/` snapshot; the generated
site should rebuild it as static content or a local Astro component, with no WordPress
runtime dependency.

## Privacy review

- Complete export mode was used with private content disabled.
- Statuses `private`, `draft`, `pending`, `future`, and `trash` are explicitly excluded.
- A private post and sensitive post-meta/option canaries were seeded before export.
- None of the three canary strings occurs in any shareable text artifact in the ZIP.
- The two images are original sanitized fixture assets with no logos, readable text,
  customer data, or identifiable faces. Both have reviewed alternative text.
- Desktop 1440×1200 and responsive mobile 500×844 screenshots were visually reviewed. The
  500 px width is intentional because Chromium headless enforces that minimum CSS layout
  width; the workflow does not mislabel a cropped 390 px image as a responsive capture.

Review outcome: accepted for the public E3 Golden Path fixture.
