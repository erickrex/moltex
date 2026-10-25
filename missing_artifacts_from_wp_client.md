# Missing artifacts in the Mega Noche WordPress export

This document lists what the Mega Noche legacy export lacks for a faithful
rebuild on django_directorio. "Faithful" means the same content, styles and
design, loaded by a one-off command rather than the phase 8 import interface.

- Export analysed: `meganoche_v2_legacy/` (unzipped from the client zip).
- Exporter: `moltex-export/1`, exporter version 1.2.9, mode `complete`,
  created 2026-08-15, origin `https://dev.meganoche.com`.
- Scope: analysis only. The exporter and the export data were not changed.

## How to read this document

Each gap has four parts:

- **Status.** **Blocking** means the rebuild cannot match the legacy site
  without it. **Nice-to-have** means the rebuild can launch without it, or a
  reasonable substitute exists.
- **Evidence.** What was observed in the export files.
- **Exporter must capture.** The additional data the exporter plugin needs to
  emit.
- **Likely source.** Where the data lives on the WordPress site. Each source
  is marked **Fact** (confirmed by the export itself, for example a table name
  and row count in `plugins/database_tables.json` or a URL in the content) or
  **Assumption** (based on how WordPress, GeoDirectory, Kadence and the other
  plugins normally store data, not confirmed against this site).

`plugins/database_tables.json` lists every table with its row count, but
not its rows. Many gaps below come from comparing those row counts with what
the exporter actually emitted.

## Summary

| # | Gap | Category | Status |
|---|-----|----------|--------|
| M1 | 592 of 720 media files not bundled (deferred) | Media | Blocking |
| M2 | Listing videos (37 `.mp4` files) not in the media map | Media | Blocking |
| M3 | Site logo and site icon not exported | Media | Blocking |
| M4 | Map marker image `pin_bar_pink` not exported | Media | Blocking |
| M5 | Alt text empty on all 720 media items | Media | Nice-to-have |
| C1 | Fields removed by the privacy filter (price per hour, featured, tags, email, package) | Content | Blocking (price, featured); Nice-to-have (rest) |
| C2 | Field definitions incomplete (25 of 121 rows missing, attributes missing) | Schema | Blocking |
| C3 | Nightclub `video` field has values but no definition | Schema | Blocking |
| C4 | Category metadata (icons, images, colours, descriptions, hierarchy) | Content | Blocking |
| C5 | Review rating criteria labels, and 8 missing reviews | Content | Blocking (labels); Nice-to-have (count) |
| C6 | Location records (slugs, coordinates, descriptions) | Content | Blocking |
| C7 | Sort and search configuration | Schema | Nice-to-have |
| C8 | Mega Stories content (`wp_story` post type) | Content | Blocking if stories stay |
| C9 | Site timezone for business hours | Metadata | Nice-to-have |
| C10 | Legacy pipe-separated gallery strings and odd `__2540` postmeta key | Content | Nice-to-have |
| S1 | Snapshots: no mobile view, no archives, no search results | Styling | Blocking |
| S2 | Font files (Roboto loaded from Google Fonts) | Styling | Nice-to-have |
| S3 | Popup design (`popup_theme`) | Styling | Nice-to-have |
| S4 | Kadence per-block generated CSS | Styling | Nice-to-have |
| F1 | Forminator form 3806 (subscription popup form) | Functional | Nice-to-have |
| F2 | Redirection plugin rules (30 rules) | SEO | Blocking |
| F3 | Spanish translation overrides (Loco Translate) | Functional | Nice-to-have |
| F4 | Code Snippets (4 custom PHP snippets) | Functional | Nice-to-have, needs review |
| F5 | MailPoet subscribers and list | Functional | Nice-to-have |
| U1 | User accounts and listing ownership | Users | Nice-to-have |
| U2 | UsersWP registration and profile fields | Users | Nice-to-have |
| X1 | Production domain unknown | Metadata | Blocking |
| X2 | Adult-consent records for every listed person | Compliance | Blocking for launch |
| X3 | Zip over the 25 MiB upload limit; stray `_verify6.sh` | Export hygiene | Nice-to-have |

## What the export already covers

