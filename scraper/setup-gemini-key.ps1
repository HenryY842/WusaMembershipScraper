$ErrorActionPreference = 'Stop'

$secretPath = Join-Path $PSScriptRoot '.gemini_api_key.dpapi'
$secureKey = Read-Host 'Gemini API key (input is hidden)' -AsSecureString
if ($secureKey.Length -lt 10) {
    throw 'The entered Gemini API key is empty or too short.'
}

$encryptedKey = ConvertFrom-SecureString -SecureString $secureKey
Set-Content -LiteralPath $secretPath -Value $encryptedKey -Encoding Ascii
Write-Host 'Saved the API key encrypted for this Windows account. The monthly task can decrypt it when it runs as this account.'
