param(
    [switch]$KeepEnvironment
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
$composeFile = Join-Path $scriptDir 'docker-compose-release.yml'
$outputDir = Join-Path $scriptDir 'release-output'
$releasePath = Join-Path $repoRoot 'dist/moltex-exporter-1.2.0.zip'
if (-not (Test-Path -LiteralPath $releasePath)) { throw 'Build dist/moltex-exporter-1.2.0.zip before running the release smoke.' }

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker compose -f $composeFile @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed: $($Arguments -join ' ')" }
}

function Get-ImageDigest {
    param([string]$Image)
    $digests = & docker image inspect --format '{{join .RepoDigests ","}}' $Image
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect Docker image: $Image" }
    return ($digests -join '').Trim()
}

function Read-ZipJson {
    param([string]$ZipPath, [string]$EntryName)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $entry = $archive.GetEntry($EntryName)
        if (-not $entry) { throw "Release export is missing $EntryName." }
        $reader = New-Object IO.StreamReader($entry.Open())
        try { return ($reader.ReadToEnd() | ConvertFrom-Json) } finally { $reader.Dispose() }
    } finally { $archive.Dispose() }
}

function Wait-ForWordPress {
    param([string]$BaseUrl)
    $deadline = (Get-Date).AddMinutes(5)
    do {
        try { if ((Invoke-WebRequest -Uri "$BaseUrl/wp-login.php" -UseBasicParsing -TimeoutSec 10).StatusCode -eq 200) { return } } catch { Start-Sleep -Seconds 2 }
    } while ((Get-Date) -lt $deadline)
    throw "WordPress did not become ready at $BaseUrl"
}

function New-AdminSession {
    param([string]$BaseUrl, [string]$Name)
    $cookies = Join-Path $outputDir "$Name-cookies.txt"
    & curl.exe -fsS -c $cookies "$BaseUrl/wp-login.php" -o NUL
    & curl.exe -fsSL -b $cookies -c $cookies --data-urlencode 'log=moltex-admin' --data-urlencode 'pwd=moltex-fixture-password' --data-urlencode 'wp-submit=Log In' --data-urlencode "redirect_to=$BaseUrl/wp-admin/" --data-urlencode 'testcookie=1' "$BaseUrl/wp-login.php" -o NUL
    if ($LASTEXITCODE -ne 0) { throw 'WordPress administrator login failed.' }
    return $cookies
}

function Install-ReleaseUpload {
    param([string]$BaseUrl, [string]$Session)
    $page = & curl.exe -fsS -b $Session "$BaseUrl/wp-admin/plugin-install.php?tab=upload"
    $nonce = [regex]::Match(($page -join "`n"), 'name="_wpnonce" value="([^"]+)"').Groups[1].Value
    if (-not $nonce) { throw 'Could not locate the plugin upload nonce.' }
    $response = & curl.exe -fsS -b $Session -c $Session -F "_wpnonce=$nonce" -F '_wp_http_referer=/wp-admin/plugin-install.php?tab=upload' -F "pluginzip=@$releasePath;type=application/zip" -F 'install-plugin-submit=Install Now' "$BaseUrl/wp-admin/update.php?action=upload-plugin"
    if ($LASTEXITCODE -ne 0 -or ($response -join "`n") -notmatch 'Plugin installed successfully') { throw 'WordPress did not install the uploaded release ZIP.' }
    Invoke-Compose run --rm cli wp plugin activate moltex-exporter
}

function Get-ExporterNonce {
    param([string]$BaseUrl, [string]$Session)
    $page = & curl.exe -fsS -b $Session "$BaseUrl/wp-admin/admin.php?page=moltex-exporter"
    if (($page -join "`n") -notmatch 'Export preflight passed') { throw 'Installed release preflight did not pass.' }
    $nonce = [regex]::Match(($page -join "`n"), 'var moltexExporter\s*=\s*\{[^;]*"nonce":"([^"]+)"').Groups[1].Value
    if (-not $nonce) { throw 'Could not locate the exporter nonce.' }
    return $nonce
}

