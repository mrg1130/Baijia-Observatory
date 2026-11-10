@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, bs4, websocket, curl_cffi, webview" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements-desktop.txt
  if errorlevel 1 goto failed
)
start "" ".venv\Scripts\pythonw.exe" desktop.py
exit /b 0
:failed
echo 启动失败，请检查 Python 3.10+、网络或端口 8765 是否被占用。
pause
exit /b 1
