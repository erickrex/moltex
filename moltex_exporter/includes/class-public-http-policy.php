<?php
/**
 * Public-only HTTP policy for exporter source requests.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Validates destinations and delegates requests to WordPress safe HTTP APIs.
 */
class Moltex_Exporter_Public_Http_Policy {

	const DEFAULT_MAX_BYTES = 5242880;

	/**
	 * Validate an absolute HTTP(S) URL and every resolved address.
	 *
	 * @param string        $url      Candidate URL.
	 * @param callable|null $resolver Testable hostname resolver.
	 * @return string Validated URL.
	 * @throws InvalidArgumentException For an unsafe destination.
	 */
	public static function require_public_url( $url, $resolver = null ) {
		if ( ! is_string( $url ) || '' === trim( $url ) || trim( $url ) !== $url ) {
			throw new InvalidArgumentException( 'HTTP destination must be an absolute public URL.' );
		}
		$parts = parse_url( $url );
		$scheme = is_array( $parts ) && isset( $parts['scheme'] ) ? strtolower( $parts['scheme'] ) : '';
		$host = is_array( $parts ) && isset( $parts['host'] ) ? strtolower( trim( rtrim( $parts['host'], '.' ), '[]' ) ) : '';
		$port = is_array( $parts ) && isset( $parts['port'] ) ? (int) $parts['port'] : ( 'https' === $scheme ? 443 : 80 );
		if (
			! in_array( $scheme, array( 'http', 'https' ), true ) ||
			'' === $host ||
			isset( $parts['user'] ) ||
			isset( $parts['pass'] ) ||
			$port < 1 ||
			$port > 65535 ||
			'localhost' === $host ||
			'.localhost' === substr( $host, -10 )
		) {
			throw new InvalidArgumentException( 'HTTP destination must be an absolute public URL.' );
		}

		$addresses = filter_var( $host, FILTER_VALIDATE_IP )
			? array( $host )
			: call_user_func( $resolver ?: array( __CLASS__, 'resolve_host' ), $host );
		if ( empty( $addresses ) ) {
			throw new InvalidArgumentException( 'HTTP destination hostname could not be resolved.' );
		}
		foreach ( array_unique( $addresses ) as $address ) {
			if ( ! self::is_public_ip( $address ) ) {
				throw new InvalidArgumentException( 'HTTP destination resolves to a non-public address.' );
			}
		}
		return $url;
	}

	/**
	 * Execute a bounded request through WordPress redirect-safe validation.
	 *
	 * @param string $url  Public URL.
	 * @param array  $args WordPress request arguments.
	 * @return array|WP_Error
	 */
	public static function get( $url, array $args = array() ) {
		self::require_public_url( $url );
		$defaults = array(
			'timeout'             => 30,
			'redirection'         => 5,
			'sslverify'           => true,
			'reject_unsafe_urls'  => true,
			'limit_response_size' => self::DEFAULT_MAX_BYTES,
		);
		return wp_safe_remote_get( $url, array_merge( $defaults, $args ) );
	}

	/**
	 * Resolve A and AAAA records without returning hostnames to the caller.
	 *
	 * @param string $host Hostname.
	 * @return array
	 */
	public static function resolve_host( $host ) {
		$addresses = array();
		if ( function_exists( 'dns_get_record' ) ) {
			$records = @dns_get_record( $host, DNS_A | DNS_AAAA );
			foreach ( is_array( $records ) ? $records : array() as $record ) {
				if ( ! empty( $record['ip'] ) ) {
					$addresses[] = $record['ip'];
				}
				if ( ! empty( $record['ipv6'] ) ) {
					$addresses[] = $record['ipv6'];
				}
			}
		}
		if ( empty( $addresses ) ) {
			$fallback = @gethostbynamel( $host );
			$addresses = is_array( $fallback ) ? $fallback : array();
		}
		return $addresses;
	}

	/**
	 * Reject private, reserved, link-local, loopback, and mapped-private IPs.
	 *
	 * @param string $address IP address.
	 * @return bool
	 */
	private static function is_public_ip( $address ) {
		if ( ! filter_var( $address, FILTER_VALIDATE_IP ) ) {
			return false;
		}
		if ( 0 === stripos( $address, '::ffff:' ) ) {
			$address = substr( $address, 7 );
		}
		return false !== filter_var(
			$address,
			FILTER_VALIDATE_IP,
			FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE
		);
	}
}
