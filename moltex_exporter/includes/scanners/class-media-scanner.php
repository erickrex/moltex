<?php
/**
 * Media Scanner Class
 *
 * Scans exported content for media references and exports only referenced media files.
 * Creates a media map for URL rewriting and exports attachment metadata.
 *
 * @package Moltex_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Media Scanner Class
 */
class Moltex_Exporter_Media_Scanner extends Moltex_Exporter_Scanner_Base {

	/**
	 * Exported content data (from ContentScanner).
	 *
	 * @var array
	 */
	private $exported_content = array();

	/**
	 * Referenced media items.
	 *
	 * @var array
	 */
	private $referenced_media = array();

	/**
	 * Media map for URL rewriting.
	 *
	 * @var array
	 */
	private $media_map = array();

	/** Export artifact path keyed by source media URL. */
	private $media_artifacts = array();

	/**
	 * Video URL => poster image URL, from <video poster> markup (M2).
	 *
	 * @var array
	 */
	private $video_posters = array();

	/** First exported artifact path keyed by source-file SHA-256. */
	private $artifacts_by_hash = array();

	/**
	 * WordPress uploads directory info.
	 *
	 * @var array
	 */
	private $upload_dir = array();

	/** @var array|null Back-reference applied to media added while scanning. */
	private $current_reference = null;

