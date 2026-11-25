$ErrorActionPreference = 'Stop'

$scraperDir = $PSScriptRoot
$projectDir = (Resolve-Path (Join-Path $scraperDir '..')).Path
$logDir = Join-Path $scraperDir 'logs'
$null = New-Item -ItemType Directory -Path $logDir -Force
$runId = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$logPath = Join-Path $logDir "monthly-scrape-$runId.log"
$stagingPath = Join-Path $logDir "offers-staging-$runId.json"
$offersPath = Join-Path $scraperDir 'offers.json'
$transcriptStarted = $false

try {
    Start-Transcript -LiteralPath $logPath -Force | Out-Null
    $transcriptStarted = $true
    Write-Output "Monthly WUSA offers scrape started at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')."

    $keyPath = Join-Path $scraperDir '.gemini_api_key.dpapi'
    if (-not $env:GEMINI_API_KEY -and -not $env:GOOGLE_API_KEY) {
        if (Test-Path -LiteralPath $keyPath -PathType Leaf) {
            $encryptedKey = (Get-Content -LiteralPath $keyPath -Raw).Trim()
            $secureKey = ConvertTo-SecureString -String $encryptedKey
            $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
            try {
                $env:GEMINI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
            }
            finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
            }
        }
        else {
            throw 'Gemini API key is not configured. Run scraper\setup-gemini-key.ps1 first.'
        }
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $python) {
        throw 'python.exe was not found in PATH for the scheduled task. Add Python to this Windows user PATH.'
    }

    Write-Output 'Running the scraper with --classify. Linked sources are refreshed when offer content changes; cached Gemini results are reused otherwise. Nominatim geocoding is enabled by --classify.'
    Push-Location $projectDir
    try {
        & $python.Source -m scraper.wusa_scraper --classify --output $stagingPath
        $scraperExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($scraperExitCode -ne 0) {
        throw "Scraper exited with code $scraperExitCode. The existing offers.json was left unchanged."
    }

    if (-not (Test-Path -LiteralPath $stagingPath -PathType Leaf)) {
        throw 'The scraper completed without creating its staging JSON. The existing offers.json was left unchanged.'
    }
    $export = Get-Content -LiteralPath $stagingPath -Raw | ConvertFrom-Json
    if (-not $export.offers -or @($export.offers).Count -eq 0) {
        throw 'The scraper returned no offers. The existing offers.json was left unchanged.'
    }
    $failedOffers = @($export.offers | Where-Object {
        -not $_.classification -or $_.classification.status -eq 'error'
    })
    if ($failedOffers.Count -gt 0) {
        $titles = ($failedOffers | ForEach-Object { $_.title }) -join ', '
        throw "Classification failed for $($failedOffers.Count) offer(s): $titles. The existing offers.json was left unchanged."
    }

    if (Test-Path -LiteralPath $offersPath -PathType Leaf) {
        [System.IO.File]::Replace($stagingPath, $offersPath, $null)
    }
    else {
        Move-Item -LiteralPath $stagingPath -Destination $offersPath
    }
    Write-Output "Published $(@($export.offers).Count) offers to $offersPath."
    Write-Output "Monthly WUSA offers scrape finished successfully at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')."
}
catch {
    Write-Error $_.Exception.Message -ErrorAction Continue
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
        $transcriptStarted = $false
    }
    exit 1
}
finally {
    if (Test-Path -LiteralPath $stagingPath -PathType Leaf) {
        Remove-Item -LiteralPath $stagingPath -Force
    }
    Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
    }
}
