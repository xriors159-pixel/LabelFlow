@echo off
setlocal
cd /d "%~dp0"

if exist "dist\LabelFlow.exe" (
  "dist\LabelFlow.exe" --uninstall-context-menu
  exit /b %errorlevel%
)

python context_menu.py uninstall
exit /b %errorlevel%
