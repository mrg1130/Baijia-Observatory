@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "TEMP=%CD%\.cache\venv-temp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"

where python >nul 2>&1
if errorlevel 1 goto python_failed

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto venv_failed
)

".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo 正在修复虚拟环境中的 pip...
  ".venv\Scripts\python.exe" -m ensurepip --upgrade
  if errorlevel 1 goto venv_failed
)

".venv\Scripts\python.exe" -c "import fastapi, uvicorn, bs4, websocket, curl_cffi, webview" >nul 2>&1
if errorlevel 1 (
  echo 正在安装百家观测所需组件，请保持网络连接...
  ".venv\Scripts\python.exe" -m pip install -r requirements-desktop.txt
  if errorlevel 1 goto dependency_failed
)

start "" ".venv\Scripts\pythonw.exe" desktop.py
exit /b 0

:python_failed
echo 未找到 Python。请安装 Python 3.10 或更高版本，并勾选“Add Python to PATH”。
pause
exit /b 1

:venv_failed
echo 虚拟环境修复失败。请确认项目目录可写，然后重新运行此脚本。
pause
exit /b 1

:dependency_failed
echo 组件下载失败。请检查网络或代理，联网后重新运行此脚本即可继续安装。
pause
exit /b 1
