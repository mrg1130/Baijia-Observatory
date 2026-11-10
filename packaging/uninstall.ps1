$ErrorActionPreference = 'Stop'
$appDir = [System.IO.Path]::GetFullPath($PSScriptRoot)
$expected = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\BaijiaObservatory'))
if ($appDir -ne $expected) { throw '卸载目录无效' }
Get-CimInstance Win32_Process -Filter "Name = 'BaijiaObservatory.exe'" | ForEach-Object {
    if ($_.ExecutablePath -and [System.IO.Path]::GetFullPath($_.ExecutablePath).StartsWith($expected + '\', [StringComparison]::OrdinalIgnoreCase)) { Stop-Process -Id $_.ProcessId -Force }
}
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @($shell.SpecialFolders.Item('Desktop'),$shell.SpecialFolders.Item('Programs'))) {
    Remove-Item -LiteralPath (Join-Path $folder '百家观测.lnk') -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BaijiaObservatory' -Recurse -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $appDir -Recurse -Force
