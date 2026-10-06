@echo off
title Spotify a TIDAL Pro - Migrador de Playlists
color 0b
echo ==============================================================
echo        SPOTIFY a TIDAL PRO - MIGRACION RAPIDA
echo ==============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [!] No se encontro el entorno virtual .venv
    echo Creando entorno virtual e instalando librerias...
    python -m venv .venv
    call .\.venv\Scripts\pip.exe install -r requirements.txt
)

echo [OK] Servidor iniciando en: http://127.0.0.1:8000
echo Abriendo tu navegador web...
start "" "http://127.0.0.1:8000"

.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
