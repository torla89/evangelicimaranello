@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

echo === Pubblicazione del Gestore Canti su Cloudflare R2 ===
echo.

set "PYCMD="
where py >nul 2>nul && set "PYCMD=py"
if not defined PYCMD (
    where python >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
    if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYCMD=%LocalAppData%\Programs\Python\Python312\python.exe"
)
if not defined PYCMD (
    echo Python non trovato. Lancia prima "build_exe.bat", che lo installa da solo, poi riprova.
    pause
    exit /b 1
)

echo Installo le librerie necessarie...
"%PYCMD%" -m pip install --quiet boto3 requests
if errorlevel 1 (
    echo Installazione delle librerie non riuscita.
    pause
    exit /b 1
)

echo.
"%PYCMD%" pubblica_canti_r2.py %*
echo.
pause
