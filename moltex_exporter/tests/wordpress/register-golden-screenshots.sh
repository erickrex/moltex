#!/bin/sh
set -eu

cd /var/www/html

plugin_root="/var/www/html/wp-content/plugins/moltex-exporter"
desktop_path="$plugin_root/tests/wordpress/golden-output/home-desktop.png"
mobile_path="$plugin_root/tests/wordpress/golden-output/home-mobile.png"

if [ ! -f "$desktop_path" ] || [ ! -f "$mobile_path" ]; then
  echo "Golden Path screenshots are missing." >&2
  exit 1
fi

desktop_id="$(wp media import "$desktop_path" --title="Golden Path home desktop reference" --alt="Lakeside Commons homepage desktop reference" --porcelain)"
mobile_id="$(wp media import "$mobile_path" --title="Golden Path home mobile reference" --alt="Lakeside Commons homepage mobile reference" --porcelain)"

references="[{\"attachment_id\":$desktop_id,\"route\":\"/\",\"viewport\":\"desktop-1440x1200\",\"label\":\"home\"},{\"attachment_id\":$mobile_id,\"route\":\"/\",\"viewport\":\"mobile-500x844\",\"label\":\"home\"}]"
wp option update moltex_reference_screenshots "$references" --format=json >/dev/null

printf '{"desktop_attachment_id":%s,"mobile_attachment_id":%s,"screenshot_count":2}\n' "$desktop_id" "$mobile_id"
