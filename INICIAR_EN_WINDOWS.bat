@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creando entorno virtual...
  py -m venv .venv
  if errorlevel 1 goto :error
)
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Se creo .env. Revisa BACKUP_ADMIN_TOKEN en ese archivo.
)
echo [2/4] Instalando dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo [3/4] Iniciando BackupManager...
echo [4/4] Abre http://127.0.0.1:8000
echo Para backups completos conecta Neon en .env; el modo SQLite solo es local.
start "" "http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload
pause
exit /b 0
:error
echo Error. Revisa Python, pip y conexion de red.
pause
exit /b 1