These parts are present and good enough for the rebuild. They are listed so
the gaps below are not read as "the export is unusable".

- **Listings.** 121 published listings: 14 `gd_chicas`, 107 `gd_nightclubs`.
  Each has title, content, legacy permalink, address, categories, custom field
  values and media references. 119 have coordinates, 31 have reviews and a
  review summary, 23 have tags. `export_completeness.json` reports zero
  failures.
- **Pages and posts.** 35 pages, 7 posts and 2 popups, with parsed Kadence
  block trees (`blocks`) and raw HTML.
- **Design tokens.** `theme/theme_mods.json` holds the Kadence header and
  footer layout, logo width (170 px), navigation colours, button styles and the
  base font (Roboto, 17 px, line height 1.6). `theme/rendered/` holds 25
  rendered stylesheets, including the global palette variables
  (`--global-palette*`) and the Customizer custom CSS (post 39).
- **SEO.** `seo_full.json` holds Yoast data for 165 URLs.
- **Navigation and forms.** `menus.json` (2 menus, 4 locations) and
  `forms_config.json` (all 5 Ninja Forms).

## Media

### M1. 592 of 720 media files are not bundled

- **Status:** Blocking.
- **Evidence:** In `media/media_map.json`, 128 items have status `bundled`
  and 592 have status `deferred` (`method: source-fetch`, `artifact: null`).
  Most deferred items are listing gallery images, for example
  `2025/05/chicas_mia_5.jpg`. One deferred URL was fetched and is still online.
- **Exporter must capture:** Every original file referenced by
  `media_map.json`, written under `media/YYYY/MM/`. If size limits require it,
  split the export into a data part and one or more media parts, each with a
  SHA-256 checksum per file.
- **Likely source:**
  - Fact: the files are in `wp-content/uploads/YYYY/MM/`, as the URLs show.
  - Fact: GeoDirectory gallery rows are in `wp_geodir_attachments` (1017 rows).
  - Assumption: the gap between 1017 attachment rows and 720 media items comes
    from unpublished listings, revisions or non-image attachments. The exporter
    should report that difference instead of leaving it implicit.

### M2. Listing videos are not in the media map

- **Status:** Blocking. 28 nightclub listings show a video.
- **Evidence:** 37 `.mp4` URLs are referenced in the content, for example
  `2025/05/club_salome_video_1.mp4`. None of them appears in `media_map.json`.
  Every media map item is `image/jpeg`, `image/png` or `image/gif`, which
  suggests the exporter only collects images. Values appear in the nightclub
  custom field `video` and in `legacy_public_postmeta.geodir_video` (28
  listings). One Chicas listing also references a video
  (`chicas_mia_video_1.mp4`).
- **Exporter must capture:** Video files as media items with MIME type,
  duration, dimensions, poster image (if any) and checksum, linked to the
  listing and to the field that references them.
- **Likely source:**
  - Fact: the files are in `wp-content/uploads/2025/05/`.
  - Fact: the references are in the `video` column of
    `wp_geodir_gd_nightclubs_detail` (`detail_storage:
    geodirectory_cpt_detail`) and in the `geodir_video` postmeta key.
  - Assumption: each video has an attachment row in `wp_posts`
    (`post_type = attachment`, `post_mime_type = video/mp4`).

### M3. Site logo and site icon are not exported

- **Status:** Blocking. The header shows the logo on every page.
- **Evidence:** `theme/theme_mods.json` has `custom_logo: 3751`, but
  attachment 3751 is not in `media_map.json`. The snapshots reference
  `2025/05/cropped-Proyecto-nuevo-2-scaled-1.png` (logo) and
  `2025/04/cropped-cropped-logo_meganoche_2025-*.png` in 32, 180, 192 and 270
  px sizes (site icon). Neither file is in the media map. `site_options.json`
  does not include the `site_icon` option.
- **Exporter must capture:** Every attachment referenced by theme settings
  and site options, not only attachments referenced by posts. At minimum:
  `custom_logo`, `site_icon` and any Kadence settings that point to images
  (mobile logo, transparent header logo, background images).
