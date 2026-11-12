@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\repair_login.ps1"
if errorlevel 1 (
  echo.
  echo Login repair did not complete. Review the message above.
  pause
)
