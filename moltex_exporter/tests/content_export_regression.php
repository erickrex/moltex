<?php
/**
 * Regression checks for exporting per-item content JSON files.
 *
 * Run with:
 * php tests/content_export_regression.php
 */

if ( ! defined( 'WPINC' ) ) {
	define( 'WPINC', 'wp-includes' );
}
if ( ! defined( 'ABSPATH' ) ) {
	define( 'ABSPATH', dirname( __DIR__ ) . '/' );
}

require_once dirname( __DIR__ ) . '/includes/trait-error-logger.php';

function trailingslashit( $string ) {
	return rtrim( $string, '/\\' ) . '/';
}

function wp_mkdir_p( $target ) {
	return is_dir( $target ) || mkdir( $target, 0777, true );
}

function current_time( $type, $gmt = 0 ) {
	if ( 'timestamp' === $type || 'U' === $type ) {
		return time();
	}

	if ( 'mysql' === $type ) {
		return gmdate( 'Y-m-d H:i:s' );
	}

	return gmdate( $type ?: 'Y-m-d H:i:s' );
}

function wp_json_encode( $data, $options = 0 ) {
	return json_encode( $data, $options );
}

function do_action( $tag ) {
	return null;
}

function apply_filters( $tag, $value ) {
	return $value;
}

function sanitize_file_name( $filename ) {
	return preg_replace( '/[^a-z0-9\\-_\\.]/', '-', strtolower( (string) $filename ) );
}

require_once dirname( __DIR__ ) . '/includes/class-exporter.php';

function assert_true( $condition, $message ) {
	if ( ! $condition ) {
		fwrite( STDERR, "Assertion failed: {$message}\n" );
		exit( 1 );
	}
}

$export_dir = sys_get_temp_dir() . '/moltex_content_export_' . uniqid();
$results = array(
	'site'    => array(
		'site' => array(
			'url'                 => 'https://example.test',
			'home_url'            => 'https://example.test',
			'wp_version'          => '7.0.1',
			'permalink_structure' => '/%postname%/',
			'site_title'          => 'Test Site',
			'language'            => 'en-US',
		),
	),
	'content' => array(
		'export_mode'        => 'complete',
		'posts'             => array(
			array(
				'id'     => 101,
				'type'   => 'post',
				'slug'   => 'sample-post',
				'title'  => 'Sample Post',
				'status' => 'publish',
				'author' => array( 'display_name' => 'Fixture Author' ),
				'date_gmt' => '2026-07-14 20:00:00',
				'modified_gmt' => '2026-07-14 20:00:00',
				'taxonomies' => array(),
				'raw_html' => '<p>Sample Post</p>',
				'legacy_permalink' => 'https://example.test/sample-post/',
				'postmeta' => array(),
			),
			array(
				'id'     => 102,
				'type'   => 'post',
				'slug'   => 'sample-post',
				'title'  => 'Duplicate Slug Post',
				'status' => 'publish',
				'author' => array( 'display_name' => 'Fixture Author' ),
				'date_gmt' => '2026-07-14 20:00:00',
				'modified_gmt' => '2026-07-14 20:00:00',
				'taxonomies' => array(),
				'raw_html' => '<p>Duplicate</p>',
				'legacy_permalink' => 'https://example.test/sample-post/',
				'postmeta' => array(),
			),
		),
		'pages'             => array(
			array(
				'id'     => 202,
				'type'   => 'page',
				'slug'   => 'about-us',
				'title'  => 'About Us',
				'status' => 'publish',
				'author' => array( 'display_name' => 'Fixture Author' ),
				'date_gmt' => '2026-07-14 20:00:00',
				'modified_gmt' => '2026-07-14 20:00:00',
				'taxonomies' => array(),
				'raw_html' => '<p>About Us</p>',
				'legacy_permalink' => 'https://example.test/about-us/',
				'postmeta' => array(),
			),
		),
		'custom_post_types' => array(
			'gd_place' => array(
				array(
					'id'     => 303,
					'type'   => 'gd_place',
					'slug'   => 'sample-cafe',
					'title'  => 'Sample Cafe',
					'status' => 'publish',
					'author' => array( 'display_name' => 'Fixture Author' ),
					'date_gmt' => '2026-07-14 20:00:00',
					'modified_gmt' => '2026-07-14 20:00:00',
					'taxonomies' => array(),
					'raw_html' => '<p>Sample Cafe</p>',
					'legacy_permalink' => 'https://example.test/sample-cafe/',
					'postmeta' => array(),
				),
			),
		),
		'block_usage'       => array(),
		'completeness'      => array(
			'complete'          => true,
			'post_types'        => array(
				'post'     => array( 'discovered' => 2, 'exported' => 2, 'excluded' => 0, 'failed' => 0, 'complete' => true ),
				'page'     => array( 'discovered' => 1, 'exported' => 1, 'excluded' => 0, 'failed' => 0, 'complete' => true ),
				'gd_place' => array( 'discovered' => 1, 'exported' => 1, 'excluded' => 0, 'failed' => 0, 'complete' => true ),
			),
			'excluded_statuses' => array( 'private', 'draft' ),
		),
	),
	'settings' => array(
		'core'       => array(),
		'language'   => array(),
		'reading'    => array(),
		'discussion' => array(),
		'media'      => array(),
	),
	'menus' => array(
		'menu_locations' => array(),
		'menus'           => array(),
	),
	'media' => array(
		'media_map' => array(),
	),
	'migration_readiness' => array(
		'blockers' => array(),
	),
	'seo_full' => array(
		'schema_version' => '1.0.0',
		'pages'          => array(),
	),
	'forms' => array(
		'detected_plugins' => array(),
		'forms'            => array(),
		'forms_in_content' => array(),
		'summary'          => array(),
	),
	'integration_manifest' => array(
		'schema_version' => '1.0.0',
		'integrations'   => array(),
	),
	// These scanners emit structured observations only. Their legacy CSV/SQL
	// sidecars are optional and intentionally absent.
	'redirects' => array(
		'redirect_candidates' => array(),
	),
	'database' => array(
		'custom_tables' => array(),
	),
);

