#!/bin/sh
set -eu

cd /var/www/html

until wp db check --quiet; do
  sleep 2
done

site_url="${MOLTEX_SMOKE_URL:-http://localhost:8094}"
plugin_root="/var/www/html/wp-content/plugins/moltex-exporter"

if ! wp core is-installed; then
  wp core install \
    --url="$site_url" \
    --title="Lakeside Commons" \
    --admin_user="moltex-admin" \
    --admin_password="moltex-fixture-password" \
    --admin_email="admin@example.invalid" \
    --skip-email
fi

wp option update home "$site_url"
wp option update siteurl "$site_url"
wp option update blogname "Lakeside Commons"
wp option update blogdescription "Workshops, stories, and practical information from a small lakeside community space."
wp option update permalink_structure '/%postname%/'
wp rewrite flush --hard

cp -R "$plugin_root/tests/wordpress/fixtures/wordpress-seo" /var/www/html/wp-content/plugins/
cp -R "$plugin_root/tests/wordpress/fixtures/golden-path-capability" /var/www/html/wp-content/plugins/
wp plugin activate moltex-exporter wordpress-seo golden-path-capability

existing_ids="$(wp post list --post_type=post,page,attachment --format=ids)"
if [ -n "$existing_ids" ]; then
  # shellcheck disable=SC2086
  wp post delete $existing_ids --force >/dev/null
fi

menu_ids="$(wp menu list --fields=term_id --format=ids)"
if [ -n "$menu_ids" ]; then
  # shellcheck disable=SC2086
  wp menu delete $menu_ids >/dev/null
fi

hero_id="$(wp media import "$plugin_root/tests/wordpress/fixtures/golden-media/lakeside-pavilion.png" \
  --title="Lakeside pavilion at sunrise" \
  --alt="Timber community pavilion beside a calm lake in autumn" \
  --porcelain)"
workshop_id="$(wp media import "$plugin_root/tests/wordpress/fixtures/golden-media/community-workshop.png" \
  --title="Community flower workshop" \
  --alt="Hands arranging local flowers and ceramic cups on a wooden workshop table" \
  --porcelain)"
hero_url="$(wp post get "$hero_id" --field=guid)"
workshop_url="$(wp post get "$workshop_id" --field=guid)"

home_content="<figure class=\"wp-block-image size-full\"><img src=\"$hero_url\" alt=\"Timber community pavilion beside a calm lake in autumn\" class=\"wp-image-$hero_id\" /></figure>
<h1>A place to learn, make, and meet by the lake</h1>
<p>Lakeside Commons is a small public pavilion for practical workshops, local stories, and quiet visits.</p>
<h2>Plan a visit</h2><p>Find seasonal opening hours, accessibility notes, and low-impact travel information.</p>
<p><a href=\"$site_url/visit/\">Visitor information</a> · <a href=\"$site_url/stories/\">Latest stories</a></p>"
about_content="<h1>About Lakeside Commons</h1><p>The commons is a fictional, sanitized demonstration site built inside a real WordPress installation for the Moltex Golden Path.</p><p>Its content is original and contains no production customer data.</p>"
visit_content="<h1>Visit</h1><p>The pavilion has step-free access, bicycle parking, and a quiet room. Public transport stops at Market Square.</p>[lake_schedule season=\"autumn\"]<h2>Map decision</h2><p>The source site embeds an external map that must receive an explicit static-site disposition.</p><iframe src=\"https://www.youtube.com/embed/aqz-KE-bpKQ\" title=\"Fixture external media embed\"></iframe>"
contact_content="<h1>Contact and access</h1><p>For the public fixture, contact details are intentionally represented as reviewed placeholders.</p><p>Email: [email]</p>"
stories_content="<h1>Stories from the commons</h1><p>Workshop notes, seasonal observations, and practical updates from Lakeside Commons.</p>"

