<?php
/**
 * PHPUnit Bootstrap File
 *
 * Sets up the testing environment and loads WordPress test functions.
 *
 * @package Moltex_Exporter
 */

// Define test constants
define( 'MOLTEX_TESTS_DIR', __DIR__ );
define( 'MOLTEX_PLUGIN_DIR', dirname( __DIR__ ) );

// Load WordPress mock functions
require_once MOLTEX_TESTS_DIR . '/mocks/wordpress-functions.php';

// Load plugin files
require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-site-scanner.php';
require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-theme-scanner.php';
require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-plugin-scanner.php';
require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-content-scanner.php';
require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-migration-readiness-scanner.php';
require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-taxonomy-scanner.php';
require_once MOLTEX_PLUGIN_DIR . '/includes/scanners/class-media-scanner.php';
