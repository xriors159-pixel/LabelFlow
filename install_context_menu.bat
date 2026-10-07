@echo off
setlocal
cd /d "%~dp0"

if exist "dist\LabelFlow.exe" goto install

echo LabelFlow.exe not found. Building it with PyInstaller...
python -m pip install --disable-pip-version-check pyinstaller
if errorlevel 1 exit /b 1
python -m PyInstaller --noconfirm --clean LabelFlow.spec
if errorlevel 1 exit /b 1

:install
if not exist "dist\LabelFlow.exe" (
  echo Build failed: dist\LabelFlow.exe is missing.
  exit /b 1
)
"dist\LabelFlow.exe" --install-context-menu
exit /b %errorlevel%