$exporter = new Moltex_Exporter_Exporter( $export_dir, $results );
$result   = $exporter->export_all();

assert_true( ! empty( $result['success'] ), 'Exporter should complete successfully.' );
assert_true( empty( $result['warnings'] ), 'Intentionally absent optional sidecars must not create warnings.' );
assert_true( ! file_exists( $export_dir . '/error_log.json' ), 'An otherwise clean export must not create error_log.json for optional omissions.' );
assert_true( file_exists( $export_dir . '/content/post/sample-post.json' ), 'Post JSON should be written under content/post/.' );
assert_true( file_exists( $export_dir . '/content/post/sample-post-102.json' ), 'Duplicate slugs should use a stable source-ID suffix.' );
assert_true( file_exists( $export_dir . '/content/page/about-us.json' ), 'Page JSON should be written under content/page/.' );
assert_true( file_exists( $export_dir . '/content/gd_place/sample-cafe.json' ), 'CPT JSON should be written under content/gd_place/.' );
assert_true( file_exists( $export_dir . '/bundle.json' ), 'The versioned bundle manifest should be written.' );
assert_true( ! empty( $result['bundle_id'] ), 'A deterministic bundle identity should be returned.' );

$place_data = json_decode( file_get_contents( $export_dir . '/content/gd_place/sample-cafe.json' ), true );
assert_true( is_array( $place_data ), 'Exported content file should contain valid JSON.' );
assert_true( (int) $place_data['id'] === 303, 'Exported content JSON should preserve the content payload.' );

function remove_tree( $path ) {
	if ( ! file_exists( $path ) ) {
		return;
	}
	if ( is_file( $path ) ) {
		unlink( $path );
		return;
	}
	foreach ( scandir( $path ) as $item ) {
		if ( '.' === $item || '..' === $item ) {
			continue;
		}
		remove_tree( $path . DIRECTORY_SEPARATOR . $item );
	}
	rmdir( $path );
}

remove_tree( $export_dir );

fwrite( STDOUT, "content_export_regression: ok\n" );
