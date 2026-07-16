<?php
/**
 * WordPress Function Mocks for Testing
 *
 * Provides mock implementations of WordPress functions for unit testing.
 *
 * @package Moltex_Exporter
 */

// Define WPINC constant
if ( ! defined( 'WPINC' ) ) {
	define( 'WPINC', 'wp-includes' );
}

// Define ABSPATH constant
if ( ! defined( 'ABSPATH' ) ) {
	define( 'ABSPATH', '/var/www/html/' );
}

// Define WP_PLUGIN_DIR constant
if ( ! defined( 'WP_PLUGIN_DIR' ) ) {
	define( 'WP_PLUGIN_DIR', ABSPATH . 'wp-content/plugins' );
}

// Global variables for mocking
global $wp_version, $wpdb, $wp_post_types, $wp_taxonomies, $shortcode_tags;
$wp_version = '6.4.2';

/**
 * Minimal wpdb replacement for scanner unit tests.
 */
class Mock_WPDB {
	public $prefix = 'wp_';
	public $options = 'wp_options';
	public $posts = 'wp_posts';
	public $postmeta = 'wp_postmeta';
	public $terms = 'wp_terms';
	public $term_taxonomy = 'wp_term_taxonomy';
	public $term_relationships = 'wp_term_relationships';
	public $termmeta = 'wp_termmeta';
	public $comments = 'wp_comments';
	public $commentmeta = 'wp_commentmeta';
	public $links = 'wp_links';
	public $usermeta = 'wp_usermeta';
	public $users = 'wp_users';

	public function prepare( $query, ...$args ) {
		return $query;
	}

	public function esc_like( $value ) {
		return addcslashes( $value, '_%\\' );
	}

	public function get_results( $query ) {
		return array();
	}

	public function get_col( $query ) {
		return array();
	}

	public function get_var( $query ) {
		return 0;
	}
}

$wpdb = new Mock_WPDB();

// Mock data storage
global $mock_options, $mock_posts, $mock_postmeta, $mock_terms, $mock_termmeta, $mock_plugins, $mock_themes, $mock_upload_dir, $mock_attached_files;
$mock_options = array();
$mock_posts = array();
$mock_postmeta = array();
$mock_terms = array();
$mock_termmeta = array();
$mock_plugins = array();
$mock_themes = array();
$mock_upload_dir = null;
$mock_attached_files = array();

global $mock_filters;
$mock_filters = array();

/**
 * Mock wp_parse_args().
 */
function wp_parse_args( $args, $defaults = array() ) {
	if ( is_object( $args ) ) {
		$args = get_object_vars( $args );
	} elseif ( is_string( $args ) ) {
		parse_str( $args, $args );
	}

	return array_merge( $defaults, is_array( $args ) ? $args : array() );
}

/**
 * Register a mock filter or action callback.
 */
function add_filter( $hook_name, $callback, $priority = 10, $accepted_args = 1 ) {
	global $mock_filters;
	$mock_filters[ $hook_name ][ $priority ][] = array( $callback, $accepted_args );
	return true;
}

/**
 * Register a mock action callback.
 */
function add_action( $hook_name, $callback, $priority = 10, $accepted_args = 1 ) {
	return add_filter( $hook_name, $callback, $priority, $accepted_args );
}

/**
 * Apply registered mock filters.
 */
function apply_filters( $hook_name, $value, ...$args ) {
	global $mock_filters;
	if ( empty( $mock_filters[ $hook_name ] ) ) {
		return $value;
	}

	ksort( $mock_filters[ $hook_name ] );
	foreach ( $mock_filters[ $hook_name ] as $callbacks ) {
		foreach ( $callbacks as $registered ) {
			$callback_args = array_slice( array_merge( array( $value ), $args ), 0, $registered[1] );
			$value = call_user_func_array( $registered[0], $callback_args );
		}
	}

	return $value;
}

/**
 * Run registered mock actions.
 */
function do_action( $hook_name, ...$args ) {
	global $mock_filters;
	if ( empty( $mock_filters[ $hook_name ] ) ) {
		return;
	}

	ksort( $mock_filters[ $hook_name ] );
	foreach ( $mock_filters[ $hook_name ] as $callbacks ) {
		foreach ( $callbacks as $registered ) {
			call_user_func_array( $registered[0], array_slice( $args, 0, $registered[1] ) );
		}
	}
}

