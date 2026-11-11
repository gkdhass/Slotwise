# Self-signed local certificate generator for Windows hosts.
# Requires OpenSSL (Git for Windows or Chocolatey). The Compose stack generates
# its own certificate in a named volume, so this is only for direct host use.
param(
    [string]$OutDir = (Join-Path $PSScriptRoot "..\nginx\certs")
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$certFile = Join-Path $OutDir "fullchain.pem"
$keyFile = Join-Path $OutDir "privkey.pem"

if ((Test-Path $certFile) -and (Test-Path $keyFile)) {
    Write-Output "Certificates already exist in $OutDir"
    exit 0
}

openssl req -x509 -nodes -newkey rsa:2048 -days 825 `
    -keyout $keyFile -out $certFile `
    -subj "/C=XX/O=Slotwise Development/CN=localhost" `
    -addext "subjectAltName=DNS:localhost,DNS:nginx,IP:127.0.0.1"

Write-Output "Generated development certificate in $OutDir"
