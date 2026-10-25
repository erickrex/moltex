<?php
/**
 * Taxonomy Scanner Class
 *
 * Exports taxonomy and term data for all taxonomies used by exported content.
 * Includes term metadata, hierarchical relationships, and term-to-post mappings.
 *
 * @package Moltex_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Taxonomy Scanner Class
 */
class Moltex_Exporter_Taxonomy_Scanner extends Moltex_Exporter_Scanner_Base {

	/**
	 * Exported content data (from ContentScanner).
	 *
	 * @var array
	 */
	private $exported_content = array();

	/**
	 * Post IDs that were exported.
	 *
	 * @var array
	 */
	private $exported_post_ids = array();

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
		$this->exported_content = isset( $this->context['content'] ) ? $this->context['content'] : array();
		$this->extract_exported_post_ids();
	}

	/**
	 * Extract post IDs from exported content.
	 */
	private function extract_exported_post_ids() {
		$this->exported_post_ids = array();

		// Extract from posts
		if ( isset( $this->exported_content['posts'] ) && is_array( $this->exported_content['posts'] ) ) {
			foreach ( $this->exported_content['posts'] as $post ) {
				if ( isset( $post['id'] ) ) {
					$this->exported_post_ids[] = $post['id'];
				}
			}
		}

		// Extract from pages
		if ( isset( $this->exported_content['pages'] ) && is_array( $this->exported_content['pages'] ) ) {
			foreach ( $this->exported_content['pages'] as $page ) {
				if ( isset( $page['id'] ) ) {
					$this->exported_post_ids[] = $page['id'];
				}
			}
		}

		// Extract from custom post types
		if ( isset( $this->exported_content['custom_post_types'] ) && is_array( $this->exported_content['custom_post_types'] ) ) {
			foreach ( $this->exported_content['custom_post_types'] as $post_type => $items ) {
				if ( is_array( $items ) ) {
					foreach ( $items as $item ) {
						if ( isset( $item['id'] ) ) {
							$this->exported_post_ids[] = $item['id'];
						}
					}
				}
			}
		}

		$this->exported_post_ids = array_unique( $this->exported_post_ids );
	}

	/**
	 * Scan and collect taxonomy data.
	 *
	 * @return array Taxonomy data.
	 */
	public function scan() {
		// Identify all taxonomies used by exported content
		$used_taxonomies = $this->identify_used_taxonomies();

		// Build taxonomy data structure
		$taxonomy_data = array(
			'schema_version' => 1,
			'taxonomies'     => array(),
			'term_relationships' => array(),
		);

		// Export each taxonomy
		$this->geodir_term_meta = $this->load_geodir_term_meta();
		foreach ( $used_taxonomies as $taxonomy_name ) {
			$taxonomy_data['taxonomies'][ $taxonomy_name ] = $this->export_taxonomy( $taxonomy_name );
		}

		// Rows of the plugin-owned GeoDirectory term table (C4/M4), reconciled
		// against the exported terms so none disappear without a reason.
		if ( null !== $this->geodir_term_meta ) {
			$unattached = array();
			foreach ( $this->geodir_term_meta['rows_by_term'] as $term_id => $rows ) {
				if ( ! isset( $this->geodir_attached_terms[ $term_id ] ) ) {
					foreach ( $rows as $row ) {
						$unattached[] = array( 'term_id' => $term_id ) + $row;
					}
				}
			}
			$unattached = array_merge( $unattached, $this->geodir_term_meta['rows_without_term'] );
			$taxonomy_data['geodir_term_meta'] = array(
				'table'            => $this->geodir_term_meta['table'],
				'source_rows'      => $this->geodir_term_meta['source_rows'],
				'attached_rows'    => $this->geodir_term_meta['source_rows'] - count( $unattached ),
				'unattached_rows'  => $unattached,
			);
		}

		// Export term-to-post relationships for exported content
		$taxonomy_data['term_relationships'] = $this->export_term_relationships();

		return $taxonomy_data;
	}

	/**
	 * Identify all taxonomies used by exported content.
	 *
	 * @return array Taxonomy names.
	 */
	private function identify_used_taxonomies() {
		$taxonomies = array();

		// Get taxonomies from exported content
		foreach ( $this->exported_post_ids as $post_id ) {
			$post = get_post( $post_id );
			if ( ! $post ) {
				continue;
			}

			$post_taxonomies = get_object_taxonomies( $post->post_type );
			$taxonomies = array_merge( $taxonomies, $post_taxonomies );
		}

		// Remove duplicates and exclude certain built-in taxonomies
		$taxonomies = array_unique( $taxonomies );
		$exclude = array( 'nav_menu', 'link_category', 'post_format' );
		$taxonomies = array_diff( $taxonomies, $exclude );

		return array_values( $taxonomies );
	}

	/**
	 * Export a single taxonomy with all its terms.
	 *
	 * @param string $taxonomy_name Taxonomy name.
	 * @return array Taxonomy data.
	 */
	private function export_taxonomy( $taxonomy_name ) {
		$taxonomy_obj = get_taxonomy( $taxonomy_name );

		if ( ! $taxonomy_obj ) {
			return array();
		}

		// Get all terms for this taxonomy
		$terms = get_terms( array(
			'taxonomy'   => $taxonomy_name,
			'hide_empty' => false,
			'orderby'    => 'term_id',
			'order'      => 'ASC',
		) );

		if ( is_wp_error( $terms ) ) {
			return array();
		}

		// Build taxonomy data
		$taxonomy_data = array(
			'name'         => $taxonomy_obj->label,
			'slug'         => $taxonomy_name,
			'description'  => $taxonomy_obj->description,
			'hierarchical' => $taxonomy_obj->hierarchical,
			'public'       => $taxonomy_obj->public,
			'object_types' => $taxonomy_obj->object_type,
			'terms'        => array(),
		);

		// Export each term
		foreach ( $terms as $term ) {
			$taxonomy_data['terms'][] = $this->export_term( $term, $taxonomy_name );
		}

		return $taxonomy_data;
	}

	/**
	 * Export a single term with metadata.
	 *
	 * @param WP_Term $term Term object.
	 * @param string  $taxonomy_name Taxonomy name.
	 * @return array Term data.
	 */
	private function export_term( $term, $taxonomy_name ) {
		$term_data = array(
			'term_id'     => $term->term_id,
			'name'        => $term->name,
			'slug'        => $term->slug,
			'description' => $term->description,
			'parent'      => $term->parent,
			'count'       => $term->count,
		);

		// Get term metadata
		$term_meta = $this->get_term_metadata( $term->term_id, $taxonomy_name );
		if ( ! empty( $term_meta ) ) {
			$term_data['meta'] = $term_meta;
		}

		// Records stored only in the GeoDirectory term table (icon, colour,
		// default image, marker, descriptions).
		$term_id = (int) $term->term_id;
		if ( null !== $this->geodir_term_meta && isset( $this->geodir_term_meta['rows_by_term'][ $term_id ] ) ) {
			$term_data['geodir_meta'] = $this->geodir_term_meta['rows_by_term'][ $term_id ];
			$this->geodir_attached_terms[ $term_id ] = true;
		}

		return $term_data;
	}

	/**
	 * GeoDirectory term table rows (null when the table does not exist).
	 *
	 * @var array|null
	 */
	private $geodir_term_meta = null;

	/**
	 * Term IDs whose GeoDirectory rows were attached to an exported term.
	 *
	 * @var array
	 */
	private $geodir_attached_terms = array();

	/**
	 * Read every row of {prefix}geodir_term_meta, schema-agnostically: values
	 * are decoded, credential/personal columns dropped, and rows grouped by
	 * term_id. A meta_key/meta_value pair is also folded into a `meta` map.
	 *
	 * @return array|null
	 */
	private function load_geodir_term_meta() {
		global $wpdb;
		if ( ! isset( $wpdb ) || ! is_object( $wpdb ) ) {
			return null;
		}
		$table = $wpdb->prefix . 'geodir_term_meta';
		if ( ! $wpdb->get_var( $wpdb->prepare( 'SHOW TABLES LIKE %s', $table ) ) ) {
			return null;
		}
		$rows = $wpdb->get_results( "SELECT * FROM {$table}", ARRAY_A );
		$result = array( 'table' => 'geodir_term_meta', 'source_rows' => 0, 'rows_by_term' => array(), 'rows_without_term' => array() );
		foreach ( is_array( $rows ) ? $rows : array() as $row ) {
			if ( ! is_array( $row ) ) {
				continue;
			}
			$result['source_rows']++;
			$clean = array();
			foreach ( $row as $column => $value ) {
				if ( preg_match( '/email|_ip$|^ip$|user_id|owner_id|password|token|secret/i', (string) $column ) ) {
					continue;
				}
				$clean[ $column ] = $this->decode_value( $value );
			}
			if ( isset( $clean['meta_key'] ) && array_key_exists( 'meta_value', $clean ) ) {
				$clean['meta'] = array( (string) $clean['meta_key'] => $clean['meta_value'] );
			}
			$term_id = isset( $clean['term_id'] ) ? (int) $clean['term_id'] : 0;
			unset( $clean['term_id'] );
			if ( $term_id > 0 ) {
				$result['rows_by_term'][ $term_id ][] = $clean;
			} else {
				$result['rows_without_term'][] = $clean;
			}
		}
		return $result;
	}

	/**
	 * Decode a serialized or JSON column value without instantiating objects.
	 *
	 * @param mixed $value Raw column value.
	 * @return mixed
	 */
	private function decode_value( $value ) {
		if ( ! is_string( $value ) ) {
			return $value;
		}
		if ( preg_match( '/^(a|s|i|d|b):\d*[:;]/', $value ) || 'N;' === $value ) {
			$decoded = @unserialize( $value, array( 'allowed_classes' => false ) );
			if ( false !== $decoded || 'b:0;' === $value ) {
				return $decoded;
			}
		}
		$first = substr( ltrim( $value ), 0, 1 );
		if ( '{' === $first || '[' === $first ) {
			$decoded = json_decode( $value, true );
			if ( null !== $decoded ) {
				return $decoded;
			}
		}
		return $value;
	}

	/**
	 * Get term metadata with filtering.
	 *
	 * @param int    $term_id Term ID.
	 * @param string $taxonomy_name Taxonomy name.
	 * @return array Filtered term metadata.
	 */
	private function get_term_metadata( $term_id, $taxonomy_name ) {
		// Get all term meta
		$all_meta = get_term_meta( $term_id );

		if ( empty( $all_meta ) ) {
			return array();
		}

		return Moltex_Exporter_Security_Filters::filter_export_meta( $all_meta );
	}

	/**
	 * Export term-to-post relationships for exported content.
	 *
	 * @return array Term relationships keyed by post ID.
	 */
	private function export_term_relationships() {
		$relationships = array();

		foreach ( $this->exported_post_ids as $post_id ) {
			$post = get_post( $post_id );
			if ( ! $post ) {
				continue;
			}

			// Get all taxonomies for this post type
			$taxonomies = get_object_taxonomies( $post->post_type );

			$post_terms = array();

			foreach ( $taxonomies as $taxonomy ) {
				// Skip excluded taxonomies
				$exclude = array( 'nav_menu', 'link_category', 'post_format' );
				if ( in_array( $taxonomy, $exclude, true ) ) {
					continue;
				}

				// Get terms for this post and taxonomy
				$terms = wp_get_post_terms( $post_id, $taxonomy, array( 'fields' => 'ids' ) );

				if ( ! is_wp_error( $terms ) && ! empty( $terms ) ) {
					$post_terms[ $taxonomy ] = $terms;
				}
			}

			if ( ! empty( $post_terms ) ) {
				$relationships[ $post_id ] = $post_terms;
			}
		}

		return $relationships;
	}
}