- **Likely source:**
  - Fact: logo = attachment 3751 (`wp_posts`), referenced from the
    `theme_mods_kadence` option.
  - Assumption: site icon = the `site_icon` option in `wp_options`, pointing to
    the attachment for `logo_meganoche_2025`.

### M4. Map marker image is not exported

- **Status:** Blocking for visual parity of the map.
- **Evidence:** `2025/04/pin_bar_pink-scaled-e1745855403461.png` is referenced
  in content and snapshots but is not in `media_map.json`.
- **Exporter must capture:** Marker icons, with the category or post type
  each one belongs to.
- **Likely source:**
  - Fact: the file is in `wp-content/uploads/2025/04/`.
  - Assumption: it is the category marker icon stored as GeoDirectory term
    meta (`ct_cat_icon`) in `wp_termmeta` or `wp_geodir_term_meta` (28 rows).
    It may also be a GeoDirectory default marker setting in the `geodir_settings`
    option.

### M5. Alt text is empty on all media

- **Status:** Nice-to-have. The rebuild can generate alt text from the
  listing name, but the legacy values should be checked first.
- **Evidence:** All 720 media items have an empty `alt`.
- **Exporter must capture:** `_wp_attachment_image_alt` for each attachment,
  and the GeoDirectory image title and caption.
- **Likely source:** Assumption: the alt text really is empty in the source.
  WordPress stores it in `wp_postmeta` (`_wp_attachment_image_alt`), and
  GeoDirectory stores image titles in `wp_geodir_attachments`. The exporter
  should confirm the value is empty instead of omitting it.

## Content and schema

### C1. Fields removed by the privacy filter

- **Status:**
  - Blocking: `precio_por_hora` (if it shows publicly) and `featured`.
  - Nice-to-have: `post_tags` (Chicas), `email`, `ciudad_donde_esta_ubicada`,
    `package_id`, `expire_date`.
- **Evidence:** `geodirectory.json` → `privacy.excluded_field_keys` lists
  `ciudad_donde_esta_ubicada`, `email`, `expire_date`, `featured`,
  `package_id`, `post_tags` and `precio_por_hora`. The Chicas `precio_html`
  table is exported. The hourly price is not.
- **Exporter must capture:** For each excluded field, at least its definition
  and whether it is shown publicly. Then, depending on the client's decision:
  - The values of fields that are public on the live site (price per hour,
    featured flag, tags).
  - A per-listing boolean "email present" instead of the address, so contact
    forms can be configured without exporting personal data.
  - Package and expiry values if paid tiers continue. The nightclub categories
    `oro`, `plata` and `bronce` look like tiers modelled as categories, so this
    matters for the rebuild's taxonomy design.
- **Likely source:**
  - Fact: the values are columns of `wp_geodir_gd_chicas_detail` and
    `wp_geodir_gd_nightclubs_detail`.
  - Fact: `wp_geodir_post_packages` (4 rows), `wp_geodir_price` (5 rows) and
    `wp_geodir_pricemeta` (71 rows) hold the Pricing Manager packages.

### C2. Field definitions are incomplete

- **Status:** Blocking. Without these attributes the custom fields cannot be
  rebuilt with the same labels, order, icons and display rules.
- **Evidence:**
  - `wp_geodir_custom_fields` has 121 rows. `geodirectory.json` defines 96
    fields: 74 for Chicas, 7 for Nightclubs and 15 for the unused `gd_place`.
    That leaves 25 definitions unaccounted for, more than the 7 excluded
    fields explain.
  - Each exported definition has only `key`, `label`, `field_type`,
    `data_type`, `show_in` and `sort_order`.
- **Exporter must capture:** The full row for every field, including
  `is_active`, `is_required`, `required_msg`, `default_value`,
  `option_values` (for select and radio fields), `placeholder_value`,
  `field_icon`, `css_class`, `cat_sort`, `cat_filter`, `for_admin_use`,
  `is_public`, `validation_pattern`, `validation_msg`, `extra_fields` and
  `tab_parent`/`tab_level`. It also needs a reason for each field it skips.
- **Likely source:** Fact: `wp_geodir_custom_fields` (121 rows). Assumption:
  the column names above match GeoDirectory 2.8 (`2.8.116` per the snapshot
  asset URLs).

