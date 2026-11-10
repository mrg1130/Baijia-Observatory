$ErrorActionPreference = 'Stop'
$runtimeRoots = @((Join-Path ${env:ProgramFiles(x86)} 'Microsoft\EdgeWebView\Application'),(Join-Path $env:ProgramFiles 'Microsoft\EdgeWebView\Application'),(Join-Path $env:LOCALAPPDATA 'Microsoft\EdgeWebView\Application'))
$runtimeFound = $false
foreach ($runtimeRoot in $runtimeRoots) {
    if (Test-Path -LiteralPath $runtimeRoot) {
        if (Get-ChildItem -LiteralPath $runtimeRoot -Filter 'msedgewebview2.exe' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1) { $runtimeFound=$true; break }
    }
}
if (-not $runtimeFound) {
    $bootstrap = Join-Path $PSScriptRoot 'MicrosoftEdgeWebview2Setup.exe'
    Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $bootstrap
    $signature = Get-AuthenticodeSignature -LiteralPath $bootstrap
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Microsoft Corporation*') { throw 'WebView2 运行组件验证未完成' }
    $runtimeSetup = Start-Process -FilePath $bootstrap -ArgumentList @('/silent','/install') -WindowStyle Hidden -PassThru -Wait
    if ($runtimeSetup.ExitCode -notin @(0,3010)) { throw 'WebView2 运行组件安装未完成' }
}
$appDir = Join-Path $env:LOCALAPPDATA 'Programs\BaijiaObservatory'
$expected = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\BaijiaObservatory'))
if ([System.IO.Path]::GetFullPath($appDir) -ne $expected) { throw '安装目录无效' }
Get-CimInstance Win32_Process -Filter "Name = 'BaijiaObservatory.exe'" | ForEach-Object {
    if ($_.ExecutablePath -and [System.IO.Path]::GetFullPath($_.ExecutablePath).StartsWith($expected + '\', [StringComparison]::OrdinalIgnoreCase)) { Stop-Process -Id $_.ProcessId -Force }
}
New-Item -ItemType Directory -Force -Path $appDir | Out-Null
Expand-Archive -LiteralPath (Join-Path $PSScriptRoot 'payload.zip') -DestinationPath $appDir -Force
$exe = Join-Path $appDir 'BaijiaObservatory.exe'
$shell = New-Object -ComObject WScript.Shell
$desktop = $shell.SpecialFolders.Item('Desktop')
$programs = $shell.SpecialFolders.Item('Programs')
foreach ($folder in @($desktop,$programs)) {
    $shortcut = $shell.CreateShortcut((Join-Path $folder '百家观测.lnk'))
    $shortcut.TargetPath = $exe
    $shortcut.WorkingDirectory = $appDir
    $shortcut.Description = '百家号内容数据工作台'
    $shortcut.Save()
}
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BaijiaObservatory'
New-Item -Path $key -Force | Out-Null
$uninstall = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $appDir 'uninstall.ps1') + '"'
@{DisplayName='百家观测';DisplayVersion='1.1.0';Publisher='Baijia Observatory';InstallLocation=$appDir;DisplayIcon=$exe;UninstallString=$uninstall;NoModify=1;NoRepair=1} | ForEach-Object {
    foreach ($name in $_.Keys) { New-ItemProperty -Path $key -Name $name -Value $_[$name] -Force | Out-Null }
}
Start-Process -FilePath $exe -WorkingDirectory $appDir
