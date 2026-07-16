<?php
/**
 * Validates and persists reviewed reference screenshot declarations.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'WPINC' ) ) {
	die;
}

class Moltex_Exporter_Reference_Screenshots {

	const OPTION_NAME = 'moltex_reference_screenshots';
	const MAX_REFERENCES = 10;
	const MAX_BYTES = 10485760;

	/**
	 * Return saved declarations.
	 *
	 * @return array
	 */
	public function get_references() {
		$references = get_option( self::OPTION_NAME, array() );
		return is_array( $references ) ? array_values( $references ) : array();
	}

	/**
	 * Validate declarations and prepare their source receipts.
	 *
	 * @param array $references Candidate declarations.
	 * @return array Result containing valid references, prepared receipts, and errors.
	 */
	public function validate( $references ) {
		$errors = array();
		$valid = array();
		$prepared = array();

		if ( ! is_array( $references ) ) {
			return array(
				'valid'      => false,
				'references' => array(),
				'prepared'   => array(),
				'errors'     => array( 'Reference screenshots must be an array.' ),
			);
		}

		if ( count( $references ) > self::MAX_REFERENCES ) {
			return array(
				'valid'      => false,
				'references' => array(),
				'prepared'   => array(),
				'errors'     => array( sprintf( 'At most %d reference screenshots are allowed.', self::MAX_REFERENCES ) ),
			);
		}

		if ( empty( $references ) ) {
			return array(
				'valid'      => true,
				'references' => array(),
				'prepared'   => array(),
				'errors'     => array(),
			);
		}

		$uploads = wp_upload_dir();
		$uploads_root = empty( $uploads['basedir'] ) ? false : realpath( $uploads['basedir'] );
		if ( false === $uploads_root ) {
			return array(
				'valid'      => false,
				'references' => array(),
				'prepared'   => array(),
				'errors'     => array( 'The WordPress uploads directory is unavailable.' ),
			);
		}

		$uploads_prefix = trailingslashit( str_replace( '\\', '/', $uploads_root ) );
		$seen = array();
		foreach ( array_values( $references ) as $index => $reference ) {
			$result = $this->validate_one( $reference, $uploads_prefix );
			if ( ! $result['valid'] ) {
				$errors[] = sprintf( 'Screenshot %d: %s', $index + 1, $result['error'] );
				continue;
			}

			$key = strtolower( $result['prepared']['artifact'] );
			if ( isset( $seen[ $key ] ) ) {
				$errors[] = sprintf( 'Screenshot %d: duplicate artifact path %s.', $index + 1, $result['prepared']['artifact'] );
				continue;
			}
			$seen[ $key ] = true;
			$valid[] = $result['reference'];
			$prepared[] = $result['prepared'];
		}

		return array(
			'valid'      => empty( $errors ) && count( $valid ) === count( $references ),
			'references' => $valid,
			'prepared'   => $prepared,
			'errors'     => $errors,
		);
	}

	/**
	 * Validate and persist declarations as one atomic setting update.
	 *
	 * @param array $references Candidate declarations.
	 * @return array Validation result.
	 */
	public function save( $references ) {
		$result = $this->validate( $references );
		if ( ! $result['valid'] ) {
			return $result;
		}
		update_option( self::OPTION_NAME, $result['references'], false );
		return $result;
	}

	/**
	 * Validate a single declaration.
	 *
	 * @param mixed  $reference Candidate declaration.
	 * @param string $uploads_prefix Normalized uploads root with trailing slash.
	 * @return array
	 */
	private function validate_one( $reference, $uploads_prefix ) {
		if ( ! is_array( $reference ) || empty( $reference['attachment_id'] ) ) {
			return array( 'valid' => false, 'error' => 'attachment_id is required.' );
		}

		$attachment_id = absint( $reference['attachment_id'] );
		$source = get_attached_file( $attachment_id );
		$source_real = $source ? realpath( $source ) : false;
		$source_normalized = false === $source_real ? '' : str_replace( '\\', '/', $source_real );
		if ( false === $source_real || 0 !== strpos( $source_normalized, $uploads_prefix ) ) {
			return array( 'valid' => false, 'error' => 'attachment is unavailable or outside uploads.' );
		}

		$bytes = filesize( $source_real );
		$image = @getimagesize( $source_real );
		if ( 'png' !== strtolower( pathinfo( $source_real, PATHINFO_EXTENSION ) ) || false === $image || 'image/png' !== $image['mime'] ) {
			return array( 'valid' => false, 'error' => 'attachment must contain a valid PNG.' );
		}
		if ( false === $bytes || $bytes > self::MAX_BYTES ) {
			return array( 'valid' => false, 'error' => 'attachment exceeds the 10 MB evidence limit.' );
		}

		$route = isset( $reference['route'] ) ? trim( (string) $reference['route'] ) : '';
		$viewport = isset( $reference['viewport'] ) ? sanitize_file_name( (string) $reference['viewport'] ) : '';
		$label = ! empty( $reference['label'] ) ? sanitize_file_name( (string) $reference['label'] ) : 'page';
		if ( empty( $viewport ) || 1 !== preg_match( '#^/(?!/)[^\x00-\x1F\x7F]*$#', $route ) ) {
			return array( 'valid' => false, 'error' => 'route must be site-relative and viewport must be non-empty.' );
		}
		if ( empty( $label ) ) {
			$label = 'page';
		}

		$clean = array(
			'attachment_id' => $attachment_id,
			'route'         => $route,
			'viewport'      => $viewport,
			'label'         => $label,
		);
		$artifact = 'screenshots/' . $viewport . '-' . $label . '.png';

		return array(
			'valid'     => true,
			'reference' => $clean,
			'prepared'  => array_merge(
				$clean,
				array(
					'source'   => $source_real,
					'artifact' => $artifact,
					'bytes'    => $bytes,
					'sha256'   => hash_file( 'sha256', $source_real ),
				)
			),
		);
	}
}