### C3. Nightclub `video` field has values but no definition

- **Status:** Blocking (same reason as M2).
- **Evidence:** Every nightclub listing has a `video` key in `custom_fields`,
  but `geodirectory.json` has no `video` field for `gd_nightclubs`.
- **Exporter must capture:** The definition of every field that has values.
  The exporter should fail or warn when a value has no matching definition.
- **Likely source:** Assumption: a `wp_geodir_custom_fields` row with
  `htmlvar_name = video`, probably one of the 25 missing rows in C2.

### C4. Category metadata

- **Status:** Blocking. Category icons, colours and images appear on cards,
  map markers and archive headers.
- **Evidence:** Listings carry only `term_id`, `name`, `slug` and `taxonomy`
  for each category. The export has no term list, so there are no
  descriptions, parent-child relations, icons, default images or colours.
  Five categories are in use: Nightclubs `bronce` (57), `plata` (37), `oro`
  (13); Chicas `Colombianas` (9), `Rubias` (6). Categories with zero listings
  are not visible at all.
- **Exporter must capture:** Every term of `gd_chicascategory`,
  `gd_nightclubscategory` and the tag taxonomies, including empty ones. For
  each term: description, parent, count, order, and GeoDirectory term meta
  (icon, default image, colour, top and bottom description, schema type),
  with the referenced images added to the media map.
- **Likely source:**
  - Fact: `wp_geodir_term_meta` (28 rows).
  - Assumption: `wp_terms`, `wp_term_taxonomy` and `wp_termmeta` with keys
    `ct_cat_icon`, `ct_cat_default_img`, `ct_cat_color`, `ct_cat_top_desc` and
    `ct_cat_schema`.

### C5. Review rating criteria and missing reviews

- **Status:**
  - Blocking: criteria labels, because multi-criteria ratings cannot be shown
    without them.
  - Nice-to-have: the 8 missing reviews.
- **Evidence:**
  - 100 reviews were exported. 84 have an empty `ratings` value. 16 have
    criteria keyed only by numeric IDs (`"1"` to `"5"`), with no names.
  - `wp_geodir_rating_category` and `wp_geodir_rating_style` each have 5 rows.
    `wp_geodir_post_review` has 108 rows.
- **Exporter must capture:** Each criterion (ID, title, post types,
  categories, display order, style, star count and labels). For each review:
  approval status and, if images are attached, those images. The exporter
  should also report why the other 8 reviews were excluded (for example
  unapproved, spam, or attached to an unpublished listing).
- **Likely source:**
  - Fact: `wp_geodir_rating_category` and `wp_geodir_rating_style`.
  - Fact: `wp_geodir_post_review`, plus `wp_comments` for the review text.

### C6. Location records

- **Status:** Blocking. Legacy URLs contain location slugs
  (`/chicas/quito/3596/`, `/nightclubs/carcelen/...`), so the rebuild needs
  the same slugs to keep URLs and archive pages.
- **Evidence:** Each listing has only `city`, `region`, `country` and
  `street` strings. There is no postcode, no location slug and no
  neighbourhood. `wp_geodir_post_locations` has 38 rows.
  `wp_geodir_post_neighbourhood` and `wp_geodir_location_seo` are empty.
- **Exporter must capture:** Every location row (country, region, city,
  slugs, latitude, longitude, default flag, description, meta title and meta
  description), and for each listing the location ID, postcode and the
  neighbourhood, if any.
- **Likely source:** Fact: `wp_geodir_post_locations` (38 rows). Assumption:
  postcode and neighbourhood are columns of the `wp_geodir_gd_*_detail`
  tables.

### C7. Sort and search configuration

- **Status:** Nice-to-have. django_directorio has its own filters, but the
  legacy defaults show what users expect.
- **Evidence:** `wp_geodir_custom_sort_fields` has 9 rows, but only 3 sort
  options are exported (1 for Chicas, 2 for `gd_place`, 0 for Nightclubs).
  `search_fields` is empty for every post type, and
  `wp_geodir_custom_advance_search_fields` has 0 rows. The snapshots load the
  `geodir_advance_search_filters` plugin.
