<?php
/**
 * Plugin Name: Golden Path Seasonal Schedule
 * Description: Fixture shortcode representing custom source behavior needing disposition.
 * Version: 1.0.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

add_shortcode(
	'lake_schedule',
	function( $attributes ) {
		$attributes = shortcode_atts( array( 'season' => 'current' ), $attributes );
		return sprintf(
			'<section class="seasonal-schedule" data-season="%s"><h2>Seasonal opening</h2><p>Wednesday to Sunday, 10:00–17:00.</p></section>',
			esc_attr( $attributes['season'] )
		);
	}
);