/**
 * Mock absint().
 */
function absint( $value ) {
	return abs( (int) $value );
}

/**
 * Mock get_site_url()
 */
function get_site_url() {
	return 'https://example.com';
}

/**
 * Mock get_home_url()
 */
function get_home_url() {
	return 'https://example.com';
}

/**
 * Mock home_url().
 */
function home_url( $path = '' ) {
	return rtrim( get_home_url(), '/' ) . '/' . ltrim( $path, '/' );
}

/**
 * Mock get_bloginfo()
 */
function get_bloginfo( $show = '' ) {
	$info = array(
		'name' => 'Test Site',
		'description' => 'Just another WordPress site',
		'language' => 'en-US',
		'charset' => 'UTF-8',
	);
	
	return isset( $info[ $show ] ) ? $info[ $show ] : '';
}

/**
 * Mock is_multisite()
 */
function is_multisite() {
	return false;
}

/**
 * Mock get_option()
 */
function get_option( $option, $default = false ) {
	global $mock_options;
	return isset( $mock_options[ $option ] ) ? $mock_options[ $option ] : $default;
}

/**
 * Mock update_option().
 */
function update_option( $option, $value, $autoload = null ) {
	global $mock_options;
	$mock_options[ $option ] = $value;
	return true;
}

/**
 * Mock wp_unslash().
 */
function wp_unslash( $value ) {
	return $value;
}

/**
 * Mock WordPress security primitives.
 */
function wp_verify_nonce( $nonce, $action = -1 ) {
	global $mock_nonce_valid;
	return ! isset( $mock_nonce_valid ) || (bool) $mock_nonce_valid;
}

function current_user_can( $capability ) {
	global $mock_user_can;
	return ! isset( $mock_user_can ) || (bool) $mock_user_can;
}

/**
 * Mock the WordPress admin screen context used by legacy content filters.
 */
function get_current_screen() {
	global $mock_current_screen;
	return isset( $mock_current_screen ) ? $mock_current_screen : null;
}

function set_current_screen( $screen = '' ) {
	global $mock_current_screen;
	$mock_current_screen = (object) array( 'id' => $screen );
	return $mock_current_screen;
}

/**
 * Mock get_post_types()
 */
function get_post_types( $args = array(), $output = 'names' ) {
	global $wp_post_types;
	
	if ( empty( $wp_post_types ) ) {
		$wp_post_types = array(
			'post' => (object) array(
				'name' => 'post',
				'label' => 'Posts',
				'labels' => (object) array( 'name' => 'Posts' ),
				'description' => 'Posts',
				'public' => true,
				'hierarchical' => false,
				'has_archive' => true,
				'rewrite' => array( 'slug' => 'blog' ),
				'menu_icon' => 'dashicons-admin-post',
				'show_in_rest' => true,
				'rest_base' => 'posts',
			),
			'page' => (object) array(
				'name' => 'page',
				'label' => 'Pages',
				'labels' => (object) array( 'name' => 'Pages' ),
				'description' => 'Pages',
				'public' => true,
				'hierarchical' => true,
				'has_archive' => false,
				'rewrite' => array( 'slug' => 'page' ),
				'menu_icon' => 'dashicons-admin-page',
				'show_in_rest' => true,
				'rest_base' => 'pages',
			),
		);
	}
	
	if ( $output === 'objects' ) {
		return $wp_post_types;
	}
	
	return array_keys( $wp_post_types );
}

/**
 * Mock get_all_post_type_supports()
 */
function get_all_post_type_supports( $post_type ) {
	return array( 'title', 'editor', 'thumbnail', 'excerpt' );
}

/**
 * Mock get_object_taxonomies()
 */
function get_object_taxonomies( $object, $output = 'names' ) {
	if ( $object === 'post' ) {
		return array( 'category', 'post_tag' );
	}
	return array();
}

/**
 * Mock get_taxonomies()
 */
