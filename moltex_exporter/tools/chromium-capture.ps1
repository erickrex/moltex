function Resolve-MoltexChromiumBrowser {
    param([string]$BrowserPath)

    if ($BrowserPath) {
        $candidates = @($BrowserPath)
    } else {
        $candidates = @(
            "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
            "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
            "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
            "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
        )
        foreach ($commandName in @('chrome.exe', 'msedge.exe')) {
            $command = Get-Command $commandName -ErrorAction SilentlyContinue
            if ($command) { $candidates += $command.Source }
        }
    }

    foreach ($candidate in @($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $resolved = (Resolve-Path -LiteralPath $candidate).Path
        $metadata = [Diagnostics.FileVersionInfo]::GetVersionInfo($resolved)
        $leafName = [IO.Path]::GetFileName($resolved)
        $name = if ($leafName -ieq 'chrome.exe') {
            'Google Chrome'
        } elseif ($leafName -ieq 'msedge.exe') {
            'Microsoft Edge'
        } elseif ($metadata.ProductName) {
            $metadata.ProductName
        } else {
            'Chromium'
        }
        $version = if ($metadata.ProductVersion) { $metadata.ProductVersion } else { $metadata.FileVersion }
        if (-not $version) { $version = 'unknown' }
        return [pscustomobject][ordered]@{ Name = $name; Version = $version; Path = $resolved }
    }

    if ($BrowserPath) { throw "The requested Chromium browser does not exist: $BrowserPath" }
    throw 'Google Chrome or Microsoft Edge is required. Use -BrowserPath to select another Chromium installation.'
}

function Invoke-MoltexReferenceCapture {
    param(
        [Parameter(Mandatory = $true)][string]$BaseUrl,
        [string[]]$Routes = @('/'),
        [Parameter(Mandatory = $true)][string]$OutputDirectory,
        [string]$BrowserPath
    )

    $origin = $BaseUrl.TrimEnd('/')
    if ($origin -notmatch '^https?://') { throw 'BaseUrl must use http or https.' }
    $browser = Resolve-MoltexChromiumBrowser -BrowserPath $BrowserPath
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $profileRoot = Join-Path $OutputDirectory '.browser-profiles'
    New-Item -ItemType Directory -Path $profileRoot -Force | Out-Null
    $viewports = @(
        @{ Name = 'desktop-1440x1200'; Size = '1440,1200'; Suffix = 'desktop' },
        # Chromium headless enforces a 500 CSS-pixel minimum layout width.
        @{ Name = 'mobile-500x844'; Size = '500,844'; Suffix = 'mobile' }
    )
    $captures = @()

    try {
        foreach ($route in $Routes) {
            if ($route -notmatch '^/(?!/)') { throw "Route must be site-relative: $route" }
            $label = if ($route -eq '/') { 'home' } else { ($route.Trim('/') -replace '[^a-zA-Z0-9_-]', '-') }
            if (-not $label) { $label = 'page' }
            foreach ($viewport in $viewports) {
                $name = "$label-$($viewport.Suffix).png"
                $path = Join-Path $OutputDirectory $name
                $profile = Join-Path $profileRoot "$label-$($viewport.Suffix)"
                & $browser.Path --headless --disable-gpu --hide-scrollbars `
                    --run-all-compositor-stages-before-draw --virtual-time-budget=5000 `
                    "--user-data-dir=$profile" "--window-size=$($viewport.Size)" `
                    "--screenshot=$path" "$origin$route" | Out-Host
                $deadline = (Get-Date).AddSeconds(15)
                while ((-not (Test-Path -LiteralPath $path) -or (Get-Item -LiteralPath $path -ErrorAction SilentlyContinue).Length -lt 10000) -and (Get-Date) -lt $deadline) {
                    Start-Sleep -Milliseconds 250
                }
                if (-not (Test-Path -LiteralPath $path) -or (Get-Item -LiteralPath $path).Length -lt 10000) {
                    throw "Screenshot capture failed: $name"
                }
                $captures += [ordered]@{
                    file = $name
                    route = $route
                    viewport = $viewport.Name
                    bytes = (Get-Item -LiteralPath $path).Length
                    sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
                }
            }
        }
    } finally {
        Start-Sleep -Milliseconds 500
        Remove-Item -LiteralPath $profileRoot -Recurse -Force -ErrorAction SilentlyContinue
    }

    return [ordered]@{
        generated_at = (Get-Date).ToUniversalTime().ToString('o')
        base_url = $origin
        browser = [ordered]@{ name = $browser.Name; version = $browser.Version; engine = 'Chromium' }
        screenshots = $captures
    }
}