- **Exporter must capture:** All 9 sort rows (including default sort and
  active flags), the Advanced Search plugin settings, and the attributes of
  every search block or widget used on pages.
- **Likely source:**
  - Fact: `wp_geodir_custom_sort_fields` (9 rows).
  - Assumption: search fields are configured in the attributes of GeoDirectory
    search blocks inside page content, or in the `geodir_settings` option,
    because the dedicated table is empty.

### C8. Mega Stories content

- **Status:** Blocking if stories remain on profiles. This is an open
  decision for the client.
- **Evidence:** `plugins/custom_post_types.json` lists `wp_story` as a
  non-public post type. It was not exported. The Chicas detail template
  (`content/page/chicas-details.json`) uses the `gd-listing-stories-block`
  block, and the snapshots load `mega_stories` assets. No story content is in
  the export.
- **Exporter must capture:** All `wp_story` posts, their media (images and
  videos), their link to a listing, publish and expiry dates, and display
  order.
- **Likely source:**
  - Fact: the `wp_story` post type in `wp_posts`.
  - Assumption: the listing link and expiry are in `wp_postmeta`. No dedicated
    `mega_stories` table appears in `database_tables.json`.

The exporter skips non-public post types, so the same pattern also drops
`forminator_forms` (F1), `popup_theme` (S3), `kadence_form`, `kadence_header`,
`kadence_navigation` and `kb_icon`. The header and navigation appear to be
built from Customizer settings, which are exported. Assumption: the Kadence
post types are unused, but the exporter should list them with counts so that
can be confirmed.

### C9. Site timezone

- **Status:** Nice-to-have. Ecuador is UTC−5 with no daylight saving time, so
  the value can be set by hand.
- **Evidence:** `site_options.json` has an empty `timezone_string` and no
  `gmt_offset`. Business hours are exported as strings such as
  `"Mo 12:00-00:00"` with no timezone.
- **Exporter must capture:** `gmt_offset` and `timezone_string`, and the
  timezone stored inside each GeoDirectory business hours value.
- **Likely source:**
  - Fact: `wp_options` (`gmt_offset`, `timezone_string`).
  - Fact: `wp_geodir_business_hours` (698 rows).
  - Assumption: GeoDirectory stores a UTC offset inside the `business_hours`
    field value.

### C10. Legacy gallery strings and stray postmeta

- **Status:** Nice-to-have. The normalized `geodirectory.media` list already
  covers the images.
- **Evidence:** `content/gd_nightclubs/5-climate-c5-by-cero-km.json` has a
  `postmeta.__2540.post_images` value in the old GeoDirectory format
  `url|id||::url|id||`. The `__2540` key suggests data from another post (a
  revision or a duplicate) nested into this one.
- **Exporter must capture:** Only normalized media lists, plus an explanation
  of nested postmeta keys. Raw legacy strings should be dropped or moved to a
  clearly labelled diagnostic field.
- **Likely source:** Assumption: `wp_postmeta` of post 2540, picked up by the
  exporter's postmeta walk.

## Styling and design

### S1. Snapshots are not enough for visual parity

- **Status:** Blocking for the Chicas templates and for mobile layouts.
- **Evidence:** 12 HTML snapshots, all desktop:
  - Home three times (`meganoche.html`, `clubs.html` and `club-item.html` all
    have canonical `https://dev.meganoche.com/`).
  - One Chicas profile (`altoano.html`) and one nightclub profile
    (`bohemia-kassandra-kfc-cerrado-permanentemente.html`).
  - Add-listing, blog, contact, test pages and the subscription popup.
  - Missing: Chicas archive, Nightclubs archive, category and location
    archives, search results, user profile, compare and saved lists. There
    are no mobile or tablet snapshots and no screenshots.
- **Exporter must capture:**
  - One snapshot per template: home, each post type archive, a category
    archive, a location archive, search results, each post type's detail
    page, profile, compare and 404.
  - Each snapshot as HTML plus a full-page PNG, at 390 px, 768 px and
    1440 px widths.
  - It should resolve each requested URL and refuse to save a snapshot whose
    canonical URL differs from the requested one, so the home page cannot be
    saved three times again.
