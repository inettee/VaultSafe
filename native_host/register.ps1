param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-p]{32}$')]
    [string]$ExtensionId
)

$ErrorActionPreference = 'Stop'
$hostName = 'com.vaultsafe.chrome'
$project = Split-Path -Parent $PSScriptRoot
$python = (Resolve-Path -LiteralPath (Join-Path $project '.venv\Scripts\python.exe')).Path
$hostScript = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'host.py')).Path
& $python -I -c 'import win32pipe, win32security'
if ($LASTEXITCODE -ne 0) { throw 'Install requirements.txt into .venv first.' }

$directory = Join-Path $env:LOCALAPPDATA 'VaultSafe\ChromeHost'
$launcher = Join-Path $directory 'launch.cmd'
$manifestPath = Join-Path $directory "$hostName.json"
$origin = "chrome-extension://$ExtensionId/"
$registryPath = "Software\Google\Chrome\NativeMessagingHosts\$hostName"
$utf8 = [System.Text.UTF8Encoding]::new($false)

$existingKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($registryPath)
if ($null -ne $existingKey) {
    try {
        if ($existingKey.GetValue('') -ne $manifestPath) {
            throw 'The host uses a different manifest. Its registration has been kept.'
        }
    } finally {
        $existingKey.Dispose()
    }
}

New-Item -ItemType Directory -Path $directory -Force | Out-Null
$python = $python.Replace('%', '%%')
$hostScript = $hostScript.Replace('%', '%%')
$launcherText = @"
@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
"$python" -I -u "$hostScript" "$origin" %*
"@
[System.IO.File]::WriteAllText($launcher, $launcherText + "`r`n", $utf8)

$manifest = [ordered]@{
    name = $hostName
    description = 'VaultSafe Chrome demo host'
    path = $launcher
    type = 'stdio'
    allowed_origins = @($origin)
}
[System.IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json), $utf8)
$registryKey = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($registryPath)
try {
    $registryKey.SetValue('', $manifestPath, [Microsoft.Win32.RegistryValueKind]::String)
} finally {
    $registryKey.Dispose()
}
Write-Output "Registered $hostName for $origin"
