<?php
/**
 * Canonical, filesystem-safe source-site identity.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Builds and validates the identity shared by the bundle and ZIP filename.
 */
class Moltex_Exporter_Site_Identity {

	/**
	 * Build identity from an absolute public site origin and display name.
	 *
	 * @param string $origin    Public source origin.
	 * @param string $site_name WordPress site title.
	 * @return array
	 * @throws InvalidArgumentException When the origin has no valid host.
	 */
	public static function from_values( $origin, $site_name ) {
		$parts = parse_url( trim( (string) $origin ) );
		if ( ! is_array( $parts ) || empty( $parts['host'] ) ) {
			throw new InvalidArgumentException( 'Site origin must contain a valid domain.' );
		}

		$domain = strtolower( rtrim( (string) $parts['host'], '.' ) );
		$seed   = $domain;
		if ( isset( $parts['port'] ) ) {
			$seed .= '-' . (int) $parts['port'];
		}
		if ( ! empty( $parts['path'] ) && '/' !== $parts['path'] ) {
			$seed .= '-' . trim( (string) $parts['path'], '/' );
		}

		$workspace_slug = strtolower( preg_replace( '/[^a-z0-9]+/', '-', $seed ) );
		$workspace_slug = trim( substr( $workspace_slug, 0, 100 ), '-' );
		if ( '' === $workspace_slug ) {
			throw new InvalidArgumentException( 'Site origin cannot produce a safe workspace name.' );
		}

		$site_name = trim( (string) $site_name );
		return array(
			'site_name'      => '' !== $site_name ? $site_name : $domain,
			'domain'         => $domain,
			'workspace_slug' => $workspace_slug,
		);
	}
}