function get_taxonomies( $args = array(), $output = 'names' ) {
	global $wp_taxonomies;
	
	if ( empty( $wp_taxonomies ) ) {
		$wp_taxonomies = array(
			'category' => (object) array(
				'name' => 'category',
				'label' => 'Categories',
				'labels' => (object) array( 'name' => 'Categories' ),
				'description' => 'Categories',
				'public' => true,
				'hierarchical' => true,
				'rewrite' => array( 'slug' => 'category' ),
				'object_type' => array( 'post' ),
				'show_in_rest' => true,
				'rest_base' => 'categories',
			),
			'post_tag' => (object) array(
				'name' => 'post_tag',
				'label' => 'Tags',
				'labels' => (object) array( 'name' => 'Tags' ),
				'description' => 'Tags',
				'public' => true,
				'hierarchical' => false,
				'rewrite' => array( 'slug' => 'tag' ),
				'object_type' => array( 'post' ),
				'show_in_rest' => true,
				'rest_base' => 'tags',
			),
		);
	}
	
	if ( $output === 'objects' ) {
		return $wp_taxonomies;
	}
	
	return array_keys( $wp_taxonomies );
}

/**
 * Mock wp_count_posts()
 */
function wp_count_posts( $post_type = 'post' ) {
	return (object) array(
		'publish' => 10,
		'private' => 2,
		'draft' => 3,
	);
}

/**
 * Minimal callable WP_Theme replacement.
 */
class Mock_WP_Theme {
	private $data;
	private $directory;
	private $parent_theme;

	public function __construct( array $data = array(), $directory = '', $parent_theme = false ) {
		$this->data = array_merge(
			array(
				'Name'       => 'Twenty Twenty-Four',
				'Version'    => '1.0',
				'Description'=> 'A test theme',
				'Author'     => 'WordPress',
				'AuthorURI'  => 'https://wordpress.org',
				'ThemeURI'   => 'https://wordpress.org/themes/twentytwentyfour',
				'Template'   => 'twentytwentyfour',
				'Stylesheet' => 'twentytwentyfour',
				'TextDomain' => 'twentytwentyfour',
			),
			$data
		);
		$this->directory = $directory ?: sys_get_temp_dir() . '/moltex-test-theme';
		$this->parent_theme = $parent_theme;
	}

	public function get( $key ) {
		return isset( $this->data[ $key ] ) ? $this->data[ $key ] : '';
	}

	public function get_template() {
		return $this->data['Template'];
	}

	public function get_stylesheet() {
		return $this->data['Stylesheet'];
	}

	public function get_stylesheet_directory() {
		return $this->directory;
	}

	public function parent() {
		return $this->parent_theme;
	}

	public function get_page_templates() {
		return array();
	}
}

/**
 * Mock wp_get_theme().
 */
function wp_get_theme() {
	global $mock_themes;
	return empty( $mock_themes ) ? new Mock_WP_Theme() : $mock_themes[0];
}

/**
 * Mock wp_upload_dir()
 */
function wp_upload_dir() {
	global $mock_upload_dir;
	if ( is_array( $mock_upload_dir ) ) {
		return $mock_upload_dir;
	}
	return array(
		'path' => '/var/www/html/wp-content/uploads/2024/01',
		'url' => 'https://example.com/wp-content/uploads/2024/01',
		'subdir' => '/2024/01',
		'basedir' => '/var/www/html/wp-content/uploads',
		'baseurl' => 'https://example.com/wp-content/uploads',
		'error' => false,
	);
}

/**
 * Mock get_attached_file().
 */
function get_attached_file( $attachment_id ) {
	global $mock_attached_files;
	return isset( $mock_attached_files[ $attachment_id ] ) ? $mock_attached_files[ $attachment_id ] : false;
}

/**
 * Mock trailingslashit()
 */
function trailingslashit( $string ) {
	return rtrim( $string, '/\\' ) . '/';
}

/**
 * Mock wp_mkdir_p()
 */
function wp_mkdir_p( $target ) {
	if ( is_dir( $target ) ) {
		return true;
	}

	return mkdir( $target, 0755, true );
}

/**
 * Mock get_plugins()
 */
function get_plugins() {
	return array(
		'akismet/akismet.php' => array(
			'Name' => 'Akismet Anti-Spam',
			'Version' => '5.0',
			'Description' => 'Anti-spam plugin',
			'Author' => 'Automattic',
			'AuthorURI' => 'https://automattic.com',
			'PluginURI' => 'https://akismet.com',
			'TextDomain' => 'akismet',
			'Network' => false,
		),
	);
}

/**
 * Mock current_time()
 */
function current_time( $type, $gmt = 0 ) {
	if ( $type === 'mysql' ) {
		return date( 'Y-m-d H:i:s' );
	}
	return time();
}

/**
 * Mock wp_json_encode()
 */
