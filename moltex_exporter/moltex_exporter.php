<?php
/**
 * Plugin Name: Moltex Exporter
 * Description: Create a privacy-filtered WordPress evidence bundle for verified migration into a Git-managed Astro repository.
 * Version: 1.0.0
 * Author: Moltex Contributors
 * License: GPL v2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Requires at least: 5.9
 * Requires PHP: 7.4
 * Tested up to: 7.0
 * Network: false
 * 
 * @package Moltex_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Currently plugin version.
 */
define( 'MOLTEX_EXPORTER_VERSION', '1.0.0' );

/**
 * Plugin directory path.
 */
define( 'MOLTEX_EXPORTER_PATH', plugin_dir_path( __FILE__ ) );

/**
 * Plugin directory URL.
 */
define( 'MOLTEX_EXPORTER_URL', plugin_dir_url( __FILE__ ) );

/**
 * The code that runs during plugin activation.
 */
function activate_moltex_exporter() {
	require_once MOLTEX_EXPORTER_PATH . 'includes/trait-error-logger.php';
	require_once MOLTEX_EXPORTER_PATH . 'includes/class-packager.php';
	$packager = new Moltex_Exporter_Packager();
	$packager->cleanup_old_artifacts();
}

/**
 * The code that runs during plugin deactivation.
 */
function deactivate_moltex_exporter() {
	// Clean up transients
	delete_transient( 'moltex_scan_progress' );
	delete_transient( 'moltex_scan_results' );
}

register_activation_hook( __FILE__, 'activate_moltex_exporter' );
register_deactivation_hook( __FILE__, 'deactivate_moltex_exporter' );

/**
 * Initialize the plugin.
 */
function moltex_exporter_init() {
	// Load shared trait and utilities (needed by Scanner_Base, Packager, Exporter, Scanner_Orchestrator)
	require_once MOLTEX_EXPORTER_PATH . 'includes/trait-error-logger.php';
	require_once MOLTEX_EXPORTER_PATH . 'includes/class-callback-resolver.php';
	require_once MOLTEX_EXPORTER_PATH . 'includes/class-source-identifier.php';
	require_once MOLTEX_EXPORTER_PATH . 'includes/class-scanner-base.php';

	// Load security filters class (always available)
	require_once MOLTEX_EXPORTER_PATH . 'includes/class-security-filters.php';

	// Load scanner orchestrator class
	require_once MOLTEX_EXPORTER_PATH . 'includes/class-scanner.php';

	// Load admin page class (needed for AJAX handlers too)
	require_once MOLTEX_EXPORTER_PATH . 'includes/class-admin-page.php';

	// Initialize admin page (registers AJAX handlers and admin UI)
	$admin_page = new Moltex_Exporter_Admin_Page();
	$admin_page->init();
}
add_action( 'init', 'moltex_exporter_init' );
