<?php
/**
 * Declarative ownership signatures for legacy plugin evidence.
 *
 * Signatures are observations only. This registry never loads plugin PHP and
 * never chooses a target implementation.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Resolve high-confidence plugin-family ownership without substring guessing.
 */
class Moltex_Exporter_Plugin_Signature_Registry {

	/**
	 * Return stable plugin-family signatures.
	 *
	 * @return array
	 */
	public function get_signatures() {
		return array(
			'advanced-custom-fields' => array(
				'slugs' => array( 'advanced-custom-fields', 'advanced-custom-fields-pro' ),
				'table_prefixes' => array( 'acf_' ),
				'meta_prefixes' => array( 'acf_' ),
				'block_namespaces' => array( 'acf/' ),
			),
			'pods' => array(
				'slugs' => array( 'pods' ),
				'table_prefixes' => array( 'pods_' ),
				'meta_prefixes' => array( 'pods_' ),
			),
			'meta-box' => array(
				'slugs' => array( 'meta-box', 'meta-box-aio' ),
				'meta_prefixes' => array( 'rwmb_' ),
			),
			'carbon-fields' => array(
				'slugs' => array( 'carbon-fields' ),
				'meta_prefixes' => array( '_carbon_' ),
			),
			'geodirectory' => array(
				'slugs' => array( 'geodirectory' ),
				'table_prefixes' => array( 'geodir_', 'gd_' ),
				'meta_prefixes' => array( 'geodir_', 'gd_' ),
				'shortcodes' => array( 'gd_map', 'gd_search', 'gd_listings', 'gd_post_images', 'gd_post_meta', 'gd_loop', 'gd_loop_paging' ),
				'block_namespaces' => array( 'geodirectory/' ),
			),
			'gravity-forms' => array(
				'slugs' => array( 'gravityforms' ),
				'table_prefixes' => array( 'gf_' ),
				'shortcodes' => array( 'gravityform' ),
			),
			'ninja-forms' => array(
				'slugs' => array( 'ninja-forms' ),
				'table_prefixes' => array( 'nf3_' ),
				'shortcodes' => array( 'ninja_form' ),
			),
			'forminator' => array(
				'slugs' => array( 'forminator' ),
				'table_prefixes' => array( 'frmt_' ),
				'shortcodes' => array( 'forminator_form' ),
			),
			'contact-form-7' => array(
				'slugs' => array( 'contact-form-7' ),
				'shortcodes' => array( 'contact-form-7' ),
			),
			'kadence-blocks' => array(
				'slugs' => array( 'kadence-blocks', 'kadence-blocks-pro' ),
				'block_namespaces' => array( 'kadence/' ),
			),
		);
	}

	/**
	 * Normalize an installed slug into a known family.
	 *
	 * @param string $slug Plugin slug.
	 * @return string|null
	 */
	public function family_for_slug( $slug ) {
		$slug = strtolower( trim( (string) $slug ) );
		foreach ( $this->get_signatures() as $family => $signature ) {
			if ( in_array( $slug, $signature['slugs'], true ) ) {
				return $family;
			}
		}
		return null;
	}

	/**
	 * Resolve ownership from an exact shortcode signature.
	 *
	 * @param string $tag Shortcode tag.
	 * @return array
	 */
	public function resolve_shortcode( $tag ) {
		return $this->resolve_exact( 'shortcodes', strtolower( (string) $tag ) );
	}

	/**
	 * Resolve ownership from a namespace prefix.
	 *
	 * @param string $name Block name.
	 * @return array
	 */
	public function resolve_block( $name ) {
		return $this->resolve_prefix( 'block_namespaces', strtolower( (string) $name ) );
	}

	/**
	 * Resolve ownership from a table prefix after the WordPress prefix is removed.
	 *
	 * @param string $name Table suffix.
	 * @return array
	 */
	public function resolve_table( $name ) {
		return $this->resolve_prefix( 'table_prefixes', strtolower( (string) $name ) );
	}

	/**
	 * Resolve ownership from a metadata prefix.
	 *
	 * @param string $name Metadata key.
	 * @return array
	 */
	public function resolve_meta( $name ) {
		return $this->resolve_prefix( 'meta_prefixes', strtolower( (string) $name ) );
	}

	private function resolve_exact( $key, $value ) {
		foreach ( $this->get_signatures() as $family => $signature ) {
			if ( isset( $signature[ $key ] ) && in_array( $value, $signature[ $key ], true ) ) {
				return array( 'source_plugin' => $family, 'ownership_confidence' => 'high' );
			}
		}
		return array( 'source_plugin' => 'unknown', 'ownership_confidence' => 'unknown' );
	}

	private function resolve_prefix( $key, $value ) {
		foreach ( $this->get_signatures() as $family => $signature ) {
			if ( empty( $signature[ $key ] ) ) {
				continue;
			}
			foreach ( $signature[ $key ] as $prefix ) {
				if ( 0 === strpos( $value, $prefix ) ) {
					return array( 'source_plugin' => $family, 'ownership_confidence' => 'high' );
				}
			}
		}
		return array( 'source_plugin' => 'unknown', 'ownership_confidence' => 'unknown' );
	}
}
