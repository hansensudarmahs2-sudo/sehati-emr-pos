@echo off
REM ============================================================
REM  Klinik ABC Demo — Auto Build Script
REM  Double-click this file di Windows Explorer untuk build EXE
REM ============================================================

echo.
echo ============================================================
echo   Klinik ABC Demo — Build EXE Auto-Script
echo ============================================================
echo.

REM Cek Python ter-install
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python tidak ter-install di Windows.
    echo.
    echo Download Python dari https://www.python.org/downloads/
    echo PENTING: Centang "Add Python to PATH" saat install.
    echo.
    pause
    exit /b 1
)

echo [1/3] Python detected:
python --version
echo.

echo [2/3] Installing dependencies (mungkin perlu 1-2 menit)...
pip install --quiet fastapi uvicorn jinja2 pyinstaller python-multipart
if errorlevel 1 (
    echo [ERROR] Gagal install dependencies.
    pause
    exit /b 1
)
echo Dependencies installed.
echo.

echo [3/3] Building EXE (perlu 3-5 menit)...
pyinstaller --clean build_exe.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller gagal build.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   BUILD SELESAI!
echo ============================================================
echo.
echo File EXE: dist\KlinikABC_Demo.exe
echo.
echo Untuk test: double-click KlinikABC_Demo.exe di folder dist\
echo Untuk share: kirim 1 file dist\KlinikABC_Demo.exe via WeTransfer / USB / dll.
echo.
pause
