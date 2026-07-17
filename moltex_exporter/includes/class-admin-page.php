<?php
/**
 * Admin Page Class
 *
 * Handles the admin interface and AJAX requests.
 *
 * @package Moltex_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Admin Page Class
 */
class Moltex_Exporter_Admin_Page {

	/**
	 * Initialize the admin page.
	 */
	public function init() {
		// Register AJAX handlers (always needed)
		add_action( 'wp_ajax_moltex_start_scan', array( $this, 'handle_ajax_start_scan' ) );
		add_action( 'wp_ajax_moltex_get_progress', array( $this, 'handle_ajax_get_progress' ) );
		add_action( 'wp_ajax_moltex_download', array( $this, 'handle_ajax_download' ) );
		add_action( 'wp_ajax_moltex_save_settings', array( $this, 'handle_ajax_save_settings' ) );
		
		// Only register admin UI hooks when in admin context
		if ( is_admin() && ! wp_doing_ajax() ) {
			// Add admin menu
			add_action( 'admin_menu', array( $this, 'add_admin_menu' ) );
			add_action( 'admin_menu', array( $this, 'remove_legacy_admin_menu' ), PHP_INT_MAX );
			
			// Enqueue admin assets
			add_action( 'admin_enqueue_scripts', array( $this, 'enqueue_assets' ) );
		}
	}

	/**
	 * Add admin menu item.
	 */
	public function add_admin_menu() {
		add_menu_page(
			'Moltex Exporter',
			'Moltex Exporter',
			'manage_options',
			'moltex-exporter',
			array( $this, 'render_page' ),
			'dashicons-migrate',
			80
		);

		add_submenu_page(
			'moltex-exporter',
			'Export blueprints',
			'Export blueprints',
			'manage_options',
			'moltex-exporter',
			array( $this, 'render_page' )
		);
	}

	/**
	 * Remove the obsolete exporter menu left by the pre-Moltex integration.
	 *
	 * The compatibility cleanup is deliberately limited to the known legacy
	 * page slug so no unrelated WordPress admin menu can be affected.
	 */
	public function remove_legacy_admin_menu() {
		remove_menu_page( 'djamingo-exporter' );
	}

	/**
	 * Enqueue admin CSS and JavaScript.
	 *
	 * @param string $hook The current admin page hook.
	 */
	public function enqueue_assets( $hook ) {
		// Don't run during AJAX requests
		if ( wp_doing_ajax() ) {
			return;
		}
		
		// Only load on our plugin page
		if ( 'toplevel_page_moltex-exporter' !== $hook ) {
			return;
		}

		wp_enqueue_style(
			'moltex-exporter-admin',
			MOLTEX_EXPORTER_URL . 'assets/css/admin.css',
			array(),
			MOLTEX_EXPORTER_VERSION
		);

		wp_enqueue_script(
			'moltex-exporter-admin',
			MOLTEX_EXPORTER_URL . 'assets/js/admin.js',
			array( 'jquery' ),
			MOLTEX_EXPORTER_VERSION,
			true
		);

		// Localize script with AJAX URL and nonce
		wp_localize_script(
			'moltex-exporter-admin',
			'moltexExporter',
			array(
				'ajaxUrl' => admin_url( 'admin-ajax.php' ),
				'nonce'   => wp_create_nonce( 'moltex_exporter_nonce' ),
			)
		);
	}

	/**
	 * Render the admin page.
	 */
	public function render_page() {
		// Check user capabilities
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( 'You do not have sufficient permissions to access this page.' );
		}

		$settings = get_option( 'moltex_settings', array() );
		$preflight = ( new Moltex_Exporter_Preflight() )->evaluate( $settings );

