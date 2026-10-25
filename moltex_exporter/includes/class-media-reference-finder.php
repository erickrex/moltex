<?php
/**
 * Media reference finder.
 *
 * Walks decoded WordPress values (block attributes, custom-field values,
 * theme mods, options, term meta) and HTML fragments, and returns every
 * media URL or attachment ID it can see, each with the context it was found
 * in. Pure PHP: no WordPress calls, so callers resolve IDs and URLs.
 *
 * @package Moltex_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Moltex_Exporter_Media_Reference_Finder {

	const MAX_DEPTH = 20;
	const MAX_REFERENCES = 2000;

	/** File extensions treated as media. */
	const MEDIA_EXTENSIONS = 'jpe?g|png|gif|webp|avif|svg|bmp|ico|mp4|m4v|webm|mov|ogv|mp3|m4a|ogg|wav|pdf';

	/** Video extensions, used to classify references. */
	const VIDEO_EXTENSIONS = array( 'mp4', 'm4v', 'webm', 'mov', 'ogv' );

	/**
	 * Keys whose positive integer value is an attachment ID.
	 *
	 * @var string[]
	 */
	private static $attachment_id_keys = array(
		'id', 'mediaid', 'imageid', 'image_id', 'attachment_id', 'attachmentid',
		'custom_logo', 'site_icon', 'site_logo', 'logo', 'logo_id', 'mobile_logo',
		'transparent_header_logo', 'header_sticky_logo', 'poster_id', 'video_id',
		'thumbnail_id', '_thumbnail_id', 'ct_cat_icon', 'ct_cat_default_img',
		'cat_icon', 'cat_default_img', 'default_marker_icon', 'marker_icon',
		'background_image_id', 'bgimgid', 'featured_image',
	);

	/**
	 * Find references in an arbitrary decoded value.
	 *
	 * @param mixed  $value   Value to walk.
	 * @param string $context Context label recorded on every hit (e.g. "theme_mod").
	 * @return array[] List of { kind: url|attachment_id, value, path, media_type }.
	 */
	public static function find( $value, $context = '' ) {
		$found = array();
		self::walk( $value, (string) $context, null, 0, $found );
		return self::unique( $found );
	}

	/**
	 * Find video/audio/poster URLs in an HTML fragment.
	 *
	 * @param string $html    HTML.
	 * @param string $context Context label.
	 * @return array[]
	 */
	public static function find_in_html( $html, $context = '' ) {
		$found = array();
		if ( ! is_string( $html ) || '' === $html ) {
			return $found;
		}
		$patterns = array(
			'/<(?:video|audio|source|track)\b[^>]*\ssrc\s*=\s*["\']([^"\']+)["\']/i',
			'/<video\b[^>]*\sposter\s*=\s*["\']([^"\']+)["\']/i',
			'/<(?:a|iframe|embed|object)\b[^>]*\s(?:href|src|data)\s*=\s*["\']([^"\']+\.(?:' . self::MEDIA_EXTENSIONS . ')(?:\?[^"\']*)?)["\']/i',
		);
		foreach ( $patterns as $pattern ) {
			if ( preg_match_all( $pattern, $html, $matches ) ) {
				foreach ( $matches[1] as $url ) {
					self::add_url( html_entity_decode( $url, ENT_QUOTES ), $context, $found );
				}
			}
		}
		// Block comment attributes carry IDs and URLs that never reach <img>.
		if ( preg_match_all( '/<!--\s+wp:([a-z0-9\/_-]+)\s+(\{.*?\})\s+\/?-->/s', $html, $blocks, PREG_SET_ORDER ) ) {
			foreach ( $blocks as $block ) {
				$attrs = json_decode( $block[2], true );
				if ( is_array( $attrs ) ) {
					self::walk( $attrs, $context . ':block=' . $block[1], null, 0, $found );
				}
			}
		}
		return self::unique( $found );
	}

	/**
	 * Pair each <video> with its poster image (M2).
	 *
	 * @param string $html HTML.
	 * @return array video URL => poster URL
	 */
	public static function find_video_posters( $html ) {
		$pairs = array();
		if ( ! is_string( $html ) || '' === $html || ! preg_match_all( '/<video\b([^>]*)>(.*?)<\/video>/is', $html, $videos, PREG_SET_ORDER ) ) {
			return $pairs;
		}
		foreach ( $videos as $video ) {
			if ( ! preg_match( '/\sposter\s*=\s*["\']([^"\']+)["\']/i', ' ' . $video[1], $poster ) ) {
				continue;
			}
			$sources = array();
			if ( preg_match( '/\ssrc\s*=\s*["\']([^"\']+)["\']/i', ' ' . $video[1], $src ) ) {
				$sources[] = $src[1];
			}
			if ( preg_match_all( '/<source\b[^>]*\ssrc\s*=\s*["\']([^"\']+)["\']/i', $video[2], $inner ) ) {
				$sources = array_merge( $sources, $inner[1] );
			}
			foreach ( $sources as $source ) {
				$pairs[ html_entity_decode( $source, ENT_QUOTES ) ] = html_entity_decode( $poster[1], ENT_QUOTES );
			}
		}
		return $pairs;
	}

	/**
	 * Classify a URL by extension.
	 *
	 * @param string $url URL.
	 * @return string video|audio|image|document|unknown
	 */
	public static function media_type( $url ) {
		$path = (string) parse_url( (string) $url, PHP_URL_PATH );
		$ext = strtolower( pathinfo( $path, PATHINFO_EXTENSION ) );
		if ( in_array( $ext, self::VIDEO_EXTENSIONS, true ) ) {
			return 'video';
		}
		if ( in_array( $ext, array( 'mp3', 'm4a', 'ogg', 'wav' ), true ) ) {
			return 'audio';
		}
		if ( 'pdf' === $ext ) {
			return 'document';
		}
		if ( '' !== $ext && preg_match( '/^(?:' . self::MEDIA_EXTENSIONS . ')$/', $ext ) ) {
			return 'image';
		}
		return 'unknown';
	}

	private static function walk( $value, $path, $key, $depth, array &$found ) {
		if ( $depth > self::MAX_DEPTH || count( $found ) >= self::MAX_REFERENCES ) {
			return;
		}
		if ( is_object( $value ) ) {
			$value = get_object_vars( $value );
		}
		if ( is_array( $value ) ) {
			foreach ( $value as $child_key => $child ) {
				$child_path = '' === $path ? (string) $child_key : $path . '.' . $child_key;
				self::walk( $child, $child_path, (string) $child_key, $depth + 1, $found );
			}
			return;
		}
		if ( null !== $key && self::is_attachment_id_key( $key ) && self::is_positive_int( $value ) ) {
			$found[] = array(
				'kind'       => 'attachment_id',
				'value'      => (int) $value,
				'path'       => $path,
				'media_type' => 'unknown',
			);
			return;
		}
		if ( ! is_string( $value ) || '' === $value ) {
			return;
		}
		$trimmed = trim( $value );
		if ( '' !== $trimmed && ( '{' === $trimmed[0] || '[' === $trimmed[0] ) ) {
			$decoded = json_decode( $trimmed, true );
			if ( is_array( $decoded ) ) {
				self::walk( $decoded, $path, $key, $depth + 1, $found );
				return;
			}
		}
		if ( false !== strpos( $value, '<' ) ) {
			foreach ( self::find_in_html( $value, $path ) as $hit ) {
				$found[] = $hit;
			}
			if ( preg_match_all( '/<img\b[^>]*\ssrc\s*=\s*["\']([^"\']+)["\']/i', $value, $imgs ) ) {
				foreach ( $imgs[1] as $url ) {
					self::add_url( $url, $path, $found );
				}
			}
			return;
		}
		$pattern = '#(?:https?:)?//[^\s"\'<>()|,]+?\.(?:' . self::MEDIA_EXTENSIONS . ')(?:\?[^\s"\'<>()|,]*)?(?=$|[\s"\'<>()|,])#i';
		if ( preg_match_all( $pattern, $value, $matches ) ) {
			foreach ( $matches[0] as $url ) {
				self::add_url( $url, $path, $found );
			}
			return;
		}
		// Relative uploads path such as "/wp-content/uploads/2023/01/a.jpg" or "2023/01/a.mp4".
		if ( preg_match( '#^/?(?:wp-content/uploads/)?\d{4}/\d{2}/[^\s"\'<>|]+\.(?:' . self::MEDIA_EXTENSIONS . ')$#i', $trimmed ) ) {
			self::add_url( $trimmed, $path, $found );
		}
	}

	private static function add_url( $url, $path, array &$found ) {
		$url = trim( (string) $url );
		if ( '' === $url || 0 === strpos( $url, 'data:' ) ) {
			return;
		}
		$found[] = array(
			'kind'       => 'url',
			'value'      => $url,
			'path'       => $path,
			'media_type' => self::media_type( $url ),
		);
	}

	private static function is_attachment_id_key( $key ) {
		return in_array( strtolower( (string) $key ), self::$attachment_id_keys, true );
	}

	private static function is_positive_int( $value ) {
		if ( is_int( $value ) ) {
			return $value > 0;
		}
		return is_string( $value ) && preg_match( '/^[1-9][0-9]{0,18}$/', $value );
	}

	private static function unique( array $found ) {
		$seen = array();
		$out = array();
		foreach ( $found as $hit ) {
			$id = $hit['kind'] . '|' . $hit['value'] . '|' . $hit['path'];
			if ( ! isset( $seen[ $id ] ) ) {
				$seen[ $id ] = true;
				$out[] = $hit;
			}
		}
		return $out;
	}
}
