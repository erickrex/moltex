param(
    [int]$Port = 8094,
    [switch]$KeepEnvironment
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $scriptDir 'docker-compose.yml'
$outputDir = Join-Path $scriptDir 'golden-output'
$env:MOLTEX_SMOKE_PORT = [string]$Port
$baseUrl = "http://localhost:$Port"
$env:MOLTEX_SMOKE_URL = $baseUrl

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker compose -f $composeFile @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}

function Wait-ForWordPress {
    $deadline = (Get-Date).AddMinutes(5)
    do {
        try {
            $response = Invoke-WebRequest -Uri "$baseUrl/wp-login.php" -UseBasicParsing -TimeoutSec 10
            if ($response.StatusCode -eq 200) { return }
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)
    throw "WordPress did not become ready at $baseUrl"
}

function Get-LastJsonObject {
    param([object[]]$Lines)
    $line = @($Lines | Where-Object { $_ -match '^\{.*\}$' } | Select-Object -Last 1)
    if ($line.Count -ne 1) { throw 'Expected one final JSON object from the fixture command.' }
    return ($line[0] | ConvertFrom-Json)
}

function New-AdminSession {
    $cookies = Join-Path $outputDir 'admin-cookies.txt'
    $dashboard = Join-Path $outputDir 'dashboard.html'
    & curl.exe -fsS -c $cookies "$baseUrl/wp-login.php" -o NUL
    & curl.exe -fsSL -b $cookies -c $cookies `
        --data-urlencode 'log=moltex-admin' `
        --data-urlencode 'pwd=moltex-fixture-password' `
        --data-urlencode 'wp-submit=Log In' `
        --data-urlencode "redirect_to=$baseUrl/wp-admin/" `
        --data-urlencode 'testcookie=1' `
        "$baseUrl/wp-login.php" -o $dashboard
    if ($LASTEXITCODE -ne 0 -or (Get-Content -Raw $dashboard) -notmatch '<title>Dashboard') {
        throw 'WordPress administrator login failed.'
    }
    Remove-Item -LiteralPath $dashboard
    return $cookies
}

function Get-ExporterNonce {
    param([string]$Session)
    $page = & curl.exe -fsS -b $Session "$baseUrl/wp-admin/admin.php?page=moltex-exporter"
    if ($LASTEXITCODE -ne 0) { throw 'Could not load the Moltex admin page.' }
    $match = [regex]::Match(($page -join "`n"), 'var moltexExporter\s*=\s*\{[^;]*"nonce":"([^"]+)"')
    if (-not $match.Success) { throw 'Could not locate the Moltex AJAX nonce.' }
    return $match.Groups[1].Value
}

function Invoke-CurlPost {
    param([string]$Uri, [hashtable]$Body, [string]$Session)
    $arguments = @('-fsS', '-b', $Session, '-c', $Session)
    foreach ($item in $Body.GetEnumerator()) {
        $arguments += '--data-urlencode'
        $arguments += "$($item.Key)=$($item.Value)"
    }
    $arguments += $Uri
    $content = & curl.exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "HTTP POST failed: $Uri" }
    return ($content -join "`n")
}

function Get-ZipEntries {
    param([string]$Path)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        return @($archive.Entries | ForEach-Object { $_.FullName })
    } finally {
        $archive.Dispose()
    }
}

function Read-ZipJson {
    param([string]$Path, [string]$EntryName)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entry = $archive.GetEntry($EntryName)
        if (-not $entry) { throw "ZIP entry is missing: $EntryName" }
        $reader = New-Object System.IO.StreamReader($entry.Open())
        try { return ($reader.ReadToEnd() | ConvertFrom-Json) } finally { $reader.Dispose() }
    } finally {
        $archive.Dispose()
    }
}

function Assert-NoPrivateMarkers {
    param([string]$Path)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $markers = @('PRIVATE-GOLDEN-CONTENT-MUST-NOT-EXPORT', 'GOLDEN-SECRET-MUST-NOT-EXPORT', 'GOLDEN-OPTION-SECRET-MUST-NOT-EXPORT')
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        foreach ($entry in $archive.Entries) {
            if ($entry.Length -gt 5242880 -or $entry.FullName -notmatch '\.(json|html|csv|txt|sql|css|js)$') { continue }
            $reader = New-Object System.IO.StreamReader($entry.Open())
            try { $content = $reader.ReadToEnd() } finally { $reader.Dispose() }
            foreach ($marker in $markers) {
                if ($content.Contains($marker)) { throw "Private marker found in $($entry.FullName): $marker" }
            }
        }
    } finally {
        $archive.Dispose()
    }
}

if (Test-Path -LiteralPath $outputDir) {
    Remove-Item -LiteralPath $outputDir -Recurse -Force
}
New-Item -ItemType Directory -Path $outputDir | Out-Null

