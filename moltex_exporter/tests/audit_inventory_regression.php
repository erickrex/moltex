<?php
/**
 * Static regression for the reviewed E1 scanner and artifact inventory.
 *
 * @package Moltex_Exporter
 */

$root     = dirname( __DIR__, 2 );
$registry = file_get_contents( $root . '/moltex_exporter/includes/class-scanner.php' );
$audit    = file_get_contents( $root . '/docs/exporter-audit.md' );

preg_match_all( "/^\s*'([a-z_]+)'\s*=>\s*array\(\s*'class'/m", $registry, $registry_matches );
$registry_keys = array_values( array_unique( $registry_matches[1] ) );

preg_match_all( '/^\| `([a-z_]+)` \| `[^`]+` \/ \d+ \|/m', $audit, $audit_matches );
$audit_keys = array_values( array_unique( $audit_matches[1] ) );

sort( $registry_keys );
sort( $audit_keys );

if ( 33 !== count( $registry_keys ) ) {
	fwrite( STDERR, 'Expected 33 executable registry entries, found ' . count( $registry_keys ) . ".\n" );
	exit( 1 );
}

if ( $registry_keys !== $audit_keys ) {
	fwrite( STDERR, "Audit scanner keys do not match the executable registry.\n" );
	exit( 1 );
}

$required_artifacts = array(
	'site_blueprint.json',
	'site_settings.json',
	'menus.json',
	'widgets.json',
	'user_roles.json',
	'site_options.json',
	'acf_field_groups.json',
	'shortcodes_inventory.json',
	'forms_config.json',
	'hooks_registry.json',
	'page_templates.json',
	'block_patterns.json',
	'rest_api_endpoints.json',
	'redirects_candidates.csv',
	'schema_mysql.sql',
	'translations.json',
	'site_environment.json',
	'plugin_behaviors.json',
	'plugins_fingerprint.json',
	'blocks_usage.json',
	'export_completeness.json',
	'migration_readiness.json',
	'error_log.json',
);

foreach ( $required_artifacts as $artifact ) {
	if ( false === strpos( $audit, '`' . $artifact . '`' ) ) {
		fwrite( STDERR, 'Audit is missing emitted artifact: ' . $artifact . "\n" );
		exit( 1 );
	}
}

echo "audit_inventory_regression: ok (33 scanners, " . count( $required_artifacts ) . " core artifacts)\n";
