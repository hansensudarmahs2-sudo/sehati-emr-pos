@echo off
REM ============================================================
REM  Klinik ABC Demo — One-Click Start
REM  Double-click file ini untuk jalankan demo
REM ============================================================

title Klinik ABC Demo
cd /d "%~dp0"

echo.
echo ============================================================
echo   Klinik ABC Demo — Starting...
echo ============================================================
echo.

REM Cek Python ter-install
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python tidak ter-install di Windows.
    echo Download dari https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Install dependencies kalau belum (silent, hanya install yang belum ada)
echo Checking dependencies...
python -m pip install --quiet --disable-pip-version-check fastapi uvicorn jinja2 python-multipart 2>nul

echo.
echo Browser akan terbuka otomatis dalam 2-3 detik...
echo Untuk stop: tutup window ini atau Ctrl+C
echo.

REM Run demo
python __main__.py

pause
