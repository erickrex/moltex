param(
    [Parameter(Mandatory = $true)][string]$BaseUrl,
    [string[]]$Routes = @('/'),
    [string]$OutputDirectory = (Join-Path (Get-Location) 'moltex-screenshots'),
    [string]$BrowserPath
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'chromium-capture.ps1')

$report = Invoke-MoltexReferenceCapture -BaseUrl $BaseUrl -Routes $Routes -OutputDirectory $OutputDirectory -BrowserPath $BrowserPath
$reportPath = Join-Path $OutputDirectory 'capture-report.json'
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
$report | ConvertTo-Json -Depth 8
