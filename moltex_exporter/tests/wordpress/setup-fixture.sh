#!/bin/sh
set -eu

cd /var/www/html

until wp db check --quiet; do
  sleep 2
done

if ! wp core is-installed; then
  wp core install \
    --url="${MOLTEX_SMOKE_URL:-http://localhost:8088}" \
    --title="Moltex E1 Fixture" \
    --admin_user="moltex-admin" \
    --admin_password="moltex-fixture-password" \
    --admin_email="admin@example.invalid" \
    --skip-email
fi

wp plugin activate moltex-exporter
wp option update blogdescription "Disposable public Moltex migration fixture"

if ! wp post get 101 --field=ID >/dev/null 2>&1; then
  wp post create --import_id=101 --post_type=post --post_status=publish --post_name=public-one --post_title="Public One" --post_content="Public fixture body."
  wp post create --import_id=102 --post_type=post --post_status=publish --post_name=public-two --post_title="Public Two" --post_content="Contact [email] for already-redacted help."
  wp post create --import_id=103 --post_type=post --post_status=publish --post_name=public-three --post_title="Public Three" --post_content="Third public fixture body."
  wp post create --import_id=201 --post_type=page --post_status=publish --post_name=about-fixture --post_title="About Fixture" --post_content="About the public fixture."
  wp post create --import_id=202 --post_type=page --post_status=publish --post_name=contact-fixture --post_title="Contact Fixture" --post_content="No personal contact data is stored."
  wp post create --import_id=301 --post_type=post --post_status=private --post_name=private-fixture --post_title="Private Fixture" --post_content="PRIVATE-CONTENT-MUST-NOT-EXPORT"
  wp post meta add 101 public_reference "fixture-public-reference"
  wp post meta add 101 _api_key "SYNTHETIC-SECRET-MUST-NOT-EXPORT"
  wp option add moltex_fixture_api_token "SYNTHETIC-OPTION-MUST-NOT-EXPORT"
fi