wp post create --import_id=201 --post_type=page --post_status=publish --post_name=home --post_title="Home" --post_content="$home_content" >/dev/null
wp post create --import_id=202 --post_type=page --post_status=publish --post_name=about --post_title="About" --post_content="$about_content" >/dev/null
wp post create --import_id=203 --post_type=page --post_status=publish --post_name=visit --post_title="Visit" --post_content="$visit_content" >/dev/null
wp post create --import_id=204 --post_type=page --post_status=publish --post_name=contact --post_title="Contact" --post_content="$contact_content" >/dev/null
wp post create --import_id=205 --post_type=page --post_status=publish --post_name=stories --post_title="Stories" --post_content="$stories_content" >/dev/null

wp post create --import_id=101 --post_type=post --post_status=publish --post_name=autumn-workshops --post_title="Autumn workshops open for booking" --post_date="2026-06-02 09:00:00" --post_content="<figure><img src=\"$workshop_url\" alt=\"Hands arranging local flowers and ceramic cups on a wooden workshop table\" /></figure><p>Three small-group sessions explore seasonal flowers, clay, and shared meals.</p>" >/dev/null
wp post create --import_id=102 --post_type=post --post_status=publish --post_name=shoreline-notes --post_title="Shoreline notes: early autumn" --post_date="2026-06-09 09:00:00" --post_content="<p>Reeds are turning gold and the eastern path remains open after the habitat survey.</p>" >/dev/null
wp post create --import_id=103 --post_type=post --post_status=publish --post_name=volunteer-table --post_title="A longer table for community suppers" --post_date="2026-06-16 09:00:00" --post_content="<p>Volunteers repaired the pavilion table using reclaimed local timber.</p>" >/dev/null
wp post create --import_id=301 --post_type=post --post_status=private --post_name=private-board-notes --post_title="Private board notes" --post_content="PRIVATE-GOLDEN-CONTENT-MUST-NOT-EXPORT" >/dev/null

wp post meta update 101 _thumbnail_id "$workshop_id" >/dev/null
wp post meta update 101 public_reference "golden-public-reference" >/dev/null
wp post meta update 101 _api_key "GOLDEN-SECRET-MUST-NOT-EXPORT" >/dev/null
wp option update moltex_fixture_api_token "GOLDEN-OPTION-SECRET-MUST-NOT-EXPORT" >/dev/null

for post_id in 201 202 203 204 205 101 102 103; do
  title="$(wp post get "$post_id" --field=post_title) | Lakeside Commons"
  description="Reviewed migration fixture description for $(wp post get "$post_id" --field=post_name)."
  wp post meta update "$post_id" _yoast_wpseo_title "$title" >/dev/null
  wp post meta update "$post_id" _yoast_wpseo_metadesc "$description" >/dev/null
  wp post meta update "$post_id" _yoast_wpseo_schema_page_type WebPage >/dev/null
done
wp option update wpseo_titles '{"breadcrumbs-enable":true,"breadcrumbs-sep":"/"}' --format=json >/dev/null

wp option update show_on_front page
wp option update page_on_front 201
wp option update page_for_posts 205

wp menu create "Primary Navigation" >/dev/null
wp menu item add-post primary-navigation 201 --title="Home" >/dev/null
wp menu item add-post primary-navigation 202 --title="About" >/dev/null
wp menu item add-post primary-navigation 203 --title="Visit" >/dev/null
stories_item="$(wp menu item add-post primary-navigation 205 --title="Stories" --porcelain)"
wp menu item add-post primary-navigation 101 --title="Autumn workshops" --parent-id="$stories_item" >/dev/null
wp menu item add-post primary-navigation 102 --title="Shoreline notes" --parent-id="$stories_item" >/dev/null
wp menu item add-post primary-navigation 103 --title="Community suppers" --parent-id="$stories_item" >/dev/null
wp menu item add-post primary-navigation 204 --title="Contact" >/dev/null

wp option delete moltex_reference_screenshots >/dev/null 2>&1 || true

printf '{"site_url":"%s","hero_id":%s,"workshop_id":%s,"public_content":8,"referenced_media":2}\n' \
  "$site_url" "$hero_id" "$workshop_id"