function wp_json_encode( $data, $options = 0 ) {
	return json_encode( $data, $options );
}

/**
 * Mock parse_blocks()
 */
function parse_blocks( $content ) {
	// Simple mock - return empty array for non-block content
	if ( strpos( $content, '<!-- wp:' ) === false ) {
		return array();
	}
	
	// Return a simple block structure
	return array(
		array(
			'blockName' => 'core/paragraph',
			'attrs' => array(),
			'innerHTML' => '<p>Test content</p>',
			'innerBlocks' => array(),
		),
	);
}

/**
 * Mock get_post()
 */
function get_post( $post_id = null ) {
	global $mock_posts;
	if ( null === $post_id ) {
		global $post;
		return isset( $post ) ? $post : null;
	}
	
	if ( isset( $mock_posts[ $post_id ] ) ) {
		return $mock_posts[ $post_id ];
	}
	
	return null;
}

/**
 * Mock get_post_meta()
 */
function get_post_meta( $post_id, $key = '', $single = false ) {
	global $mock_postmeta;
	
	if ( ! isset( $mock_postmeta[ $post_id ] ) ) {
		return $single ? '' : array();
	}
	
	if ( $key ) {
		if ( isset( $mock_postmeta[ $post_id ][ $key ] ) ) {
			return $single ? $mock_postmeta[ $post_id ][ $key ] : array( $mock_postmeta[ $post_id ][ $key ] );
		}
		return $single ? '' : array();
	}
	
	// Return all meta
	$all_meta = array();
	foreach ( $mock_postmeta[ $post_id ] as $meta_key => $meta_value ) {
		$all_meta[ $meta_key ] = array( $meta_value );
	}
	return $all_meta;
}

/**
 * Mock get_terms()
 */
function get_terms( $args = array() ) {
	global $mock_terms;
	
	if ( empty( $mock_terms ) ) {
		return array();
	}
	
	return $mock_terms;
}

/**
 * Mock wp_get_post_terms()
 */
function wp_get_post_terms( $post_id, $taxonomy, $args = array() ) {
	return array( 1, 2 );
}

/**
 * Mock get_term_meta()
 */
function get_term_meta( $term_id, $key = '', $single = false ) {
	global $mock_termmeta;
	if ( ! isset( $mock_termmeta[ $term_id ] ) ) {
		return $single ? '' : array();
	}

	if ( '' !== $key ) {
		if ( ! array_key_exists( $key, $mock_termmeta[ $term_id ] ) ) {
			return $single ? '' : array();
		}
		$value = $mock_termmeta[ $term_id ][ $key ];
		return $single ? $value : array( $value );
	}

	$all_meta = array();
	foreach ( $mock_termmeta[ $term_id ] as $meta_key => $meta_value ) {
		$all_meta[ $meta_key ] = array( $meta_value );
	}
	return $all_meta;
}

/**
 * Mock taxonomy_exists()
 */
function taxonomy_exists( $taxonomy ) {
	global $wp_taxonomies;
	get_taxonomies( array(), 'objects' );
	return isset( $wp_taxonomies[ $taxonomy ] );
}

/**
 * Mock get_taxonomy()
 */
function get_taxonomy( $taxonomy ) {
	global $wp_taxonomies;
	get_taxonomies( array(), 'objects' );
	return isset( $wp_taxonomies[ $taxonomy ] ) ? $wp_taxonomies[ $taxonomy ] : false;
}

/**
 * Mock wp_get_attachment_url()
 */
function wp_get_attachment_url( $attachment_id ) {
	return 'https://example.com/wp-content/uploads/2024/01/image-' . $attachment_id . '.jpg';
}

/**
 * Mock attachment_url_to_postid()
 */
function attachment_url_to_postid( $url ) {
	// Extract ID from mock URL pattern
	if ( preg_match( '/image-(\d+)\.jpg/', $url, $matches ) ) {
		return (int) $matches[1];
	}
	return 0;
}

/**
 * Mock get_post_mime_type()
 */
function get_post_mime_type( $post_id ) {
	return 'image/jpeg';
}

/**
 * Mock wp_get_attachment_metadata()
 */
function wp_get_attachment_metadata( $attachment_id ) {
	return array(
		'width' => 1920,
		'height' => 1080,
		'file' => '2024/01/image-' . $attachment_id . '.jpg',
		'sizes' => array(
			'thumbnail' => array(
				'file' => 'image-' . $attachment_id . '-150x150.jpg',
				'width' => 150,
				'height' => 150,
			),
		),
		'image_meta' => array(
			'aperture' => '2.8',
			'camera' => 'Test Camera',
		),
	);
}

