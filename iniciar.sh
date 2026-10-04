#!/usr/bin/env bash
echo "=============================================================="
echo "       SPOTIFY a TIDAL PRO - MIGRACION RAPIDA"
echo "=============================================================="
echo ""

if [ ! -f ".venv/Scripts/python.exe" ]; then
    echo "[!] Creando entorno virtual..."
    python -m venv .venv
    ./.venv/Scripts/pip install -r requirements.txt
fi

echo "[OK] Servidor iniciando en: http://127.0.0.1:8000"
# Open browser on Windows from Git Bash
explorer.exe "http://127.0.0.1:8000" 2>/dev/null || cmd.exe /c start "http://127.0.0.1:8000" 2>/dev/null &

./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
