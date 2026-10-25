<?php
use PHPUnit\Framework\TestCase;

require_once dirname( __DIR__ ) . '/includes/scanners/class-translation-scanner.php';

class TranslationFilesTest extends TestCase {
	private $dir;

	protected function setUp(): void {
		$this->dir = sys_get_temp_dir() . '/moltex-lang-' . uniqid();
		mkdir( $this->dir . '/loco/plugins', 0777, true );
		mkdir( $this->dir . '/plugins', 0777, true );
		file_put_contents( $this->dir . '/loco/plugins/geodirectory-es_ES.po', "msgid \"\"\nmsgstr \"\"\n\"Language: es_ES\\n\"\n\"X-Generator: Loco https://localise.biz/\\n\"\n\nmsgctxt \"menu\"\nmsgid \"Places\"\nmsgstr \"Lugares\"\n\nmsgid \"%d review\"\nmsgid_plural \"%d reviews\"\nmsgstr[0] \"%d reseña\"\nmsgstr[1] \"%d \"\n\"reseñas\"\n" );
		file_put_contents( $this->dir . '/plugins/akismet-es_ES.po', "msgid \"\"\nmsgstr \"\"\n\"Project-Id-Version: Plugins - Akismet - Stable\\n\"\n\nmsgid \"Spam\"\nmsgstr \"Spam\"\n" );
	}

	protected function tearDown(): void {
		foreach ( array( '/loco/plugins/geodirectory-es_ES.po', '/plugins/akismet-es_ES.po' ) as $file ) {
			@unlink( $this->dir . $file );
		}
		@rmdir( $this->dir . '/loco/plugins' );
		@rmdir( $this->dir . '/loco' );
		@rmdir( $this->dir . '/plugins' );
		@rmdir( $this->dir );
	}

	public function test_loco_overrides_are_parsed_and_stock_language_packs_skipped() {
		$files = ( new Moltex_Exporter_Translation_Scanner() )->scan_translation_files( $this->dir );

		$this->assertCount( 1, $files );
		$this->assertSame( 'loco/plugins/geodirectory-es_ES.po', $files[0]['path'] );
		$this->assertSame( 'geodirectory', $files[0]['text_domain'] );
		$this->assertSame( 'es_ES', $files[0]['locale'] );
		$this->assertSame( 'plugin', $files[0]['scope'] );
		$this->assertSame( 'loco', $files[0]['source'] );
		$this->assertSame( 2, $files[0]['entry_count'] );
		$this->assertSame( 'menu', $files[0]['entries'][0]['context'] );
		$this->assertSame( array( 'Lugares' ), $files[0]['entries'][0]['msgstr'] );
		$this->assertSame( array( '%d reseña', '%d reseñas' ), $files[0]['entries'][1]['msgstr'] );
	}

	/**
	 * Build a little-endian .mo file from original => translation pairs.
	 */
	private static function mo( array $pairs ) {
		$count = count( $pairs );
		$originals_offset = 28;
		$translations_offset = $originals_offset + 8 * $count;
		$data_offset = $translations_offset + 8 * $count;
		$tables = array( '', '' );
		$data = '';
		foreach ( array( array_keys( $pairs ), array_values( $pairs ) ) as $t => $strings ) {
			foreach ( $strings as $string ) {
				$tables[ $t ] .= pack( 'VV', strlen( $string ), $data_offset + strlen( $data ) );
				$data .= $string . "\0";
			}
		}
		return pack( 'VVVVVVV', 0x950412de, 0, $count, $originals_offset, $translations_offset, 0, 0 ) . $tables[0] . $tables[1] . $data;
	}

	public function test_compiled_only_override_is_decoded() {
		// Regression: an override shipped only as .mo used to be dropped.
		mkdir( $this->dir . '/loco/themes', 0777, true );
		$mo = $this->dir . '/loco/themes/kadence-es_ES.mo';
		file_put_contents( $mo, self::mo( array(
			''                          => "Language: es_ES\nX-Generator: Loco https://localise.biz/\n",
			"menu\x04Home"              => 'Inicio',
			"%d club\0%d clubs"         => "%d club\0%d clubes",
		) ) );
		// A .mo beside its .po is the compiled copy and must not be listed twice.
		file_put_contents( $this->dir . '/loco/plugins/geodirectory-es_ES.mo', self::mo( array( 'Places' => 'Lugares' ) ) );
		file_put_contents( $this->dir . '/loco/plugins/broken-es_ES.mo', 'not a mo file at all, definitely' );
		try {
			$files = ( new Moltex_Exporter_Translation_Scanner() )->scan_translation_files( $this->dir );
		} finally {
			@unlink( $mo );
			@unlink( $this->dir . '/loco/plugins/geodirectory-es_ES.mo' );
			@unlink( $this->dir . '/loco/plugins/broken-es_ES.mo' );
			@rmdir( $this->dir . '/loco/themes' );
		}

		$this->assertSame( array( 'loco/plugins/geodirectory-es_ES.po', 'loco/themes/kadence-es_ES.mo' ), array_column( $files, 'path' ) );
		$compiled = $files[1];
		$this->assertSame( 'mo', $compiled['format'] );
		$this->assertSame( 'theme', $compiled['scope'] );
		$this->assertSame( 'kadence', $compiled['text_domain'] );
		$this->assertSame( 'es_ES', $compiled['locale'] );
		$this->assertSame( 'es_ES', $compiled['headers']['Language'] );
		$this->assertSame( 2, $compiled['entry_count'] );
		$by_id = array_column( $compiled['entries'], null, 'msgid' );
		$this->assertSame( 'menu', $by_id['Home']['context'] );
		$this->assertSame( array( 'Inicio' ), $by_id['Home']['msgstr'] );
		$this->assertSame( '%d clubs', $by_id['%d club']['msgid_plural'] );
		$this->assertSame( array( '%d club', '%d clubes' ), $by_id['%d club']['msgstr'] );
	}
}