function Invoke-CurlPost {
    param([string]$Uri, [hashtable]$Body, [string]$Session)
    $arguments = @('-fsS', '-b', $Session, '-c', $Session)
    foreach ($item in $Body.GetEnumerator()) { $arguments += '--data-urlencode'; $arguments += "$($item.Key)=$($item.Value)" }
    $arguments += $Uri
    $content = & curl.exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "HTTP POST failed: $Uri" }
    return ($content -join "`n")
}

function Invoke-ReleaseExport {
    param([string]$BaseUrl, [string]$Session, [string]$Mode, [string]$Name)
    $nonce = Get-ExporterNonce -BaseUrl $BaseUrl -Session $Session
    $saved = Invoke-CurlPost -Uri "$BaseUrl/wp-admin/admin-ajax.php" -Session $Session -Body @{
        action='moltex_save_settings'; nonce=$nonce; export_mode=$Mode; include_private_content='0'; complete_export_max_items='5000'; max_posts='1'; max_pages='1'; max_per_custom_post_type='1'; include_html_snapshots='1'; batch_size='50'; cleanup_after_hours='24'
    } | ConvertFrom-Json
    if (-not $saved.success) { throw "Could not save $Mode settings." }
    $scan = Invoke-CurlPost -Uri "$BaseUrl/wp-admin/admin-ajax.php" -Session $Session -Body @{ action='moltex_start_scan'; nonce=$nonce } | ConvertFrom-Json
    if (-not $scan.success) { throw "$Mode export failed: $($scan.data.message)" }
    $downloadUrl = [string]($scan.data.download_url)
    if (-not $downloadUrl) { throw "$Mode export returned no signed download URL. Response: $($scan | ConvertTo-Json -Depth 6 -Compress)" }
    $zip = Join-Path $outputDir "$Name-$Mode.zip"
    & curl.exe -fsSL -b $Session $downloadUrl -o $zip
    if ($LASTEXITCODE -ne 0) { throw 'Signed release download failed.' }
    $containerZip = "/fixtures/output/$Name-$Mode.zip"
    $validationRaw = Invoke-Compose run --rm --entrypoint php cli /var/www/html/wp-content/plugins/moltex-exporter/tools/validate-bundle.php $containerZip
    $validation = ($validationRaw -join "`n") | ConvertFrom-Json
    if (-not $validation.valid) { throw "Release export validation failed: $($validation.errors -join ' ')" }
    $completeness = Read-ZipJson -ZipPath $zip -EntryName 'export_completeness.json'
    return [ordered]@{
        mode=$Mode
        bytes=(Get-Item $zip).Length
        sha256=(Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
        bundle_id=$validation.bundle_id
        eligible=[bool]$validation.complete_migration_eligible
        artifacts=[int]$validation.artifact_count
        counts=$completeness.counts
    }
}

function Register-ReleaseScreenshots {
    param([string]$BaseUrl, [string]$Session)
    $desktopId = (Invoke-Compose run --rm cli wp media import /fixtures/tests/fixtures/golden-media/lakeside-pavilion.png --title='Release desktop reference' --porcelain | Select-Object -Last 1).Trim()
    $mobileId = (Invoke-Compose run --rm cli wp media import /fixtures/tests/fixtures/golden-media/community-workshop.png --title='Release mobile reference' --porcelain | Select-Object -Last 1).Trim()
    $nonce = Get-ExporterNonce -BaseUrl $BaseUrl -Session $Session
    $references = @(
        [ordered]@{ attachment_id=[int]$desktopId; route='/'; viewport='desktop-1440x1200'; label='home' },
        [ordered]@{ attachment_id=[int]$mobileId; route='/'; viewport='mobile-500x844'; label='home' }
    ) | ConvertTo-Json -Compress
    $saved = Invoke-CurlPost -Uri "$BaseUrl/wp-admin/admin-ajax.php" -Session $Session -Body @{ action='moltex_save_reference_screenshots'; nonce=$nonce; references=$references } | ConvertFrom-Json
    if (-not $saved.success -or @($saved.data.references).Count -ne 2) { throw "Could not register release screenshots: $($saved.data.message)" }
}

function Invoke-MatrixCase {
    param([string]$Name, [string]$WordPressImage, [string]$CliImage, [int]$Port, [switch]$Discovery)
    $env:COMPOSE_PROJECT_NAME = "moltex-release-$Name"
    $env:MOLTEX_WP_IMAGE = $WordPressImage
    $env:MOLTEX_CLI_IMAGE = $CliImage
    $env:MOLTEX_SMOKE_PORT = [string]$Port
    $env:MOLTEX_SMOKE_URL = "http://localhost:$Port"
    try {
        Invoke-Compose up -d --wait db wordpress
        Wait-ForWordPress -BaseUrl $env:MOLTEX_SMOKE_URL
        Invoke-Compose run --rm cli wp core install --url=$env:MOLTEX_SMOKE_URL --title="Moltex Release $Name" --admin_user=moltex-admin --admin_password=moltex-fixture-password --admin_email=admin@example.invalid --skip-email
        $session = New-AdminSession -BaseUrl $env:MOLTEX_SMOKE_URL -Name $Name
        Install-ReleaseUpload -BaseUrl $env:MOLTEX_SMOKE_URL -Session $session
        Invoke-Compose run --rm --entrypoint sh cli /fixtures/tests/setup-fixture.sh
        if ($Discovery) { Register-ReleaseScreenshots -BaseUrl $env:MOLTEX_SMOKE_URL -Session $session }
        $complete = Invoke-ReleaseExport -BaseUrl $env:MOLTEX_SMOKE_URL -Session $session -Mode complete -Name $Name
        $discoveryResult = $null
        if ($Discovery) { $discoveryResult = Invoke-ReleaseExport -BaseUrl $env:MOLTEX_SMOKE_URL -Session $session -Mode discovery -Name $Name }
        $wordPressVersion = (Invoke-Compose run --rm cli wp core version | Select-Object -Last 1).Trim()
        $phpVersion = (Invoke-Compose exec -T wordpress php -r 'echo PHP_VERSION;' | Select-Object -Last 1).Trim()
        return [ordered]@{
            name=$Name
            wordpress_image=$WordPressImage
            wordpress_image_digest=Get-ImageDigest $WordPressImage
            cli_image=$CliImage
            cli_image_digest=Get-ImageDigest $CliImage
            wordpress_version=$wordPressVersion
            php_version=$phpVersion
            complete=$complete
            discovery=$discoveryResult
        }
    } finally {
        if (-not $KeepEnvironment) { Invoke-Compose down --volumes --remove-orphans }
    }
}

if (Test-Path -LiteralPath $outputDir) { Remove-Item -LiteralPath $outputDir -Recurse -Force }
New-Item -ItemType Directory -Path $outputDir | Out-Null
$minimum = Invoke-MatrixCase -Name minimum -WordPressImage 'wordpress:5.9-php7.4-apache' -CliImage 'wordpress:cli-php7.4' -Port 8091
$reference = Invoke-MatrixCase -Name reference -WordPressImage 'wordpress:7.0.1-php8.2-apache' -CliImage 'wordpress:cli-2.10.0-php8.2' -Port 8092 -Discovery
$report = [ordered]@{ generated_at=(Get-Date).ToUniversalTime().ToString('o'); release_sha256=(Get-FileHash $releasePath -Algorithm SHA256).Hash.ToLowerInvariant(); minimum=$minimum; reference=$reference }
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outputDir 'release-smoke-report.json') -Encoding UTF8
$report | ConvertTo-Json -Depth 8