	/** @var array URL => {sha256, bytes} for bundled files. */
	private $artifact_info = array();

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
		$this->exported_content = isset( $this->context['content'] ) ? $this->context['content'] : array();
		$this->upload_dir = wp_upload_dir();
	}

	/**
	 * Scan and collect media data.
	 *
	 * @return array Media data including map and metadata.
	 */
	public function scan() {
		$this->media_map         = array();
		$this->media_artifacts   = array();
		$this->artifacts_by_hash = array();
		$this->artifact_info     = array();

		// Identify all referenced media
		$this->identify_referenced_media();

		// Copy media files to export directory
		$this->copy_media_files();

		// Generate media map
		$this->generate_media_map();

		// Return media data
		$bundled_files = count(
			array_filter(
				$this->media_map,
				function ( $entry ) {
					return isset( $entry['acquisition']['status'] ) && 'bundled' === $entry['acquisition']['status'];
				}
			)
		);
		$deferred_files = count(
			array_filter(
				$this->media_map,
				function ( $entry ) {
					return isset( $entry['acquisition']['status'] ) && 'deferred' === $entry['acquisition']['status'];
				}
			)
		);
		return array(
			'media_map'         => $this->media_map,
			'total_files'       => count( $this->referenced_media ),
			'bundled_files'     => $bundled_files,
			'deferred_files'    => $deferred_files,
			'unavailable_files' => count( $this->media_map ) - $bundled_files - $deferred_files,
		);
	}

	/**
	 * Identify all media referenced in exported content.
	 */
	private function identify_referenced_media() {
		$this->referenced_media = array();

		// Scan posts
		if ( isset( $this->exported_content['posts'] ) && is_array( $this->exported_content['posts'] ) ) {
			foreach ( $this->exported_content['posts'] as $post ) {
				$this->scan_content_item( $post );
			}
		}

		// Scan pages
		if ( isset( $this->exported_content['pages'] ) && is_array( $this->exported_content['pages'] ) ) {
			foreach ( $this->exported_content['pages'] as $page ) {
				$this->scan_content_item( $page );
			}
		}

		// Scan custom post types
		if ( isset( $this->exported_content['custom_post_types'] ) && is_array( $this->exported_content['custom_post_types'] ) ) {
			foreach ( $this->exported_content['custom_post_types'] as $post_type => $items ) {
				if ( is_array( $items ) ) {
					foreach ( $items as $item ) {
						$this->scan_content_item( $item );
					}
				}
			}
		}

		$this->identify_site_level_media();

		// Remove duplicates
		$this->referenced_media = array_values( array_unique( $this->referenced_media, SORT_REGULAR ) );
	}

	/**
	 * Scan a single content item for media references.
	 *
	 * @param array $content_item Content item data.
	 */
	private function scan_content_item( $content_item ) {
		// 1. Featured image
		if ( isset( $content_item['featured_media'] ) && ! empty( $content_item['featured_media'] ) ) {
			$this->add_media_reference( $content_item['featured_media'] );
		}

		// 2. Inline images in blocks
		if ( isset( $content_item['blocks'] ) && is_array( $content_item['blocks'] ) ) {
			$this->scan_blocks_for_media( $content_item['blocks'] );
		}

		// 3. Images in raw HTML content
		if ( isset( $content_item['raw_html'] ) && ! empty( $content_item['raw_html'] ) ) {
			$this->scan_html_for_media( $content_item['raw_html'] );
		}

		// GeoDirectory stores gallery relationships outside native attachments.
		// bundle_all (default) bundles every gallery original; featured_only keeps
		// the pre-1.4 behavior of deferring non-featured gallery items.
		if ( ! empty( $content_item['geodirectory']['media'] ) && is_array( $content_item['geodirectory']['media'] ) ) {
			$this->current_reference = $this->reference_for( $content_item, 'geodirectory.media' );
			foreach ( $content_item['geodirectory']['media'] as $media ) {
				$featured = ! empty( $media['metadata']['featured'] );
				$media['acquisition'] = ( $featured || 'featured_only' !== $this->media_acquisition_policy() )
					? $this->acquisition( 'bundled', 'bundle' )
					: $this->acquisition( 'deferred', 'source-fetch' );
				$this->add_media_reference( $media );
			}
		}

		// Videos, posters and block-attribute media that never reach <img> (M2/M4).
		$this->current_reference = $this->reference_for( $content_item, 'content' );
		if ( ! empty( $content_item['raw_html'] ) && is_string( $content_item['raw_html'] ) ) {
			$this->add_finder_hits( Moltex_Exporter_Media_Reference_Finder::find_in_html( $content_item['raw_html'], 'content' ), $content_item );
			foreach ( Moltex_Exporter_Media_Reference_Finder::find_video_posters( $content_item['raw_html'] ) as $video => $poster ) {
				$this->video_posters[ $video ] = $poster;
			}
		}
		foreach ( array( 'custom_fields', 'legacy_public_postmeta' ) as $section ) {
			if ( ! empty( $content_item['geodirectory'][ $section ] ) && is_array( $content_item['geodirectory'][ $section ] ) ) {
				$this->add_finder_hits( Moltex_Exporter_Media_Reference_Finder::find( $content_item['geodirectory'][ $section ], 'geodirectory.' . $section ), $content_item );
			}
		}
		// Ordinary (already privacy-filtered) postmeta, e.g. Web Stories
		// keep their video/poster URLs here rather than in post_content (C8).
		if ( ! empty( $content_item['postmeta'] ) && is_array( $content_item['postmeta'] ) ) {
			$this->add_finder_hits( Moltex_Exporter_Media_Reference_Finder::find( $content_item['postmeta'], 'postmeta' ), $content_item );
		}
		$this->current_reference = null;
	}

	/**
	 * Collect media referenced from site-level settings (M3/M4): logo, site
	 * icon, theme mods and GeoDirectory settings such as the default marker.
	 */
	private function identify_site_level_media() {
		$sources = array(
			'option:site_icon'   => array( 'site_icon' => get_option( 'site_icon' ) ),
			'option:site_logo'   => array( 'site_logo' => get_option( 'site_logo' ) ),
			'theme_mod'          => function_exists( 'get_theme_mods' ) ? get_theme_mods() : array(),
			'option:geodir_settings' => get_option( 'geodir_settings', array() ),
		);
		foreach ( $sources as $context => $value ) {
			if ( empty( $value ) ) {
				continue;
			}
			// The context is recorded as the reference source, so field paths stay relative.
			$hits = Moltex_Exporter_Media_Reference_Finder::find( $value, '' );
			$this->add_finder_hits( $hits, null, $context );
		}
		// Category icons/default images stored in term meta (C4).
		$taxonomies = isset( $this->context['taxonomies']['taxonomies'] ) && is_array( $this->context['taxonomies']['taxonomies'] ) ? $this->context['taxonomies']['taxonomies'] : array();
		foreach ( $taxonomies as $taxonomy => $taxonomy_data ) {
			foreach ( isset( $taxonomy_data['terms'] ) && is_array( $taxonomy_data['terms'] ) ? $taxonomy_data['terms'] : array() as $term ) {
				if ( ! isset( $term['term_id'] ) ) {
					continue;
				}
				// WordPress term meta plus rows stored only in geodir_term_meta.
				foreach ( array( 'meta', 'geodir_meta' ) as $section ) {
					if ( empty( $term[ $section ] ) ) {
						continue;
					}
					$hits = Moltex_Exporter_Media_Reference_Finder::find( $term[ $section ], 'meta' === $section ? '' : $section );
					$this->add_finder_hits( $hits, null, 'term:' . $taxonomy . ':' . (int) $term['term_id'] );
				}
			}
		}
		// GeoDirectory term rows whose term was not exported still name media.
		$unattached = isset( $this->context['taxonomies']['geodir_term_meta']['unattached_rows'] ) ? $this->context['taxonomies']['geodir_term_meta']['unattached_rows'] : array();
		foreach ( is_array( $unattached ) ? $unattached : array() as $row ) {
			$term_id = is_array( $row ) && isset( $row['term_id'] ) ? (int) $row['term_id'] : 0;
			$this->add_finder_hits( Moltex_Exporter_Media_Reference_Finder::find( $row, 'geodir_meta' ), null, 'geodir_term_meta:' . $term_id );
		}
		$this->current_reference = null;
	}

	/**
	 * Route finder hits into the reference list with their context.
	 *
	 * @param array[]     $hits         Finder hits.
	 * @param array|null  $content_item Owning content item, or null for site-level.
	 * @param string      $context      Site-level context label.
	 */
	private function add_finder_hits( array $hits, $content_item, $context = '' ) {
		foreach ( $hits as $hit ) {
			$this->current_reference = null === $content_item
				? array( 'source' => $context, 'field' => $hit['path'] )
				: $this->reference_for( $content_item, $hit['path'] );
			if ( 'attachment_id' === $hit['kind'] ) {
				$this->add_attachment_by_id( $hit['value'] );
			} else {
				$url = $hit['value'];
				if ( 0 === strpos( $url, '//' ) ) {
					$url = 'https:' . $url;
				} elseif ( ! preg_match( '#^https?://#i', $url ) && false === strpos( $url, '/wp-content/uploads/' ) ) {
					$url = trailingslashit( $this->upload_dir['baseurl'] ) . ltrim( $url, '/' );
				}
				$this->add_media_by_url( $url );
			}
		}
	}

	/**
	 * Build a back-reference to the content item that uses a media file.
	 *
	 * @param array  $content_item Content item.
	 * @param string $field        Field or context path.
	 * @return array
	 */
	private function reference_for( $content_item, $field ) {
		return array(
			'source'    => 'post',
			'post_id'   => isset( $content_item['id'] ) ? (int) $content_item['id'] : 0,
			'post_type' => isset( $content_item['type'] ) ? (string) $content_item['type'] : '',
			'field'     => (string) $field,
		);
	}

	/**
	 * Media acquisition policy from the admin settings.
	 *
	 * @return string bundle_all|featured_only
	 */
	private function media_acquisition_policy() {
		return Moltex_Exporter_Export_Policy::get( 'media_acquisition' );
	}

	/**
	 * Add a media reference to the list.
	 *
	 * @param array $media_data Media data with id, url, and optional alt.
	 */
	private function add_media_reference( $media_data ) {
		if ( empty( $media_data['url'] ) ) {
			return;
		}
		$reference = $this->current_reference;

		// Plugin-owned attachment IDs can collide with WordPress attachment IDs.
		// The source URL is the stable identity used by the bundle media map.
		foreach ( $this->referenced_media as $index => $existing ) {
			if ( $existing['url'] === $media_data['url'] ) {
				if ( ! $this->should_bundle( $existing ) && $this->should_bundle( $media_data ) ) {
					$existing['acquisition'] = $this->acquisition( 'bundled', 'bundle' );
				}
				if ( null !== $reference ) {
					$existing['references'] = isset( $existing['references'] ) ? $existing['references'] : array();
					if ( ! in_array( $reference, $existing['references'], true ) ) {
						$existing['references'][] = $reference;
					}
				}
				$this->referenced_media[ $index ] = $existing;
				return;
			}
		}

		$media_data['references'] = null === $reference ? array() : array( $reference );
		$this->referenced_media[] = $media_data;
	}

	/**
	 * Recursively scan blocks for media references.
	 *
	 * @param array $blocks Blocks array.
	 */
	private function scan_blocks_for_media( $blocks ) {
		foreach ( $blocks as $block ) {
			// Check block name for media-related blocks
			if ( isset( $block['name'] ) ) {
				$this->scan_block_for_media( $block );
			}

			// Recursively scan inner blocks
			if ( isset( $block['innerBlocks'] ) && is_array( $block['innerBlocks'] ) ) {
				$this->scan_blocks_for_media( $block['innerBlocks'] );
			}
		}
	}

	/**
	 * Scan a single block for media references.
	 *
	 * @param array $block Block data.
	 */
	private function scan_block_for_media( $block ) {
		$block_name = $block['name'];

		// Core image block
		if ( 'core/image' === $block_name && isset( $block['attrs']['id'] ) ) {
			$attachment_id = $block['attrs']['id'];
			$this->add_attachment_by_id( $attachment_id );
		}

		// Core gallery block
		if ( 'core/gallery' === $block_name && isset( $block['attrs']['ids'] ) && is_array( $block['attrs']['ids'] ) ) {
			foreach ( $block['attrs']['ids'] as $attachment_id ) {
				$this->add_attachment_by_id( $attachment_id );
			}
		}

		// Core media-text block
		if ( 'core/media-text' === $block_name && isset( $block['attrs']['mediaId'] ) ) {
			$attachment_id = $block['attrs']['mediaId'];
			$this->add_attachment_by_id( $attachment_id );
		}

		// Core cover block
		if ( 'core/cover' === $block_name && isset( $block['attrs']['id'] ) ) {
			$attachment_id = $block['attrs']['id'];
			$this->add_attachment_by_id( $attachment_id );
		}

		// Scan block HTML for image URLs
		if ( isset( $block['html'] ) && ! empty( $block['html'] ) ) {
			$this->scan_html_for_media( $block['html'] );
		}
	}

	/**
	 * Add an attachment by ID.
	 *
	 * @param int $attachment_id Attachment ID.
	 */
	private function add_attachment_by_id( $attachment_id ) {
		$attachment_id = absint( $attachment_id );
		if ( ! $attachment_id ) {
			return;
		}

		$attachment_url = wp_get_attachment_url( $attachment_id );
		if ( ! $attachment_url ) {
			return;
		}

		$alt_text = get_post_meta( $attachment_id, '_wp_attachment_image_alt', true );

		$this->add_media_reference( array(
			'id'  => $attachment_id,
			'url' => $attachment_url,
			'alt' => $alt_text,
		) );
	}

	/**
	 * Scan HTML content for media URLs.
	 *
	 * @param string $html HTML content.
	 */
	private function scan_html_for_media( $html ) {
		// Match img tags
		preg_match_all( '/<img[^>]+src=["\']([^"\']+)["\'][^>]*>/i', $html, $img_matches );
		
		if ( ! empty( $img_matches[1] ) ) {
			foreach ( $img_matches[1] as $img_url ) {
				$this->add_media_by_url( $img_url );
			}
		}

		// Match background images in style attributes
		preg_match_all( '/background-image:\s*url\(["\']?([^"\')\s]+)["\']?\)/i', $html, $bg_matches );
		
		if ( ! empty( $bg_matches[1] ) ) {
			foreach ( $bg_matches[1] as $bg_url ) {
				$this->add_media_by_url( $bg_url );
			}
		}

		// Match srcset attributes for responsive images
		preg_match_all( '/srcset=["\']([^"\']+)["\']/i', $html, $srcset_matches );
		
		if ( ! empty( $srcset_matches[1] ) ) {
			foreach ( $srcset_matches[1] as $srcset ) {
				// Parse srcset (format: "url1 1x, url2 2x" or "url1 100w, url2 200w")
				$srcset_urls = preg_split( '/,\s*/', $srcset );
				foreach ( $srcset_urls as $srcset_item ) {
					// Extract URL (everything before the descriptor)
					$parts = preg_split( '/\s+/', trim( $srcset_item ) );
					if ( ! empty( $parts[0] ) ) {
						$this->add_media_by_url( $parts[0] );
					}
				}
			}
		}
	}

	/**
	 * Add media by URL.
	 *
	 * @param string $url Media URL.
	 */
	private function add_media_by_url( $url ) {
		// Check if this is a local upload URL
		if ( ! $this->is_local_upload_url( $url ) ) {
			// Handle CDN URLs - add to map but don't copy
			if ( $this->is_cdn_url( $url ) ) {
				$this->add_cdn_reference( $url );
			}
			return;
		}

		// Try to get attachment ID from URL
		$attachment_id = attachment_url_to_postid( $url );
		
		if ( $attachment_id ) {
			$this->add_attachment_by_id( $attachment_id );
		} else {
			// Add by URL even if we can't find the attachment ID
			// This handles edge cases where attachment_url_to_postid fails
			$this->add_media_reference( array(
				'id'  => 0,
				'url' => $url,
				'alt' => '',
			) );
		}
	}

	/**
	 * Check if URL is a local upload URL.
	 *
	 * @param string $url URL to check.
	 * @return bool True if local upload URL.
	 */
	private function is_local_upload_url( $url ) {
		$upload_url = $this->upload_dir['baseurl'];
		
		// Normalize both URLs to protocol-relative for comparison
		$normalized_url = preg_replace( '#^https?:#', '', $url );
		$normalized_upload_url = preg_replace( '#^https?:#', '', $upload_url );

		// Check if URL starts with upload URL (protocol-agnostic)
		if ( strpos( $normalized_url, $normalized_upload_url ) === 0 ) {
			return true;
		}

		// Check if it's a relative URL to uploads
		if ( strpos( $url, '/wp-content/uploads/' ) !== false ) {
			return true;
		}

		return false;
	}

	/**
	 * Check if URL is a CDN URL.
	 *
	 * @param string $url URL to check.
	 * @return bool True if CDN URL.
	 */
	private function is_cdn_url( $url ) {
		// Common CDN patterns
		$cdn_patterns = array(
			'cloudfront.net',
			'cloudflare.com',
			'cdn.',
			'amazonaws.com',
			'googleusercontent.com',
		);

		foreach ( $cdn_patterns as $pattern ) {
			if ( strpos( $url, $pattern ) !== false ) {
				return true;
			}
		}

		return false;
	}

	/**
	 * Add CDN reference to media map.
	 *
	 * @param string $url CDN URL.
	 */
	private function add_cdn_reference( $url ) {
		// Add to media map with note that it's a CDN URL
		$this->media_map[] = array(
			'wp_src'      => $url,
			'artifact'    => null,
			'type'        => 'cdn',
			'note'        => 'External CDN resource - acquire into the target repository before production',
			'acquisition' => $this->acquisition( 'deferred', 'source-fetch' ),
		);
	}

	/**
	 * Copy media files to export directory.
	 */
	private function copy_media_files() {
		if ( empty( $this->export_dir ) ) {
			return;
		}

		// Create media directory
		$media_dir = trailingslashit( $this->export_dir ) . 'media';
		if ( ! file_exists( $media_dir ) ) {
			wp_mkdir_p( $media_dir );
		}

		foreach ( $this->referenced_media as $media ) {
			if ( ! $this->should_bundle( $media ) ) {
				continue;
			}
			$this->copy_single_media_file( $media, $media_dir );
		}
	}

	/**
	 * Copy a single media file.
	 *
	 * @param array  $media Media data.
	 * @param string $media_dir Media directory path.
	 * @return string|false Exported artifact path or false on failure.
	 */
	private function copy_single_media_file( $media, $media_dir ) {
		$url = $media['url'];

		// Get the file path from URL
		$file_path = $this->get_file_path_from_url( $url );
		
		if ( ! $file_path || ! file_exists( $file_path ) ) {
			$this->log_warning(
				'media',
				sprintf( 'Media file not found on disk (may be a deleted thumbnail): %s', $url )
			);
			return false;
		}

		// Get relative path to preserve directory structure
		$relative_path = $this->get_relative_upload_path( $url );
		
		if ( ! $relative_path ) {
			$this->log_warning(
				'media',
				sprintf( 'Could not determine relative path for: %s', $url )
			);
			return false;
		}

		$artifact_path = 'media/' . str_replace( '\\', '/', $relative_path );
		$file_hash     = hash_file( 'sha256', $file_path );
		if ( false !== $file_hash ) {
			$this->artifact_info[ $url ] = array( 'sha256' => $file_hash, 'bytes' => (int) filesize( $file_path ) );
		}
		if ( false !== $file_hash && isset( $this->artifacts_by_hash[ $file_hash ] ) ) {
			$this->media_artifacts[ $url ] = $this->artifacts_by_hash[ $file_hash ];
			return $this->media_artifacts[ $url ];
		}

		// Create destination path
		$dest_path = trailingslashit( $media_dir ) . $relative_path;
		$dest_dir = dirname( $dest_path );

		// Create subdirectories if needed
		if ( ! file_exists( $dest_dir ) ) {
			wp_mkdir_p( $dest_dir );
		}

		// Copy file
		$result = copy( $file_path, $dest_path );

		if ( ! $result ) {
			$this->log_error(
				'media',
				sprintf( 'Failed to copy media file: %s to %s', $file_path, $dest_path )
			);
			return false;
		}

		$this->media_artifacts[ $url ] = $artifact_path;
		if ( false !== $file_hash ) {
			$this->artifacts_by_hash[ $file_hash ] = $artifact_path;
		}

		return $artifact_path;
	}

	/**
	 * Get file path from URL.
	 *
	 * @param string $url Media URL.
	 * @return string|false File path or false on failure.
	 */
	private function get_file_path_from_url( $url ) {
		$upload_url = $this->upload_dir['baseurl'];
		$upload_path = $this->upload_dir['basedir'];

		// Normalize both to protocol-relative for comparison
		$normalized_url = preg_replace( '#^https?:#', '', $url );
		$normalized_upload_url = preg_replace( '#^https?:#', '', $upload_url );

		// Replace upload URL with upload path (protocol-agnostic)
		if ( strpos( $normalized_url, $normalized_upload_url ) === 0 ) {
			$relative = substr( $normalized_url, strlen( $normalized_upload_url ) );
			return $upload_path . $relative;
		}

		// Handle relative URLs
		if ( strpos( $url, '/wp-content/uploads/' ) !== false ) {
			$relative = substr( $url, strpos( $url, '/wp-content/uploads/' ) + strlen( '/wp-content/uploads/' ) );
			return trailingslashit( $upload_path ) . $relative;
		}

		return false;
	}

	/**
	 * Get relative upload path from URL.
	 *
	 * @param string $url Media URL.
	 * @return string|false Relative path or false on failure.
	 */
	private function get_relative_upload_path( $url ) {
		$upload_url = $this->upload_dir['baseurl'];

		// Normalize both to protocol-relative for comparison
		$normalized_url = preg_replace( '#^https?:#', '', $url );
		$normalized_upload_url = preg_replace( '#^https?:#', '', trailingslashit( $upload_url ) );

		// Get path relative to uploads directory (protocol-agnostic)
		if ( strpos( $normalized_url, $normalized_upload_url ) === 0 ) {
			return substr( $normalized_url, strlen( $normalized_upload_url ) );
		}

		// Handle relative URLs
		if ( strpos( $url, '/wp-content/uploads/' ) !== false ) {
			return substr( $url, strpos( $url, '/wp-content/uploads/' ) + strlen( '/wp-content/uploads/' ) );
		}

		return false;
	}

	/**
	 * Generate media map JSON.
	 */
	private function generate_media_map() {
		foreach ( $this->referenced_media as $media ) {
			$url = $media['url'];
			$relative_path = $this->get_relative_upload_path( $url );

			$acquisition = isset( $media['acquisition'] ) && is_array( $media['acquisition'] )
				? $media['acquisition']
				: $this->acquisition( 'bundled', 'bundle' );
			$artifact = null;
			if ( 'bundled' === $acquisition['status'] ) {
				if ( isset( $this->media_artifacts[ $url ] ) ) {
					$artifact = $this->media_artifacts[ $url ];
				} elseif ( empty( $this->export_dir ) && $relative_path ) {
					$artifact = 'media/' . str_replace( '\\', '/', $relative_path );
				} else {
					$acquisition = $this->acquisition( 'unavailable', 'operator-decision' );
				}
			}

			$map_entry = array(
				'wp_src'      => $url,
				'artifact'    => $artifact,
				'acquisition' => $acquisition,
			);

			if ( isset( $media['metadata'] ) && is_array( $media['metadata'] ) ) {
				$map_entry['metadata'] = $media['metadata'];
				if ( ! isset( $map_entry['metadata']['alt'] ) && isset( $media['alt'] ) ) {
					$map_entry['metadata']['alt'] = $media['alt'];
				}
			} elseif ( isset( $media['id'] ) && $media['id'] > 0 ) {
				$metadata = $this->get_attachment_metadata( $media['id'] );
				if ( ! empty( $metadata ) ) {
					$map_entry['metadata'] = $metadata;
				}
			}

			$map_entry['media_type'] = Moltex_Exporter_Media_Reference_Finder::media_type( $url );
			if ( 'video' === $map_entry['media_type'] ) {
				$map_entry = $this->apply_video_details( $map_entry, $relative_path );
			}
			if ( isset( $this->video_posters[ $url ] ) ) {
				$map_entry['poster'] = $this->video_posters[ $url ];
			}
			$poster_for = array_keys( $this->video_posters, $url, true );
			if ( ! empty( $poster_for ) ) {
				sort( $poster_for, SORT_STRING );
				$map_entry['poster_for'] = $poster_for;
			}
			if ( isset( $this->artifact_info[ $url ] ) && null !== $artifact ) {
				$map_entry['sha256'] = $this->artifact_info[ $url ]['sha256'];
				$map_entry['bytes']  = $this->artifact_info[ $url ]['bytes'];
			}
			$map_entry['references'] = isset( $media['references'] ) && is_array( $media['references'] ) ? $media['references'] : array();
			$map_entry = $this->apply_alt_text( $map_entry, $media );

			$this->media_map[] = $map_entry;
		}
	}

	/**
	 * Fill in video length and dimensions that WordPress did not record (an
	 * unregistered video has no attachment metadata) by reading the MP4/MOV
	 * container header of the local file. Values from WordPress win.
	 *
	 * @param array       $map_entry     Media map entry.
	 * @param string|bool $relative_path Path relative to uploads.
	 * @return array
	 */
	private function apply_video_details( array $map_entry, $relative_path ) {
		$metadata = isset( $map_entry['metadata'] ) && is_array( $map_entry['metadata'] ) ? $map_entry['metadata'] : array();
		if ( isset( $metadata['length'], $metadata['width'], $metadata['height'] ) ) {
			return $map_entry;
		}
		$candidates = array();
		if ( ! empty( $map_entry['artifact'] ) && ! empty( $this->export_dir ) ) {
			$candidates[] = trailingslashit( $this->export_dir ) . $map_entry['artifact'];
		}
		if ( $relative_path && ! empty( $this->upload_dir['basedir'] ) && false === strpos( (string) $relative_path, '..' ) ) {
			$candidates[] = trailingslashit( $this->upload_dir['basedir'] ) . ltrim( (string) $relative_path, '/' );
		}
		foreach ( $candidates as $path ) {
			if ( ! is_file( $path ) || is_link( $path ) ) {
				continue;
			}
			$probe = self::probe_mp4( $path );
			if ( null === $probe ) {
				$metadata['probe'] = 'unsupported_container';
				break;
			}
			$metadata = $metadata + $probe;
			$metadata['probe'] = 'container_header';
			break;
		}
		if ( ! empty( $metadata ) ) {
			$map_entry['metadata'] = $metadata;
		}
		return $map_entry;
	}

	/**
	 * Read duration (seconds) and frame size from an ISO-BMFF (MP4/M4V/MOV)
	 * file without loading the media data: only the moov box is read.
	 *
	 * @param string $path File path.
	 * @return array|null {length, width?, height?} or null when unreadable.
	 */
	public static function probe_mp4( $path ) {
		$handle = @fopen( $path, 'rb' );
		if ( false === $handle ) {
			return null;
		}
		$size = filesize( $path );
		$offset = 0;
		$moov = null;
		while ( $offset + 8 <= $size ) {
			fseek( $handle, $offset );
			$header = fread( $handle, 8 );
			if ( 8 !== strlen( $header ) ) {
				break;
			}
			$box = unpack( 'Nsize/a4type', $header );
			$length = $box['size'];
			$head = 8;
			if ( 1 === $length ) {
				$large = fread( $handle, 8 );
				if ( 8 !== strlen( $large ) ) {
					break;
				}
				$parts = unpack( 'Nhi/Nlo', $large );
				$length = $parts['hi'] * 4294967296 + $parts['lo'];
				$head = 16;
			} elseif ( 0 === $length ) {
				$length = $size - $offset;
			}
			if ( $length < $head ) {
				break;
			}
			if ( 'moov' === $box['type'] ) {
				if ( $length - $head <= 16777216 ) {
					$moov = (string) fread( $handle, (int) ( $length - $head ) );
				}
				break;
			}
			$offset += $length;
		}
		fclose( $handle );
		if ( null === $moov ) {
			return null;
		}
		$result = array();
		self::parse_mp4_boxes( $moov, $result, 0 );
		return isset( $result['length'] ) ? $result : null;
	}

	/**
	 * Walk moov children: mvhd gives the duration, the first tkhd with a
	 * non-zero size gives the frame dimensions.
	 */
	private static function parse_mp4_boxes( $data, array &$result, $depth ) {
		$pos = 0;
		$total = strlen( $data );
		while ( $pos + 8 <= $total ) {
			$box = unpack( 'Nsize/a4type', substr( $data, $pos, 8 ) );
			$length = $box['size'];
			$head = 8;
			if ( 1 === $length ) {
				if ( $pos + 16 > $total ) {
					return;
				}
				$parts = unpack( 'Nhi/Nlo', substr( $data, $pos + 8, 8 ) );
				$length = $parts['hi'] * 4294967296 + $parts['lo'];
				$head = 16;
			} elseif ( 0 === $length ) {
				$length = $total - $pos;
			}
			if ( $length < $head || $pos + $length > $total ) {
				return;
			}
			$body = substr( $data, $pos + $head, (int) ( $length - $head ) );
			if ( 'mvhd' === $box['type'] && strlen( $body ) >= 20 ) {
				if ( 1 === ord( $body[0] ) && strlen( $body ) >= 32 ) {
					$timescale = unpack( 'N', substr( $body, 20, 4 ) )[1];
					$parts = unpack( 'Nhi/Nlo', substr( $body, 24, 8 ) );
					$duration = $parts['hi'] * 4294967296 + $parts['lo'];
				} else {
					$timescale = unpack( 'N', substr( $body, 12, 4 ) )[1];
					$duration = unpack( 'N', substr( $body, 16, 4 ) )[1];
				}
				if ( $timescale > 0 ) {
					$result['length'] = round( $duration / $timescale, 3 );
				}
			} elseif ( 'tkhd' === $box['type'] && ! isset( $result['width'] ) && strlen( $body ) > 0 ) {
				$at = 1 === ord( $body[0] ) ? 88 : 76;
				if ( strlen( $body ) >= $at + 8 ) {
					$width = unpack( 'N', substr( $body, $at, 4 ) )[1] / 65536;
					$height = unpack( 'N', substr( $body, $at + 4, 4 ) )[1] / 65536;
					if ( $width > 0 && $height > 0 ) {
						$result['width'] = (int) round( $width );
						$result['height'] = (int) round( $height );
					}
				}
			} elseif ( 'trak' === $box['type'] && $depth < 4 ) {
				self::parse_mp4_boxes( $body, $result, $depth + 1 );
			}
			$pos += $length;
		}
	}

	/**
	 * Report alt text with its provenance (M5). The WordPress attachment alt
	 * wins; a GeoDirectory title is a fallback; an empty value is explicit.
	 *
	 * @param array $map_entry Media map entry.
	 * @param array $media     Source reference.
	 * @return array
	 */
	private function apply_alt_text( array $map_entry, array $media ) {
		$attachment_id = isset( $media['id'] ) ? absint( $media['id'] ) : 0;
		$is_geodirectory = isset( $media['metadata'] ) && is_array( $media['metadata'] ) && isset( $media['metadata']['featured'] );
		if ( $is_geodirectory || ! $attachment_id ) {
			$attachment_id = absint( attachment_url_to_postid( $map_entry['wp_src'] ) );
		}
		$wp_alt = $attachment_id ? trim( (string) get_post_meta( $attachment_id, '_wp_attachment_image_alt', true ) ) : '';
		$fallback = isset( $map_entry['metadata']['alt'] ) ? trim( (string) $map_entry['metadata']['alt'] ) : '';
		if ( ! isset( $map_entry['metadata'] ) || ! is_array( $map_entry['metadata'] ) ) {
			$map_entry['metadata'] = array();
		}
		if ( '' !== $wp_alt ) {
			$map_entry['metadata']['alt'] = $wp_alt;
			$map_entry['metadata']['alt_source'] = 'wp_attachment';
		} elseif ( '' !== $fallback ) {
			$map_entry['metadata']['alt'] = $fallback;
			$map_entry['metadata']['alt_source'] = $is_geodirectory ? 'geodir_title' : 'source_markup';
		} else {
			$map_entry['metadata']['alt'] = '';
			$map_entry['metadata']['alt_source'] = 'none';
		}
		return $map_entry;
	}

	/**
	 * Build source-acquisition metadata without prescribing a target path.
	 *
	 * @param string $status Bundled, deferred, or unavailable.
	 * @param string $method Bundle, source-fetch, or operator-decision.
	 * @return array
	 */
	private function acquisition( $status, $method ) {
		return array(
			'status'         => $status,
			'method'         => $method,
			'runtime_policy' => 'local-only',
		);
	}

	/**
	 * Determine whether the source binary belongs in the primary evidence bundle.
	 *
	 * @param array $media Media reference.
	 * @return bool
	 */
	private function should_bundle( $media ) {
		return empty( $media['acquisition']['status'] ) || 'deferred' !== $media['acquisition']['status'];
	}

	/**
	 * Get attachment metadata.
	 *
	 * @param int $attachment_id Attachment ID.
	 * @return array Attachment metadata.
	 */
	private function get_attachment_metadata( $attachment_id ) {
		$attachment = get_post( $attachment_id );
		
		if ( ! $attachment ) {
			return array();
		}

		$metadata = array(
			'id'       => $attachment_id,
			'title'    => $attachment->post_title,
			'caption'  => $attachment->post_excerpt,
			'alt'      => get_post_meta( $attachment_id, '_wp_attachment_image_alt', true ),
			'mime_type' => get_post_mime_type( $attachment_id ),
		);

		// Get attachment metadata (dimensions, file info, etc.)
		$wp_metadata = wp_get_attachment_metadata( $attachment_id );
		
		if ( ! empty( $wp_metadata ) ) {
			// Add dimensions for images
			if ( isset( $wp_metadata['width'] ) && isset( $wp_metadata['height'] ) ) {
				$metadata['width'] = $wp_metadata['width'];
				$metadata['height'] = $wp_metadata['height'];
			}

			// Video/audio details (M2).
			foreach ( array( 'length', 'length_formatted', 'fileformat', 'dataformat', 'bitrate' ) as $video_key ) {
				if ( isset( $wp_metadata[ $video_key ] ) && is_scalar( $wp_metadata[ $video_key ] ) ) {
					$metadata[ $video_key ] = $wp_metadata[ $video_key ];
				}
			}

			// Add file info
			if ( isset( $wp_metadata['file'] ) ) {
				$metadata['file'] = $wp_metadata['file'];
			}

			// Add EXIF data if available (for photos)
			if ( isset( $wp_metadata['image_meta'] ) && ! empty( $wp_metadata['image_meta'] ) ) {
				$metadata['exif'] = $this->filter_exif_data( $wp_metadata['image_meta'] );
			}

			// Add sizes info
			if ( isset( $wp_metadata['sizes'] ) && ! empty( $wp_metadata['sizes'] ) ) {
				$metadata['sizes'] = $wp_metadata['sizes'];
			}
		}

		return $metadata;
	}

	/**
	 * Filter EXIF data to remove sensitive information.
	 *
	 * @param array $exif_data EXIF data.
	 * @return array Filtered EXIF data.
	 */
	private function filter_exif_data( $exif_data ) {
		// Remove GPS coordinates and other potentially sensitive data
		$exclude_keys = array(
			'latitude',
			'longitude',
			'gps',
		);

		$filtered = array();

		foreach ( $exif_data as $key => $value ) {
			$key_lower = strtolower( $key );
			
			$is_excluded = false;
			foreach ( $exclude_keys as $exclude ) {
				if ( strpos( $key_lower, $exclude ) !== false ) {
					$is_excluded = true;
					break;
				}
			}

			if ( ! $is_excluded && ! empty( $value ) ) {
				$filtered[ $key ] = $value;
			}
		}

		return $filtered;
	}

	/**
	 * Save media map to JSON file.
	 *
	 * @return bool True on success, false on failure.
	 */
	public function save_media_map() {
		if ( empty( $this->export_dir ) ) {
			return false;
		}

		$media_dir = trailingslashit( $this->export_dir ) . 'media';
		$map_file = trailingslashit( $media_dir ) . 'media_map.json';

		$json = wp_json_encode( $this->media_map, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );

		if ( false === $json ) {
			error_log( 'Moltex Exporter: Failed to encode media map to JSON' );
			return false;
		}

		$result = file_put_contents( $map_file, $json );

		if ( false === $result ) {
			error_log( 'Moltex Exporter: Failed to write media_map.json' );
			return false;
		}

		return true;
	}
}
