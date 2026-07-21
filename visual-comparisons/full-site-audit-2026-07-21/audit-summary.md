# dev.wptelescope.com migration visual audit

## Scope

- Compared all 24 exported routes at a 1440 x 1200 desktop viewport.
- Compared the five primary-menu routes (`/`, `/courses/`, `/our-teachers/`, `/about-2/`, `/contact-2/`) at a 500 x 844 mobile viewport.
- Captures use the same live WordPress origin (`https://dev.wptelescope.com`) and the generated Astro preview (`http://127.0.0.1:4322`).
- No harness or generated-site source files were changed during this audit.

The four `overview-desktop-*.png` files cover the complete desktop route inventory. Individual `local-*-desktop-viewport.png` and `source-*-desktop-viewport.png` files are the full-size evidence. The `compare-*-desktop-viewport.png` and `compare-*-mobile-viewport.png` files cover the main navigation routes side by side.

## Outcome

This output is not a completed migration. `.moltex/reports/site-pipeline-report.json` identifies it as `workspace_planned_with_unfinished_tasks` with 36 tasks remaining and 15 blocked. `.moltex/reports/verification-migration.json` fails. The baseline report passes because it checks route/content/evidence presence, not visual parity or the absence of visible replacement placeholders.

## Route audit

| Routes | Main disparities |
| --- | --- |
| `/`, `/courses/` | Missing/incorrect gradients, shadows, rounded cards, decorative backgrounds, default heading scale, icons, and section spacing. |
| `/our-teachers/` | Square instead of circular portraits, lost card radius/shadow, missing Book Trial buttons, broken icon/star glyphs, `[+]` converted into placeholders, compressed two-column layout. |
| `/about-2/` | Two visible `spectra/separator` placeholders, wrong hero overlay and typography, unconstrained content width, missing radius/shadow/gradient treatment, incorrect mobile crop and spacing. |
| `/contact-2/` | Constrained hero incorrectly rendered as a horizontal flex row, producing narrow word columns; SureForms shortcode remains visible; form, spacing, and footer are missing. |
| `/services/`, `/neighborhoods/`, `/relocation-guide/`, `/properties/`, `/blog/`, `/contact/`, `/home/`, `/about/`, `/f9318-privacy-policy/` | The generic shell does not reproduce the source theme's non-transparent header, centered content width, typography, footer widgets, page-specific spacing, and form treatment. |
| `/hello-world/`, `/hello-world-2/`, and five long post slugs | Generic route rendering drops featured images, post metadata, previous/next navigation, comments, comment form, and the source post container. |
| `/sample-page/`, `/sample-page-2/` | Body text survives, but the header/footer, content width, typography, background, and vertical rhythm do not match. |
| `/form/2026/` | WordPress redirects this URL to `/`; Astro incorrectly publishes a standalone page containing four unresolved form-block placeholders. |

## Harness changes proposed

### P0 - Prevent incomplete baselines from being mistaken for migrations

1. Make the completion command fail (or emit an explicit non-deployable result) when the migration verifier fails, blocking decisions remain, required tasks are unfinished, or visible placeholders remain in published routes.
2. Distinguish `baseline generated` from `migration complete` in CLI output, preview banners, reports, and exit status.
3. Compile same-origin path-changing source responses such as `/form/2026/ -> /` as redirects/omissions instead of content routes.

### P0 - Fix deterministic Gutenberg/Spectra conversion errors

1. Add deterministic `spectra/separator` rendering (`<hr>` with width, color, thickness, and margins) instead of a decision placeholder.
2. Do not classify `layout.type="constrained"` as flex merely because `justifyContent` exists. Preserve `contentSize`/`wideSize` and center child content.
3. Support Spectra advanced background gradients, `dimRatio`, overlay composition, per-corner radii, per-side borders, shadows, background attachment/repeat, and responsive overrides.
4. Preserve rounded core-image styles (`is-style-rounded`) and translate Spectra SVG/icon names without mojibake.
5. Tighten shortcode tokenization so punctuation-only text such as `[+]` inside a normal link is not treated as a shortcode.
6. Derive inherited/default typography from captured theme/site tokens rather than imposing generic 2.5rem/2.25rem heading defaults.

### P1 - Generate route-family and shell templates

1. Replace the single generic `[...path].astro` presentation with page/post/listing/form renderers selected from canonical route/content type.
2. Render post featured media, author/date/category metadata, navigation, comment state, and reviewed static comment UI where required by the source contract.
3. Model the header as route-aware (transparent overlay versus normal document flow) and generate the observed multi-column footer/widget areas, copyright, contact data, and responsive menu styling.
4. Preserve theme layout tokens (content width, palette, font families/weights, background, and utility classes) instead of applying one hard-coded shell to every route.

### P1 - Make visual verification cover the routes users actually see

1. Select the homepage and every primary-menu route before family representatives; then add routes that introduce distinct block signatures, forms, post templates, redirects, and high layout complexity.
2. Remove the verifier's `publishedRoutes.slice(0, 5)` shortcut. Capture every selected visual-plan route at desktop and mobile viewports.
3. Compare generated captures to bound source evidence using stable signals: perceptual diff/SSIM, page-height bounds, major landmark rectangles, typography, background/image presence, and explicit placeholder detection.
4. Keep human review for nuanced parity, but make gross mutations fail automatically (missing hero, missing featured image, collapsed section, wrong redirect, placeholder, missing form, or large layout displacement).

### P2 - Regression coverage

Add reviewed fixtures and clean-plus-mutation tests for:

- constrained Spectra heroes;
- separators, gradients, shadows, radii, rounded images, and icons;
- the teachers card pattern and `[+]` link text;
- SureForms static replacement and redirect handling;
- transparent versus normal headers and footer widgets;
- post featured-image/meta/comment templates;
- visual-plan primary-navigation coverage and all selected runtime captures.

