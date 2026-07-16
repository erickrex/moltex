param(
    [string]$Treeish = 'HEAD'
)

$ErrorActionPreference = 'Stop'
$pluginRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $pluginRoot
$dist = Join-Path $repoRoot 'dist'

if ($Treeish -eq 'HEAD' -and (git -C $repoRoot status --porcelain)) {
    throw 'Release builds from HEAD require a clean working tree.'
}
$commit = (git -C $repoRoot rev-parse "$Treeish^{commit}").Trim()
if ($LASTEXITCODE -ne 0) { throw "Could not resolve release treeish: $Treeish" }
$pluginSource = git -C $repoRoot show "$Treeish`:moltex_exporter/moltex_exporter.php"
if ($LASTEXITCODE -ne 0) { throw 'Could not read the plugin header from the release tree.' }
$readmeSource = git -C $repoRoot show "$Treeish`:moltex_exporter/readme.txt"
if ($LASTEXITCODE -ne 0) { throw 'Could not read readme.txt from the release tree.' }
$exporterSource = git -C $repoRoot show "$Treeish`:moltex_exporter/includes/class-exporter.php"
if ($LASTEXITCODE -ne 0) { throw 'Could not read the exporter class from the release tree.' }
$rulesSource = git -C $repoRoot show "$Treeish`:moltex_exporter/release-files.json"
if ($LASTEXITCODE -ne 0) { throw 'Could not read release-files.json from the release tree.' }
$headerVersion = [regex]::Match(($pluginSource -join "`n"), '(?m)^ \* Version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$').Groups[1].Value
$constantVersion = [regex]::Match(($pluginSource -join "`n"), "MOLTEX_EXPORTER_VERSION',\s*'([^']+)'" ).Groups[1].Value
$stableVersion = [regex]::Match(($readmeSource -join "`n"), '(?m)^Stable tag:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$').Groups[1].Value
$fallbackVersion = [regex]::Match(($exporterSource -join "`n"), "'exporter_version'\s*=>[^\n]+:\s*'([^']+)'" ).Groups[1].Value
if (-not $headerVersion -or @($constantVersion, $stableVersion, $fallbackVersion) -contains '') {
    throw 'One or more release version declarations are missing.'
}
if (@($constantVersion, $stableVersion, $fallbackVersion) | Where-Object { $_ -ne $headerVersion }) {
    throw 'Plugin header, runtime, readme, and exporter fallback versions do not match.'
}

New-Item -ItemType Directory -Path $dist -Force | Out-Null
$zipName = "moltex-exporter-$headerVersion.zip"
$zipPath = Join-Path $dist $zipName
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
& git -C $repoRoot archive --format=zip --prefix='moltex-exporter/' --output=$zipPath "$Treeish`:moltex_exporter"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $zipPath)) { throw 'git archive failed.' }

$rules = ($rulesSource -join "`n") | ConvertFrom-Json
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::Open($zipPath, [IO.Compression.ZipArchiveMode]::Update)
try {
    $normalizedTimestamp = [DateTimeOffset]::new(2000, 1, 1, 0, 0, 0, [TimeSpan]::Zero)
    foreach ($entry in $archive.Entries) { $entry.LastWriteTime = $normalizedTimestamp }
} finally { $archive.Dispose() }

$archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $entries = @($archive.Entries | Where-Object { $_.FullName -notmatch '/$' } | ForEach-Object { $_.FullName })
} finally { $archive.Dispose() }
$relative = @($entries | ForEach-Object {
    if ($_ -notmatch '^moltex-exporter/') { throw "Release entry is outside the plugin root: $_" }
    $_.Substring('moltex-exporter/'.Length)
})
foreach ($path in $relative) {
    if ($rules.forbidden_files -contains $path) { throw "Forbidden development file in release ZIP: $path" }
    foreach ($prefix in $rules.forbidden_prefixes) {
        if ($path.StartsWith($prefix, [StringComparison]::Ordinal)) { throw "Forbidden development path in release ZIP: $path" }
    }
    $allowed = $rules.allowed_files -contains $path
    if (-not $allowed) {
        foreach ($prefix in $rules.allowed_prefixes) {
            if ($path.StartsWith($prefix, [StringComparison]::Ordinal)) { $allowed = $true; break }
        }
    }
    if (-not $allowed) { throw "Unexpected release ZIP entry: $path" }
}
foreach ($required in $rules.required_files) {
    if ($relative -notcontains $required) { throw "Required release file is missing: $required" }
}

$hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$shaPath = "$zipPath.sha256"
"$hash  $zipName" | Set-Content -LiteralPath $shaPath -Encoding ASCII
$receipt = [ordered]@{
    version = $headerVersion
    treeish = $Treeish
    commit = $commit
    zip = $zipName
    sha256 = $hash
    bytes = (Get-Item -LiteralPath $zipPath).Length
    file_count = $relative.Count
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
}
$receipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dist 'release-receipt.json') -Encoding UTF8
$receipt | ConvertTo-Json
