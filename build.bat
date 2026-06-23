@echo off
REM Build the Chroma Tool single-file GUI EXE.
REM
REM Output: dist\chroma_tool.exe (no signing, no console window).
REM Per-user settings/profiles are written at runtime to
REM %APPDATA%\ChromaTool, so the EXE is the only file you need to ship.

setlocal
cd /d "%~dp0"

echo [chroma_tool] Cleaning previous build artifacts...
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist

echo [chroma_tool] Running PyInstaller...
python -m PyInstaller --noconfirm --clean chroma_tool.spec
if errorlevel 1 (
    echo [chroma_tool] Build failed.
    exit /b 1
)

echo.
echo [chroma_tool] Build OK -^> dist\chroma_tool.exe
dir /b dist
endlocal
