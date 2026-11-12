param(
    [string]$DataDir = (Join-Path $env:LOCALAPPDATA 'BaijiaObservatory'),
    [string]$AppPath = (Join-Path $env:LOCALAPPDATA 'Programs\BaijiaObservatory\BaijiaObservatory.exe'),
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'

try {
    if (Get-Process -Name 'BaijiaObservatory' -ErrorAction SilentlyContinue) {
        throw '请先关闭“百家观测”，再重新运行此修复工具。'
    }

    $data = [System.IO.Path]::GetFullPath($DataDir)
    $cache = [System.IO.Path]::GetFullPath((Join-Path $data 'webview'))
    if ([System.IO.Path]::GetDirectoryName($cache) -ne $data) {
        throw '登录缓存路径校验失败，未执行任何操作。'
    }

    if (Test-Path -LiteralPath $cache) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $backup = [System.IO.Path]::GetFullPath((Join-Path $data "webview.backup-$stamp"))
        if ([System.IO.Path]::GetDirectoryName($backup) -ne $data -or (Test-Path -LiteralPath $backup)) {
            throw '登录缓存备份路径校验失败，未执行任何操作。'
        }
        Move-Item -LiteralPath $cache -Destination $backup
        Write-Host "旧登录缓存已备份到：$backup"
    } else {
        Write-Host '没有发现旧登录缓存，将直接重新打开软件。'
    }

    $database = Join-Path $data 'studio.sqlite3'
    if (Test-Path -LiteralPath $database) {
        Write-Host '作品数据库保持不变。'
    }

    if (-not $NoLaunch) {
        if (-not (Test-Path -LiteralPath $AppPath)) {
            throw "未找到已安装的软件：$AppPath"
        }
        Start-Process -FilePath $AppPath
        Write-Host '百家观测已重新打开，请在“连接与设置”中重新登录百度。'
    }
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