try {
    Invoke-Compose up -d --wait db wordpress
    Wait-ForWordPress

    $fixtureOutput = Invoke-Compose run --rm --entrypoint sh cli `
        /var/www/html/wp-content/plugins/moltex-exporter/tests/wordpress/setup-golden-fixture.sh
    $fixture = Get-LastJsonObject -Lines $fixtureOutput

    $session = New-AdminSession
    $nonce = Get-ExporterNonce -Session $session
    $saveBody = @{
        action = 'moltex_save_settings'
        nonce = $nonce
        export_mode = 'complete'
        include_private_content = '0'
        complete_export_max_items = '5000'
        max_posts = '100'
        max_pages = '100'
        max_per_custom_post_type = '100'
        include_html_snapshots = '1'
        batch_size = '50'
        cleanup_after_hours = '24'
    }
    $saved = Invoke-CurlPost -Uri "$baseUrl/wp-admin/admin-ajax.php" -Body $saveBody -Session $session | ConvertFrom-Json
    if (-not $saved.success) { throw "Could not save Golden Path settings: $($saved.data.message)" }

    $scan = Invoke-CurlPost -Uri "$baseUrl/wp-admin/admin-ajax.php" -Body @{ action = 'moltex_start_scan'; nonce = $nonce } -Session $session | ConvertFrom-Json
    if (-not $scan.success) { throw "Golden Path export failed: $($scan.data.message)" }

    $candidatePath = Join-Path $outputDir 'golden-candidate.zip'
    & curl.exe -fsSL -b $session $scan.data.download_url -o $candidatePath
    if ($LASTEXITCODE -ne 0) { throw 'Golden Path signed ZIP download failed.' }

    $pluginRoot = '/var/www/html/wp-content/plugins/moltex-exporter'
    $validationOutput = & docker compose -f $composeFile run --rm --entrypoint php cli `
        "$pluginRoot/tools/validate-bundle.php" "$pluginRoot/tests/wordpress/golden-output/golden-candidate.zip"
    if ($LASTEXITCODE -ne 0) { throw 'Standalone Golden Path validation failed.' }
    $validation = ($validationOutput -join "`n") | ConvertFrom-Json

    $entries = Get-ZipEntries -Path $candidatePath
    $bundle = Read-ZipJson -Path $candidatePath -EntryName 'bundle.json'
    $completeness = Read-ZipJson -Path $candidatePath -EntryName 'export_completeness.json'
    $mediaMap = @(Read-ZipJson -Path $candidatePath -EntryName 'media/media_map.json')
    $seo = Read-ZipJson -Path $candidatePath -EntryName 'seo_full.json'
    $integrations = Read-ZipJson -Path $candidatePath -EntryName 'integration_manifest.json'

    $archiveCounts = [ordered]@{
        content_json = @($entries | Where-Object { $_ -match '^content/[^/]+/[^/]+\.json$' }).Count
        media_files = @($entries | Where-Object { $_ -match '^media/.+' -and $_ -notmatch 'media_map\.json$' -and $_ -notmatch '/$' }).Count
        html_snapshots = @($entries | Where-Object { $_ -match '^snapshots/.+\.html$' }).Count
    }

    if (-not $validation.valid -or -not $validation.complete_migration_eligible) { throw 'Golden Path bundle is not complete-migration eligible.' }
    if ($archiveCounts.content_json -ne [int]$fixture.public_content) { throw 'WordPress/content artifact count mismatch.' }
    if ($archiveCounts.media_files -ne [int]$fixture.referenced_media -or $mediaMap.Count -ne [int]$fixture.referenced_media) { throw 'WordPress/media artifact count mismatch.' }
    if (@($seo.pages).Count -ne [int]$fixture.public_content) { throw 'Resolved SEO count mismatch.' }
    if (@($integrations.integrations | Where-Object { $_.integration_id -eq 'embed:youtube' }).Count -ne 1) { throw 'The YouTube capability evidence is missing.' }
    Assert-NoPrivateMarkers -Path $candidatePath

    $report = [ordered]@{
        generated_at = (Get-Date).ToUniversalTime().ToString('o')
        source = [ordered]@{
            wordpress = '7.0.1'
            php = '8.2'
            database = 'MariaDB 10.11.8'
            site_origin = $baseUrl
            public_content = [int]$fixture.public_content
            referenced_media = [int]$fixture.referenced_media
        }
        archive = $archiveCounts
        bundle_id = $bundle.bundle_id
        bundle_sha256 = (Get-FileHash $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant()
        complete = [bool]$bundle.complete
        mode = $bundle.mode
        privacy = $bundle.privacy
        counts = $completeness.post_types
        seo_pages = @($seo.pages).Count
        integration_ids = @($integrations.integrations | ForEach-Object { $_.integration_id })
        validation = $validation
        scanner_errors = @($scan.data.errors).Count
        scanner_warnings = @($scan.data.warnings).Count
    }
    $report | ConvertTo-Json -Depth 10 | Set-Content -Path (Join-Path $outputDir 'candidate-report.json') -Encoding UTF8
    $report | ConvertTo-Json -Depth 10
} finally {
    if (-not $KeepEnvironment) {
        Invoke-Compose down --volumes --remove-orphans
    }
}