		// Load template
		require_once MOLTEX_EXPORTER_PATH . 'templates/admin-page.php';
	}

	/**
	 * Sanitize settings input.
	 *
	 * @param array $input Settings input.
	 * @return array Sanitized settings.
	 */
	public function sanitize_settings( $input ) {
		$sanitized = array();

		$sanitized['export_mode'] = isset( $input['export_mode'] ) && 'discovery' === $input['export_mode']
			? 'discovery'
			: 'complete';
		$sanitized['include_private_content'] = ! empty( $input['include_private_content'] );
		$sanitized['complete_export_max_items'] = isset( $input['complete_export_max_items'] )
			? max( 1, absint( $input['complete_export_max_items'] ) )
			: 5000;

		if ( isset( $input['max_posts'] ) ) {
			$sanitized['max_posts'] = absint( $input['max_posts'] );
		}

		if ( isset( $input['max_pages'] ) ) {
			$sanitized['max_pages'] = absint( $input['max_pages'] );
		}

		if ( isset( $input['max_per_custom_post_type'] ) ) {
			$sanitized['max_per_custom_post_type'] = absint( $input['max_per_custom_post_type'] );
		}

		if ( isset( $input['include_html_snapshots'] ) ) {
			$sanitized['include_html_snapshots'] = (bool) $input['include_html_snapshots'];
		} else {
			// If checkbox is not checked, it won't be in the input array
			$sanitized['include_html_snapshots'] = true;
		}

		if ( isset( $input['batch_size'] ) ) {
			$sanitized['batch_size'] = absint( $input['batch_size'] );
		}

		if ( isset( $input['cleanup_after_hours'] ) ) {
			$sanitized['cleanup_after_hours'] = absint( $input['cleanup_after_hours'] );
		}

		return $sanitized;
	}

	/**
	 * Handle AJAX request to save settings.
	 */
	public function handle_ajax_save_settings() {
		// Load security filters
		require_once MOLTEX_EXPORTER_PATH . 'includes/class-security-filters.php';

		// Verify nonce
		$nonce = isset( $_POST['nonce'] ) ? sanitize_text_field( $_POST['nonce'] ) : '';
		if ( ! Moltex_Exporter_Security_Filters::verify_nonce( $nonce ) ) {
			wp_send_json_error( array( 'message' => 'Security check failed.' ) );
		}

		// Check user capabilities
		if ( ! Moltex_Exporter_Security_Filters::verify_capability( 'manage_options' ) ) {
			wp_send_json_error( array( 'message' => 'Insufficient permissions.' ) );
		}

		// Read settings from POST
		$input = array();
		if ( isset( $_POST['export_mode'] ) ) {
			$input['export_mode'] = sanitize_key( $_POST['export_mode'] );
		}
		if ( isset( $_POST['include_private_content'] ) ) {
			$input['include_private_content'] = $_POST['include_private_content'];
		}
		if ( isset( $_POST['complete_export_max_items'] ) ) {
			$input['complete_export_max_items'] = $_POST['complete_export_max_items'];
		}
		if ( isset( $_POST['max_posts'] ) ) {
			$input['max_posts'] = $_POST['max_posts'];
		}
		if ( isset( $_POST['max_pages'] ) ) {
			$input['max_pages'] = $_POST['max_pages'];
		}
		if ( isset( $_POST['max_per_custom_post_type'] ) ) {
			$input['max_per_custom_post_type'] = $_POST['max_per_custom_post_type'];
		}
		if ( isset( $_POST['include_html_snapshots'] ) ) {
			$input['include_html_snapshots'] = $_POST['include_html_snapshots'];
		}
		if ( isset( $_POST['batch_size'] ) ) {
			$input['batch_size'] = $_POST['batch_size'];
		}
		if ( isset( $_POST['cleanup_after_hours'] ) ) {
			$input['cleanup_after_hours'] = $_POST['cleanup_after_hours'];
		}

		// Sanitize using existing method
		$sanitized = $this->sanitize_settings( $input );

		// Save to option
		update_option( 'moltex_settings', $sanitized );

		wp_send_json_success( array( 'message' => 'Settings saved.' ) );
	}

	/**
	 * Prepare the current request for a long-running export.
	 */
	private function prepare_long_running_request() {
		if ( function_exists( 'ignore_user_abort' ) ) {
			ignore_user_abort( true );
		}

		if ( function_exists( 'wp_raise_memory_limit' ) ) {
			wp_raise_memory_limit( 'admin' );
		}

		if ( function_exists( 'set_time_limit' ) ) {
			@set_time_limit( 0 );
		}
	}

	/**
	 * Provide the admin screen context expected by older WordPress content filters.
	 *
	 * WordPress 5.9 can dereference get_current_screen() while applying block-related
	 * filters during admin AJAX. Normal admin pages set this context automatically;
	 * admin-ajax.php does not.
	 */
	private function prepare_ajax_admin_screen() {
		if ( function_exists( 'get_current_screen' ) && function_exists( 'set_current_screen' ) && null === get_current_screen() ) {
			set_current_screen( 'toplevel_page_moltex-exporter' );
		}
	}

	/**
	 * Handle AJAX request to start scan.
	 */
	public function handle_ajax_start_scan() {
		// Suppress ALL output - critical for clean JSON response
		@ini_set( 'display_errors', '0' );
		@ini_set( 'log_errors', '1' );
		error_reporting( 0 );
		
		// Clear any existing output buffers that may contain warnings
		while ( ob_get_level() > 0 ) {
			ob_end_clean();
		}
		
		// Start fresh output buffer to catch any stray output
		ob_start();
		
		// Enable error logging (not display) for debugging
		if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
			error_log( 'Moltex Exporter: Starting AJAX scan request' );
		}

		$this->prepare_ajax_admin_screen();
		$this->prepare_long_running_request();

		try {
			// Load security filters
			require_once MOLTEX_EXPORTER_PATH . 'includes/class-security-filters.php';

			// Verify nonce
			$nonce = isset( $_POST['nonce'] ) ? sanitize_text_field( $_POST['nonce'] ) : '';
			if ( ! Moltex_Exporter_Security_Filters::verify_nonce( $nonce ) ) {
				ob_end_clean();
				wp_send_json_error( array( 'message' => 'Security check failed.' ) );
			}

			// Check user capabilities
			if ( ! Moltex_Exporter_Security_Filters::verify_capability( 'manage_options' ) ) {
				ob_end_clean();
				wp_send_json_error( array( 'message' => 'Insufficient permissions.' ) );
			}

			$preflight = ( new Moltex_Exporter_Preflight() )->evaluate();
			if ( ! $preflight['ready'] ) {
				ob_end_clean();
				wp_send_json_error(
					array(
						'message'  => 'Export preflight failed: ' . implode( ' ', $preflight['blockers'] ),
						'blockers' => $preflight['blockers'],
					)
				);
			}

			// Load scanner class
			require_once MOLTEX_EXPORTER_PATH . 'includes/class-scanner.php';

			// Initialize scanner orchestrator
			if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
				error_log( 'Moltex Exporter: Initializing scanner' );
			}
			$scanner = new Moltex_Exporter_Scanner();

			// Run the scan process
			if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
				error_log( 'Moltex Exporter: Running scan' );
			}
			$result = $scanner->run_scan();
			
			// Clear any unwanted output
			ob_end_clean();
			
		} catch ( Exception $e ) {
			if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
				error_log( 'Moltex Exporter: Exception caught: ' . $e->getMessage() );
				error_log( 'Moltex Exporter: Stack trace: ' . $e->getTraceAsString() );
			}
			ob_end_clean();
			wp_send_json_error( array( 
				'message' => sprintf( 
					'Fatal error: %s', 
					$e->getMessage() 
				) 
			) );
			return;
		} catch ( Error $e ) {
			if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
				error_log( 'Moltex Exporter: PHP Error caught: ' . $e->getMessage() );
				error_log( 'Moltex Exporter: Stack trace: ' . $e->getTraceAsString() );
			}
			ob_end_clean();
			wp_send_json_error( array( 
				'message' => sprintf( 
					'PHP Error: %s', 
					$e->getMessage() 
				) 
			) );
			return;
		}

		// Discard any captured output (warnings, notices, etc.)
		if ( ob_get_level() > 0 ) {
			ob_end_clean();
		}
		
		if ( $result['success'] && ! empty( $result['results']['download_url'] ) ) {
			// Get download URL from results
			$download_url = isset( $result['results']['download_url'] ) ? $result['results']['download_url'] : '';
			$zip_filename = isset( $result['results']['zip_filename'] ) ? $result['results']['zip_filename'] : '';
			$zip_size = isset( $result['results']['zip_size'] ) ? $result['results']['zip_size'] : 0;

			// Format success message
			$message = 'Scan completed successfully!';
			
			// Add warnings count if any
			$warnings_count = isset( $result['warnings'] ) ? count( $result['warnings'] ) : 0;
			$errors_count = isset( $result['errors'] ) ? count( $result['errors'] ) : 0;
			
			if ( $warnings_count > 0 || $errors_count > 0 ) {
				$message .= ' ' . sprintf(
					'(%d warning(s), %d non-critical error(s) - see error_log.json in the export)',
					$warnings_count,
					$errors_count
				);
			}

			wp_send_json_success( array( 
				'message' => $message,
				'completed' => true,
				'download_url' => $download_url,
				'zip_filename' => $zip_filename,
				'zip_size' => $zip_size,
				'errors' => $result['errors'],
				'warnings' => $result['warnings'],
				'has_issues' => ( $warnings_count > 0 || $errors_count > 0 ),
			) );
		} else {
			// Format error message with helpful context
			$error_message = isset( $result['error'] ) ? $result['error'] : 'The export did not produce a validated download.';
			
			// Add troubleshooting tips
			$error_message .= ' ' . 'Please check the WordPress debug log for more details.';

			wp_send_json_error( array( 
				'message' => $error_message,
				'errors' => isset( $result['errors'] ) ? $result['errors'] : array(),
			) );
		}
	}

	/**
	 * Handle AJAX request to get progress.
	 */
	public function handle_ajax_get_progress() {
		// Load security filters
		require_once MOLTEX_EXPORTER_PATH . 'includes/class-security-filters.php';

		// Verify nonce
		$nonce = isset( $_POST['nonce'] ) ? sanitize_text_field( $_POST['nonce'] ) : '';
		if ( ! Moltex_Exporter_Security_Filters::verify_nonce( $nonce ) ) {
			wp_send_json_error( array( 'message' => 'Security check failed.' ) );
		}

		// Check user capabilities
		if ( ! Moltex_Exporter_Security_Filters::verify_capability( 'manage_options' ) ) {
			wp_send_json_error( array( 'message' => 'Insufficient permissions.' ) );
		}

		// Get current progress from transient
		$progress = get_transient( 'moltex_scan_progress' );

		if ( ! $progress ) {
			wp_send_json_error( array( 'message' => 'No scan in progress.' ) );
		}

		wp_send_json_success( $progress );
	}

	/**
	 * Handle AJAX request to download artifacts.
	 */
	public function handle_ajax_download() {
		// Load security filters
		require_once MOLTEX_EXPORTER_PATH . 'includes/class-security-filters.php';

		// Get verification data from request.
		$request = array(
			'token'     => isset( $_GET['token'] ) ? sanitize_text_field( $_GET['token'] ) : '',
			'nonce'     => isset( $_GET['nonce'] ) ? sanitize_text_field( $_GET['nonce'] ) : '',
			'file'      => isset( $_GET['file'] ) ? sanitize_text_field( wp_unslash( $_GET['file'] ) ) : '',
			'expires'   => isset( $_GET['expires'] ) ? absint( $_GET['expires'] ) : 0,
			'signature' => isset( $_GET['signature'] ) ? sanitize_text_field( $_GET['signature'] ) : '',
		);

		// Check user capabilities
		if ( ! Moltex_Exporter_Security_Filters::verify_capability( 'manage_options' ) ) {
			wp_die( 'Insufficient permissions.', 'Access Denied', array( 'response' => 403 ) );
		}

		if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
			error_log( 'Moltex Exporter: Handling download request' );
		}

		// Validate request
		if ( empty( $request['token'] ) && empty( $request['file'] ) ) {
			wp_die( 'Invalid download request.', 'Invalid Request', array( 'response' => 400 ) );
		}

		// Load packager class
		require_once MOLTEX_EXPORTER_PATH . 'includes/class-packager.php';
		$packager = new Moltex_Exporter_Packager();

		// Verify download request
		$download_data = $packager->verify_download_request( $request );

		if ( ! $download_data ) {
			wp_die( 'Invalid or expired download link.', 'Invalid Link', array( 'response' => 404 ) );
		}

		// Serve the file
		$packager->serve_download( $download_data['zip_path'], $download_data['zip_filename'] );
	}
}
