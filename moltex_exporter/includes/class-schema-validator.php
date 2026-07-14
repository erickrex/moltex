<?php
/**
 * Dependency-free JSON Schema subset used by moltex-export/1.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Validates the contract keywords used by the checked-in schemas.
 */
class Moltex_Exporter_Schema_Validator {

	/**
	 * Validate data against a schema array.
	 *
	 * @param mixed $data Data to validate.
	 * @param array $schema Schema definition.
	 * @return array Validation error messages.
	 */
	public function validate( $data, array $schema ) {
		$errors = array();
		$this->validate_node( $data, $schema, '$', $errors );
		return $errors;
	}

	/**
	 * Load and validate against a schema file.
	 *
	 * @param mixed  $data Data to validate.
	 * @param string $schema_path Schema path.
	 * @return array Validation error messages.
	 */
	public function validate_file( $data, $schema_path ) {
		if ( ! is_file( $schema_path ) || ! is_readable( $schema_path ) ) {
			return array( 'Schema file is unavailable: ' . $schema_path );
		}

		$schema = json_decode( file_get_contents( $schema_path ), true );
		if ( ! is_array( $schema ) || JSON_ERROR_NONE !== json_last_error() ) {
			return array( 'Schema file is not valid JSON: ' . $schema_path );
		}

		return $this->validate( $data, $schema );
	}

	private function validate_node( $data, array $schema, $path, array &$errors ) {
		if ( array_key_exists( 'const', $schema ) && $data !== $schema['const'] ) {
			$errors[] = $path . ' must equal the declared constant.';
		}

		if ( isset( $schema['enum'] ) && is_array( $schema['enum'] ) && ! in_array( $data, $schema['enum'], true ) ) {
			$errors[] = $path . ' is not one of the allowed values.';
		}

		if ( isset( $schema['type'] ) && ! $this->matches_type( $data, $schema['type'] ) ) {
			$errors[] = sprintf( '%s must be of type %s.', $path, is_array( $schema['type'] ) ? implode( '|', $schema['type'] ) : $schema['type'] );
			return;
		}

		if ( is_array( $data ) && 'array' === $this->declared_type( $schema ) ) {
			$this->validate_array( $data, $schema, $path, $errors );
		} elseif ( is_array( $data ) && 'object' === $this->declared_type( $schema ) ) {
			$this->validate_object( $data, $schema, $path, $errors );
		} elseif ( is_array( $data ) && $this->is_object_array( $data ) ) {
			$this->validate_object( $data, $schema, $path, $errors );
		} elseif ( is_array( $data ) ) {
			$this->validate_array( $data, $schema, $path, $errors );
		} elseif ( is_string( $data ) ) {
			$this->validate_string( $data, $schema, $path, $errors );
		} elseif ( is_int( $data ) || is_float( $data ) ) {
			if ( isset( $schema['minimum'] ) && $data < $schema['minimum'] ) {
				$errors[] = $path . ' is below the minimum.';
			}
		}
	}

	private function validate_object( array $data, array $schema, $path, array &$errors ) {
		if ( isset( $schema['required'] ) && is_array( $schema['required'] ) ) {
			foreach ( $schema['required'] as $required_key ) {
				if ( ! array_key_exists( $required_key, $data ) ) {
					$errors[] = $path . '.' . $required_key . ' is required.';
				}
			}
		}

		$properties = isset( $schema['properties'] ) && is_array( $schema['properties'] ) ? $schema['properties'] : array();
		foreach ( $properties as $key => $property_schema ) {
			if ( array_key_exists( $key, $data ) && is_array( $property_schema ) ) {
				$this->validate_node( $data[ $key ], $property_schema, $path . '.' . $key, $errors );
			}
		}

		if ( isset( $schema['additionalProperties'] ) && false === $schema['additionalProperties'] ) {
			foreach ( array_keys( $data ) as $key ) {
				if ( ! array_key_exists( $key, $properties ) ) {
					$errors[] = $path . '.' . $key . ' is not an allowed property.';
				}
			}
		}
	}

	private function validate_array( array $data, array $schema, $path, array &$errors ) {
		if ( isset( $schema['minItems'] ) && count( $data ) < (int) $schema['minItems'] ) {
			$errors[] = $path . ' has fewer items than allowed.';
		}

		if ( isset( $schema['maxItems'] ) && count( $data ) > (int) $schema['maxItems'] ) {
			$errors[] = $path . ' has more items than allowed.';
		}

		if ( isset( $schema['items'] ) && is_array( $schema['items'] ) ) {
			foreach ( $data as $index => $item ) {
				$this->validate_node( $item, $schema['items'], $path . '[' . $index . ']', $errors );
			}
		}
	}

	private function validate_string( $data, array $schema, $path, array &$errors ) {
		if ( isset( $schema['minLength'] ) && strlen( $data ) < (int) $schema['minLength'] ) {
			$errors[] = $path . ' is shorter than allowed.';
		}

		if ( isset( $schema['pattern'] ) && 1 !== preg_match( '#' . str_replace( '#', '\\#', $schema['pattern'] ) . '#', $data ) ) {
			$errors[] = $path . ' does not match the required pattern.';
		}
	}

	private function matches_type( $data, $type ) {
		if ( is_array( $type ) ) {
			foreach ( $type as $candidate ) {
				if ( $this->matches_type( $data, $candidate ) ) {
					return true;
				}
			}
			return false;
		}

		switch ( $type ) {
			case 'object':
				return is_array( $data ) && $this->is_object_array( $data );
			case 'array':
				return is_array( $data ) && ( array() === $data || ! $this->is_object_array( $data ) );
			case 'string':
				return is_string( $data );
			case 'integer':
				return is_int( $data );
			case 'number':
				return is_int( $data ) || is_float( $data );
			case 'boolean':
				return is_bool( $data );
			case 'null':
				return null === $data;
		}

		return true;
	}

	private function declared_type( array $schema ) {
		return isset( $schema['type'] ) && is_string( $schema['type'] ) ? $schema['type'] : null;
	}

	private function is_object_array( array $value ) {
		if ( array() === $value ) {
			// Empty JSON objects decode to arrays in associative mode. Accept them as objects.
			return true;
		}

		return array_keys( $value ) !== range( 0, count( $value ) - 1 );
	}
}
