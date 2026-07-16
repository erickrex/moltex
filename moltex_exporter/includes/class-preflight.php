<?php
/**
 * Classifies live-site prerequisites before an export starts.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'WPINC' ) ) {
	die;
}

class Moltex_Exporter_Preflight {

	public static function get_blocked_plugin_families() {
		return array(
			'woocommerce/' => array( 'ecommerce', 'WooCommerce' ),
			'easy-digital-downloads/' => array( 'ecommerce', 'Easy Digital Downloads' ),
			'memberpress/' => array( 'membership', 'MemberPress' ),
			'paid-memberships-pro/' => array( 'membership', 'Paid Memberships Pro' ),
			'restrict-content-pro/' => array( 'membership', 'Restrict Content Pro' ),
			'buddypress/' => array( 'community', 'BuddyPress' ),
			'bbpress/' => array( 'community', 'bbPress' ),
			'sfwd-lms/' => array( 'learning_management', 'LearnDash' ),
			'lifterlms/' => array( 'learning_management', 'LifterLMS' ),
			'tutor/' => array( 'learning_management', 'Tutor LMS' ),
			'bookly-responsive-appointment-booking-tool/' => array( 'booking', 'Bookly' ),
		);
	}

	/**
	 * Optional environment overrides used by deterministic tests.
	 *
	 * @var array
	 */
	private $environment;

	public function __construct( $environment = array() ) {
		$this->environment = is_array( $environment ) ? $environment : array();
	}

	/**
	 * Evaluate blocking requirements and operational warnings.
	 *
	 * @param array|null $settings Saved exporter settings.
	 * @return array
	 */
	public function evaluate( $settings = null ) {
		$settings = is_array( $settings ) ? $settings : get_option( 'moltex_settings', array() );
		$blockers = array();
		$warnings = array();

		if ( ! $this->value( 'zip_available', class_exists( 'ZipArchive' ) ) ) {
			$blockers[] = 'PHP ZipArchive is required to create and validate the download.';
		}

		$uploads = $this->value( 'uploads', wp_upload_dir() );
		$uploads_ready = is_array( $uploads ) && empty( $uploads['error'] ) && ! empty( $uploads['basedir'] );
		if ( $uploads_ready && ! isset( $this->environment['uploads_writable'] ) ) {
			$target = trailingslashit( $uploads['basedir'] ) . 'ai_migration_artifacts';
			$uploads_ready = ( is_dir( $target ) || wp_mkdir_p( $target ) ) && is_writable( $target );
		} elseif ( isset( $this->environment['uploads_writable'] ) ) {
			$uploads_ready = $uploads_ready && (bool) $this->environment['uploads_writable'];
		}
		if ( ! $uploads_ready ) {
			$blockers[] = 'WordPress uploads storage is unavailable or not writable.';
		}

		$memory_bytes = $this->parse_bytes( $this->value( 'memory_limit', ini_get( 'memory_limit' ) ) );
		if ( $memory_bytes > 0 && $memory_bytes < 268435456 ) {
			$warnings[] = 'PHP memory_limit is below the recommended 256 MB.';
		}
		$time_limit = (int) $this->value( 'max_execution_time', ini_get( 'max_execution_time' ) );
		if ( $time_limit > 0 && $time_limit < 120 ) {
			$warnings[] = 'PHP max_execution_time is below the recommended 120 seconds.';
		}

		$disk_bytes = $this->value( 'disk_free_bytes', $this->disk_free_bytes( $uploads ) );
		if ( false !== $disk_bytes && $disk_bytes < 536870912 ) {
			$warnings[] = 'Uploads storage has less than the recommended 512 MB free.';
		}

		$mode = isset( $settings['export_mode'] ) && 'discovery' === $settings['export_mode'] ? 'discovery' : 'complete';
		if ( 'complete' === $mode && empty( $settings['include_html_snapshots'] ) ) {
			$warnings[] = 'HTML snapshots are disabled for this complete export.';
		}
		$references = get_option( Moltex_Exporter_Reference_Screenshots::OPTION_NAME, array() );
		if ( 'complete' === $mode && empty( $references ) ) {
			$warnings[] = 'No reviewed desktop/mobile reference screenshots are registered.';
		}
		if ( is_multisite() ) {
			$warnings[] = 'WordPress multisite is outside the initial static migration profile.';
		}
		foreach ( (array) get_option( 'active_plugins', array() ) as $plugin_file ) {
			foreach ( self::get_blocked_plugin_families() as $prefix => $definition ) {
				if ( 0 === strpos( $plugin_file, $prefix ) ) {
					$warnings[] = $definition[1] . ' is outside the initial static migration profile.';
				}
			}
		}

		return array(
			'ready'    => empty( $blockers ),
			'blockers' => $blockers,
			'warnings' => $warnings,
		);
	}

	private function value( $key, $default ) {
		return array_key_exists( $key, $this->environment ) ? $this->environment[ $key ] : $default;
	}

	private function disk_free_bytes( $uploads ) {
		if ( ! is_array( $uploads ) || empty( $uploads['basedir'] ) || ! function_exists( 'disk_free_space' ) ) {
			return false;
		}
		return @disk_free_space( $uploads['basedir'] );
	}

	private function parse_bytes( $value ) {
		$value = trim( (string) $value );
		if ( '' === $value || '-1' === $value ) {
			return -1;
		}
		$unit = strtolower( substr( $value, -1 ) );
		$bytes = (int) $value;
		if ( 'g' === $unit ) {
			$bytes *= 1073741824;
		} elseif ( 'm' === $unit ) {
			$bytes *= 1048576;
		} elseif ( 'k' === $unit ) {
			$bytes *= 1024;
		}
		return $bytes;
	}
}
