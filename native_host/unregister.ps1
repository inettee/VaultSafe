$ErrorActionPreference = 'Stop'
$hostName = 'com.vaultsafe.chrome'
$directory = Join-Path $env:LOCALAPPDATA 'VaultSafe\ChromeHost'
$manifestPath = Join-Path $directory "$hostName.json"
$registryKey = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$hostName"

if (Test-Path -LiteralPath $registryKey) {
    if ((Get-Item -LiteralPath $registryKey).GetValue('') -ne $manifestPath) {
        throw 'The host uses a different manifest. Its registry entry has been kept.'
    }
    Remove-Item -LiteralPath $registryKey
}
foreach ($file in @($manifestPath, (Join-Path $directory 'launch.cmd'))) {
    if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file }
}
Write-Output "Unregistered $hostName."
