@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo === Gestore Sito - build ===

rem Versione di Python usata per l'installazione automatica quando manca:
rem una versione consolidata (non l'ultimissima uscita) per essere sicuri
rem che tutte le librerie del programma (in particolare pyinstaller)
rem abbiano gia' pacchetti pronti per lei.
set "PY_VERSION=3.12.10"
set "PY_FOLDER=Python312"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-amd64.exe"
set "PY_INSTALLER_PATH=%TEMP%\gestoresito_python_installer.exe"
set "PY_PERUSER_EXE=%LocalAppData%\Programs\Python\%PY_FOLDER%\python.exe"

set "PYCMD="
where py >nul 2>nul && set "PYCMD=py"
if not defined PYCMD (
    where python >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
    if exist "%PY_PERUSER_EXE%" set "PYCMD=%PY_PERUSER_EXE%"
)

if not defined PYCMD (
    echo Python non trovato: lo scarico e lo installo automaticamente...
    echo ^(Python %PY_VERSION%, solo per l'utente corrente, nessun diritto da amministratore richiesto^)
    curl -L -o "%PY_INSTALLER_PATH%" "%PY_URL%"
    if not exist "%PY_INSTALLER_PATH%" (
        echo Download di Python non riuscito ^(nessuna connessione a Internet?^).
        echo Installa Python da https://www.python.org/downloads/ e riprova.
        if not defined BUILD_CATENA pause
        exit /b 1
    )
    echo Installazione di Python in corso ^(puo' richiedere un minuto^)...
    "%PY_INSTALLER_PATH%" /quiet InstallAllUsers=0 PrependPath=1
    del "%PY_INSTALLER_PATH%" >nul 2>nul
    if exist "%PY_PERUSER_EXE%" (
        set "PYCMD=%PY_PERUSER_EXE%"
    ) else (
        echo L'installazione automatica di Python non e' riuscita.
        echo Installa Python da https://www.python.org/downloads/ e riprova.
        if not defined BUILD_CATENA pause
        exit /b 1
    )
)
echo Uso Python: %PYCMD%

echo Installazione dipendenze...
"%PYCMD%" -m pip install --upgrade pip >nul
"%PYCMD%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Errore durante l'installazione delle dipendenze.
    if not defined BUILD_CATENA pause
    exit /b 1
)

if exist "build_tmp" rmdir /s /q "build_tmp"

echo Creazione dell'eseguibile...
"%PYCMD%" -m PyInstaller --onefile --windowed --name "Gestore Sito" --icon "%~dp0icona gestione.ico" --distpath .. --workpath build_tmp --specpath build_tmp gestore_sito.py
if errorlevel 1 (
    echo Errore durante la creazione dell'eseguibile.
    if not defined BUILD_CATENA pause
    exit /b 1
)

if exist "build_tmp" rmdir /s /q "build_tmp"

echo.
echo === Completato ===
echo "Gestore Sito.exe" si trova nella cartella "Gestore sito" ^(un livello sopra questa^).
if not defined BUILD_CATENA pause
