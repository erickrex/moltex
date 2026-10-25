<?php
/**
 * Export policy settings.
 *
 * Operator choices that widen or narrow what the exporter collects. Every
 * option that would put personal data in the bundle defaults to off.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Moltex_Exporter_Export_Policy {

	const OPTION = 'moltex_settings';

	/** Default upload part size: 24 MiB keeps parts under common 25 MB upload limits. */
	const DEFAULT_PART_MAX_BYTES = 25165824;
	const MIN_PART_MAX_BYTES = 5242880;
	const MAX_PART_MAX_BYTES = 262144000;

	/**
	 * Sanitize the policy subset of the settings form.
	 *
	 * @param array $input Raw input.
	 * @return array
	 */
	public static function sanitize( $input ) {
		$input = is_array( $input ) ? $input : array();
		$part = isset( $input['part_max_bytes'] ) ? absint( $input['part_max_bytes'] ) : self::DEFAULT_PART_MAX_BYTES;
		return array(
			'media_acquisition'             => ( isset( $input['media_acquisition'] ) && 'featured_only' === $input['media_acquisition'] ) ? 'featured_only' : 'bundle_all',
			'part_max_bytes'                => min( self::MAX_PART_MAX_BYTES, max( self::MIN_PART_MAX_BYTES, $part ) ),
			'geodirectory_include_fields'   => self::key_list( isset( $input['geodirectory_include_fields'] ) ? $input['geodirectory_include_fields'] : array() ),
			'include_non_public_post_types' => self::key_list( isset( $input['include_non_public_post_types'] ) ? $input['include_non_public_post_types'] : array() ),
			'include_user_emails'           => ! empty( $input['include_user_emails'] ),
			'include_subscribers'           => ! empty( $input['include_subscribers'] ),
			'production_origin'             => self::origin( isset( $input['production_origin'] ) ? $input['production_origin'] : '' ),
		);
	}

	/**
	 * Normalize an operator-declared production origin to scheme://host[:port] (X1).
	 *
	 * @param mixed $value Raw input.
	 * @return string Empty when unset or invalid.
	 */
	public static function origin( $value ) {
		$value = trim( (string) $value );
		$parts = '' === $value ? false : parse_url( $value );
		if ( ! is_array( $parts ) || empty( $parts['host'] ) || ! in_array( strtolower( isset( $parts['scheme'] ) ? $parts['scheme'] : '' ), array( 'http', 'https' ), true ) || ! preg_match( '/^[a-z0-9.-]+$/i', $parts['host'] ) ) {
			return '';
		}
		return strtolower( $parts['scheme'] ) . '://' . strtolower( $parts['host'] ) . ( isset( $parts['port'] ) ? ':' . (int) $parts['port'] : '' );
	}

	/**
	 * Current effective policy.
	 *
	 * @return array
	 */
	public static function current() {
		$settings = get_option( self::OPTION, array() );
		return self::sanitize( is_array( $settings ) ? $settings : array() );
	}

	public static function get( $key ) {
		$policy = self::current();
		return isset( $policy[ $key ] ) ? $policy[ $key ] : null;
	}

	/**
	 * Normalize a comma/space separated string or array into unique safe keys.
	 *
	 * @param mixed $value Input.
	 * @return string[]
	 */
	public static function key_list( $value ) {
		if ( is_string( $value ) ) {
			$value = preg_split( '/[\s,]+/', $value );
		}
		if ( ! is_array( $value ) ) {
			return array();
		}
		$keys = array();
		foreach ( $value as $item ) {
			$item = strtolower( trim( (string) $item ) );
			if ( preg_match( '/^[a-z0-9_\-]{1,64}$/', $item ) ) {
				$keys[ $item ] = true;
			}
		}
		$keys = array_keys( $keys );
		sort( $keys );
		return $keys;
	}
}
