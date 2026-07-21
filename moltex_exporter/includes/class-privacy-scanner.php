<?php
/**
 * Final export-directory privacy scan.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Scans the exact uncompressed artifact inputs before bundle finalization.
 */
class Moltex_Exporter_Privacy_Scanner {

	const SCANNER_VERSION = 1;
	const MAX_SCAN_BYTES = 52428800;

	private $export_dir;

	public function __construct( $export_dir ) {
		$this->export_dir = rtrim( str_replace( '\\', '/', $export_dir ), '/' ) . '/';
	}

	/**
	 * Scan every existing artifact without returning matched secret values.
	 *
	 * @return array Clean scan receipt.
	 * @throws Moltex_Exporter_Contract_Exception When an unsafe artifact is found.
	 */
	public function scan() {
		$root = realpath( $this->export_dir );
		if ( false === $root ) {
			throw new Moltex_Exporter_Contract_Exception( 'Privacy scan export directory does not exist.' );
		}

		$artifacts = array();
		$findings = array();
		$scanned_bytes = 0;
		$iterator = new RecursiveIteratorIterator(
			new RecursiveDirectoryIterator( $root, FilesystemIterator::SKIP_DOTS )
		);

		foreach ( $iterator as $file ) {
			$relative = substr(
				str_replace( '\\', '/', $file->getPathname() ),
				strlen( str_replace( '\\', '/', $root ) ) + 1
			);
			$relative = Moltex_Exporter_Artifact_Registry::normalize_relative_path( $relative );

			if ( $file->isLink() ) {
				$findings[] = array( 'path' => $relative, 'code' => 'unsafe_symlink' );
				continue;
			}
			if ( ! $file->isFile() || in_array( $relative, array( 'bundle.json', 'privacy-scan.json' ), true ) ) {
				continue;
			}

			$bytes = (int) $file->getSize();
			if ( $bytes > self::MAX_SCAN_BYTES ) {
				$findings[] = array( 'path' => $relative, 'code' => 'privacy_scan_size_exceeded' );
				continue;
			}
			if ( 'php' === strtolower( pathinfo( $relative, PATHINFO_EXTENSION ) ) ) {
				$findings[] = array( 'path' => $relative, 'code' => 'executable_source' );
				continue;
			}

			$content = file_get_contents( $file->getPathname() );
			if ( false === $content ) {
				$findings[] = array( 'path' => $relative, 'code' => 'privacy_scan_read_failed' );
				continue;
			}

			foreach ( $this->detect( $content ) as $code ) {
				$findings[] = array( 'path' => $relative, 'code' => $code );
			}
			$scanned_bytes += $bytes;
			$artifacts[] = array(
				'path'   => $relative,
				'bytes'  => $bytes,
				'sha256' => hash( 'sha256', $content ),
			);
		}

		if ( ! empty( $findings ) ) {
			usort( $findings, array( $this, 'compare_finding' ) );
			$labels = array();
			foreach ( $findings as $finding ) {
				$labels[] = $finding['path'] . ' (' . $finding['code'] . ')';
			}
			throw new Moltex_Exporter_Contract_Exception(
				'Privacy scan blocked export artifacts: ' . implode( ', ', $labels )
			);
		}

		usort( $artifacts, array( $this, 'compare_artifact' ) );
		return array(
			'schema_version' => 1,
			'status'          => 'pass',
			'scanner_version' => self::SCANNER_VERSION,
			'scanned_files'   => count( $artifacts ),
			'scanned_bytes'   => $scanned_bytes,
			'artifacts'       => $artifacts,
		);
	}

	/**
	 * Return finding codes only; matched values must never enter diagnostics.
	 *
	 * @param string $content Artifact bytes.
	 * @return array
	 */
	private function detect( $content ) {
		$patterns = array(
			'private_key'       => '/-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/',
			'credential_prefix' => '/(?:AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,})/',
			'credential_value'  => '/(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|passwd)\s*["\']?\s*[:=]\s*["\']?[A-Za-z0-9_+\/=.-]{8,}/i',
			'privacy_canary'    => '/(?:SYNTHETIC|GOLDEN)-SECRET-MUST-NOT-EXPORT|MOLTEX-PRIVACY-CANARY/i',
			'server_path'       => '/(?:[A-Za-z]:\\\\(?:inetpub|xampp|wamp|Users)\\\\|\/(?:home|var\/www|srv\/www)\/)[^\s"\']+/i',
		);
		$codes = array();
		foreach ( $patterns as $code => $pattern ) {
			if ( preg_match( $pattern, $content ) ) {
				$codes[] = $code;
			}
		}
		return $codes;
	}

	private function compare_artifact( $left, $right ) {
		return strcmp( $left['path'], $right['path'] );
	}

	private function compare_finding( $left, $right ) {
		$path = strcmp( $left['path'], $right['path'] );
		return 0 !== $path ? $path : strcmp( $left['code'], $right['code'] );
	}
}