/**
 * Mock maybe_unserialize()
 */
function maybe_unserialize( $data ) {
	if ( is_serialized( $data ) ) {
		return @unserialize( $data );
	}
	return $data;
}

/**
 * Mock is_serialized()
 */
function is_serialized( $data ) {
	if ( ! is_string( $data ) ) {
		return false;
	}
	$data = trim( $data );
	if ( 'N;' === $data ) {
		return true;
	}
	if ( ! preg_match( '/^([adObis]):/', $data, $badions ) ) {
		return false;
	}
	return true;
}

/**
 * Mock is_wp_error()
 */
function is_wp_error( $thing ) {
	return ( $thing instanceof WP_Error );
}

/**
 * Mock WP_Error class
 */
class WP_Error {
	public $errors = array();
	
	public function __construct( $code = '', $message = '', $data = '' ) {
		if ( $code ) {
			$this->errors[ $code ] = array( $message );
		}
	}
	
	public function get_error_message() {
		return isset( $this->errors ) ? current( current( $this->errors ) ) : '';
	}
}

/**
 * Mock WP_Query class
 */
class WP_Query {
	public $posts = array();
	public $post_count = 0;
	public $current_post = -1;
	
	public function __construct( $args = array() ) {
		global $mock_posts;
		
		// Simple mock - return mock posts
		$this->posts = array_values( $mock_posts );
		$this->post_count = count( $this->posts );
	}
	
	public function have_posts() {
		return $this->current_post + 1 < $this->post_count;
	}
	
	public function the_post() {
		$this->current_post++;
		if ( isset( $this->posts[ $this->current_post ] ) ) {
			global $post;
			$post = $this->posts[ $this->current_post ];
		}
	}
}

/**
 * Mock wp_reset_postdata()
 */
function wp_reset_postdata() {
	global $post;
	$post = null;
}

/**
 * Mock get_permalink()
 */
function get_permalink( $post_id = 0 ) {
	return 'https://example.com/sample-post/';
}

/**
 * Mock get_userdata()
 */
function get_userdata( $user_id ) {
	$user = new stdClass();
	$user->display_name = 'Test User';
	return $user;
}

/**
 * Mock get_page_template_slug()
 */
function get_page_template_slug( $post_id ) {
	return '';
}

/**
 * Mock get_post_thumbnail_id()
 */
function get_post_thumbnail_id( $post_id ) {
	return 0;
}

/**
 * Mock sanitize_file_name()
 */
function sanitize_file_name( $filename ) {
	return preg_replace( '/[^a-z0-9\-_\.]/', '-', strtolower( $filename ) );
}

/**
 * Mock get_theme_mods().
 */
function get_theme_mods() {
	return array();
}

/**
 * Mock get_posts().
 */
function get_posts( $args = array() ) {
	global $mock_posts, $test_get_posts_calls;
	if ( isset( $test_get_posts_calls ) && is_array( $test_get_posts_calls ) ) {
		$test_get_posts_calls[] = $args;
	}

	$posts = array_values( $mock_posts );
	if ( isset( $args['post_type'] ) ) {
		$post_types = (array) $args['post_type'];
		$posts = array_values(
			array_filter(
				$posts,
				function( $post ) use ( $post_types ) {
					return isset( $post->post_type ) && in_array( $post->post_type, $post_types, true );
				}
			)
		);
	}

	return $posts;
}

/**
 * Mock plugin activation check.
 */
function is_plugin_active( $plugin ) {
	return false;
}

/**
 * Mock theme support lookup.
 */
function get_theme_support( $feature ) {
	return false;
}

/**
 * Prevent unit tests from making network requests.
 */
function wp_remote_get( $url, $args = array() ) {
	return new WP_Error( 'network_disabled', 'Network disabled in unit tests' );
}

/**
 * Mock response body accessor.
 */
function wp_remote_retrieve_body( $response ) {
	return is_array( $response ) && isset( $response['body'] ) ? $response['body'] : '';
}

/**
 * Mock error_log() - suppress in tests
 */
if ( ! function_exists( 'error_log' ) ) {
	function error_log( $message ) {
		// Suppress in tests
		return true;
	}
}