- **Likely source:** Fact: the rendered front end of `dev.meganoche.com`. This
  is not stored data, so the exporter (or a headless browser run beside it)
  has to render it.

### S2. Font files

- **Status:** Nice-to-have. Roboto is freely available and django_directorio
  can self-host it.
- **Evidence:** The snapshots load Roboto (regular and 700) from
  `fonts.googleapis.com`. No font files are in the export. Font Awesome 6.7.2
  CSS is exported (`rendered_font-awesome-svg-styles.css`), but the SVG and
  webfont assets it references are not.
- **Exporter must capture:** The font families, weights and subsets in use,
  and any locally hosted font files (`wp_font_face`, `kt_font`, or files under
  `wp-content/uploads/fonts/`).
- **Likely source:**
  - Fact: the `base_font` theme mod (`google: true`).
  - Fact: Font Awesome is under `wp-content/uploads/font-awesome/v6.7.2/`.
  - Assumption: no custom fonts are uploaded.

### S3. Popup design

- **Status:** Nice-to-have. Whether the subscription popup stays is an open
  client decision (phase 9, task 9.4).
- **Evidence:** Both popups are exported with their postmeta, but the
  `popup_theme` post type (Popup Maker themes: overlay, container, close
  button styles) is not. The trigger and cookie settings were not checked in
  detail.
- **Exporter must capture:** The assigned `popup_theme` for each popup with
  its settings, plus triggers, cookies and conditions in a readable form.
- **Likely source:** Assumption: `wp_posts` (`post_type = popup_theme`) and
  `wp_postmeta` (`popup_theme_settings`, `popup_settings`).

### S4. Kadence per-block generated CSS

- **Status:** Nice-to-have. The block attributes are exported, so the styles
  can be rebuilt from them.
- **Evidence:** Page `blocks` include Kadence attributes such as `uniqueID`,
  column layouts and borders. Only 26 Kadence row or column rules are in
  `rendered_inline_all.css`, collected from the pages that were snapshotted.
- **Exporter must capture:** The generated CSS for each post, keyed by post
  ID.
- **Likely source:** Assumption: Kadence Blocks prints this CSS inline per
  request, or caches it in `wp_postmeta` (`_kad_blocks_custom_css` and
  similar) or under `wp-content/uploads/kadence/`.

## Functional configuration

### F1. Forminator form 3806

- **Status:** Nice-to-have. It is the subscription popup form, which depends
  on decision 9.4.
- **Evidence:** The snapshots and rendered CSS reference
  `forminator/3806_.../css/style-3806.css`. `forms_config.json` detects only
  Ninja Forms. `wp_frmt_form_entry` has 157 rows.
- **Exporter must capture:** Forminator form definitions (fields, validation,
  notifications, destinations). Submissions are not needed.
- **Likely source:** Fact: `forminator_forms` post type (ID 3806). Assumption:
  the definition is in `wp_postmeta` (`forminator_form_meta`).

### F2. Redirection plugin rules

- **Status:** Blocking. Lost redirects lose search traffic.
- **Evidence:** `wp_redirection_items` has 30 rows and
  `wp_redirection_groups` has 2. No redirect rules are in the export, and
  `seo_full.json` has `redirect_ownership: null` for the pages checked.
  `wp_redirection_404` has 789 rows.
- **Exporter must capture:** Every redirect (source, regex flag, target,
  HTTP code, match type, group, enabled status). Optionally the top 404 paths
  from the log, aggregated and without IP addresses or user agents, to find
  URLs that still need redirects.
- **Likely source:** Fact: `wp_redirection_items`, `wp_redirection_groups` and
  `wp_redirection_404`.

### F3. Spanish translation overrides

- **Status:** Nice-to-have. django_directorio has its own Spanish
  translation, but the client's wording for GeoDirectory and UsersWP labels
  would be lost.
- **Evidence:** `site_settings.json` reports locale `en_US`, while the
  front end is in Spanish. Loco Translate is active (the administrator role
  has `loco_admin`). No `.po` or `.mo` files are in the export.
- **Exporter must capture:** Custom translation files for the active
  plugins and the theme.
