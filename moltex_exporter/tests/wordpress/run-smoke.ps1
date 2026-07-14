param(
    [int]$Port = 8088,
    [switch]$KeepEnvironment
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $scriptDir 'docker-compose.yml'
$outputDir = Join-Path $scriptDir 'output'
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
    param($Session)
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

function Get-ZipCounts {
    param([string]$Path)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $names = @($archive.Entries | ForEach-Object { $_.FullName })
        return [ordered]@{
            total_entries = $names.Count
            content_json = @($names | Where-Object { $_ -match '^content/[^/]+/[^/]+\.json$' }).Count
            snapshots = @($names | Where-Object { $_ -match '^snapshots/.+\.html$' }).Count
            media_files = @($names | Where-Object { $_ -match '^media/.+' -and $_ -notmatch 'media_map\.json$' }).Count
        }
    } finally {
        $archive.Dispose()
    }
}

function Get-BundleValidation {
    param([string]$ZipName)
    $pluginRoot = '/var/www/html/wp-content/plugins/moltex-exporter'
    $containerZip = "$pluginRoot/tests/wordpress/output/$ZipName"
    $output = & docker compose -f $composeFile run --rm --entrypoint php cli `
        "$pluginRoot/tools/validate-bundle.php" $containerZip
    if ($LASTEXITCODE -ne 0) {
        throw "Standalone validation failed for $ZipName"
    }
    $validation = ($output -join "`n") | ConvertFrom-Json
    if (-not $validation.valid) {
        throw "Bundle validation rejected ${ZipName}: $($validation.errors -join ' ')"
    }
    return [ordered]@{
        valid = [bool]$validation.valid
        bundle_id = $validation.bundle_id
        complete_migration_eligible = [bool]$validation.complete_migration_eligible
        artifact_count = [int]$validation.artifact_count
    }
}

function Invoke-Export {
    param([ValidateSet('complete','discovery')][string]$Mode, $Session)
    $nonce = Get-ExporterNonce -Session $Session
    $saveBody = @{
        action = 'moltex_save_settings'
        nonce = $nonce
        export_mode = $Mode
        include_private_content = '0'
        complete_export_max_items = '5000'
        max_posts = $(if ($Mode -eq 'discovery') { '1' } else { '100' })
        max_pages = $(if ($Mode -eq 'discovery') { '1' } else { '100' })
        max_per_custom_post_type = $(if ($Mode -eq 'discovery') { '1' } else { '100' })
        include_html_snapshots = '1'
        batch_size = '50'
        cleanup_after_hours = '24'
    }
    $saved = Invoke-CurlPost -Uri "$baseUrl/wp-admin/admin-ajax.php" -Body $saveBody -Session $Session | ConvertFrom-Json
    if (-not $saved.success) { throw "Could not save $Mode settings: $($saved.data.message)" }

    $scanBody = @{ action = 'moltex_start_scan'; nonce = $nonce }
    $scan = Invoke-CurlPost -Uri "$baseUrl/wp-admin/admin-ajax.php" -Body $scanBody -Session $Session | ConvertFrom-Json
    if (-not $scan.success) { throw "$Mode export failed: $($scan.data.message)" }

    $zipPath = Join-Path $outputDir "$Mode-export.zip"
    & curl.exe -fsSL -b $Session $scan.data.download_url -o $zipPath
    if ($LASTEXITCODE -ne 0) { throw "$Mode signed ZIP download failed." }
    $counts = Get-ZipCounts -Path $zipPath
    $validation = Get-BundleValidation -ZipName (Split-Path -Leaf $zipPath)
    return [ordered]@{
        mode = $Mode
        zip = (Split-Path -Leaf $zipPath)
        bytes = (Get-Item $zipPath).Length
        scanner_errors = @($scan.data.errors).Count
        scanner_warnings = @($scan.data.warnings).Count
        counts = $counts
        validation = $validation
    }
}

if (Test-Path -LiteralPath $outputDir) {
    Remove-Item -LiteralPath $outputDir -Recurse -Force
}
New-Item -ItemType Directory -Path $outputDir | Out-Null

try {
    Invoke-Compose up -d --wait db wordpress
    Wait-ForWordPress
    Invoke-Compose run --rm --entrypoint sh cli /var/www/html/wp-content/plugins/moltex-exporter/tests/wordpress/setup-fixture.sh
    $session = New-AdminSession
    $complete = Invoke-Export -Mode complete -Session $session
    Start-Sleep -Seconds 1
    $discovery = Invoke-Export -Mode discovery -Session $session
    $comparison = [ordered]@{
        generated_at = (Get-Date).ToUniversalTime().ToString('o')
        wordpress = '7.0.1'
        php = '8.2'
        database = 'MariaDB 10.11.8'
        complete = $complete
        discovery = $discovery
    }
    $comparison | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $outputDir 'comparison.json') -Encoding UTF8
    Copy-Item -LiteralPath (Join-Path $outputDir 'complete-export.zip') -Destination (Join-Path $outputDir 'legacy-1-candidate.zip')
    $comparison | ConvertTo-Json -Depth 6
} finally {
    if (-not $KeepEnvironment) {
        Invoke-Compose down --volumes --remove-orphans
    }
}