- **Likely source:** Assumption: `wp-content/languages/loco/plugins/` and
  `wp-content/languages/loco/themes/`, or `wp-content/languages/`.

### F4. Code Snippets

- **Status:** Nice-to-have, but needs review. Snippets can change behaviour
  that does not show in the data (redirects, field formatting, access rules).
- **Evidence:** The `wp_snippets` table has 4 rows. No snippet code is in the
  export. `hooks_registry.json` and `theme/functions.php` are exported.
- **Exporter must capture:** Each snippet's name, description, scope, active
  flag and code, so a developer can review it. The code is not to be run.
- **Likely source:** Fact: `wp_snippets` (4 rows).

### F5. MailPoet subscribers

- **Status:** Nice-to-have. This is personal data, so it needs a decision
  from the client before it is exported.
- **Evidence:** `wp_mailpoet_subscribers` has 23 rows and
  `wp_mailpoet_segments` has 3. Neither is exported.
- **Exporter must capture:** If the client agrees: subscriber email, status,
  lists and consent date. Otherwise, only the lists and their counts.
- **Likely source:** Fact: `wp_mailpoet_subscribers`,
  `wp_mailpoet_subscriber_segment` and `wp_mailpoet_segments`.

## Users

### U1. User accounts and listing ownership

- **Status:** Nice-to-have for a visual rebuild. It becomes blocking if
  listing owners must log in and edit their listings on day one.
- **Evidence:** Listings carry only `author.display_name` (for example
  "Mary"). No user list, user ID, email or role assignment is exported.
  `user_roles.json` describes roles but not users.
- **Exporter must capture:** For each user who owns a listing or a review:
  a stable user ID, display name, role and the listing IDs they own. Emails
  only with the client's agreement. Never passwords.
- **Likely source:** Fact: `post_author` in `wp_posts`. Assumption:
  `wp_users` and `wp_usermeta` (`wp_capabilities`), and `wp_uusermeta`
  (12 rows) for UsersWP profile data.

### U2. UsersWP registration and profile fields

- **Status:** Nice-to-have.
- **Evidence:** `wp_uform_fields` has 17 rows, `wp_uprofile_tabs` 1 and
  `wp_uuser_sorting` 8. None of it is exported.
- **Exporter must capture:** The registration and profile form fields
  (key, label, type, required flag, order).
- **Likely source:** Fact: `wp_uform_fields`, `wp_uprofile_tabs` and
  `wp_uuser_sorting`.

## Site metadata, compliance and export hygiene

### X1. Production domain

- **Status:** Blocking for SEO (canonical URLs, sitemaps, redirects).
- **Evidence:** `home` and `siteurl` are `https://dev.meganoche.com`. All
  canonical URLs, Yoast data and media URLs use that host.
- **Exporter must capture:** Nothing more. The exporter reports what the site
  says. The client must confirm whether `dev.meganoche.com` is the live site
  or the production domain is different.
- **Likely source:** Not in WordPress if production is a separate install.

### X2. Adult-consent records

- **Status:** Blocking for launch, not for building the rebuild.
- **Evidence:** Nothing in the export records that each person listed in
  Chicas is an adult who agreed to be published. Phase 9 task 9.7 requires a
  written policy.
- **Exporter must capture:** Nothing. The client must supply this.
- **Likely source:** Assumption: not stored in WordPress at all.

### X3. Package size and stray file

- **Status:** Nice-to-have, because the one-off command reads the unzipped
  folder. It matters again once the upload interface exists.
- **Evidence:** The zip is 34.9 MB. The phase 8 upload limit is 25 MiB. The
  zip also contains `_verify6.sh`, a test script from the WSL machine that is
  not part of the export.
- **Exporter must capture:** Nothing extra. The export should be split into
  parts under the limit (see M1), and only files listed in `bundle.json`
  should be included.

## Requests outside the exporter

These items cannot be solved by changing the exporter and must come from the
client:

1. The production domain (X1).
2. Whether `precio_por_hora` and the featured flag show publicly (C1).
3. Whether stories (C8) and the subscription popup (S3, F1) stay.
4. Agreement to export user emails and subscribers (U1, F5).
5. The adult-consent policy (X2).
