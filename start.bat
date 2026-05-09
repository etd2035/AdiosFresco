@echo off
cd /d "%~dp0"
echo.
echo  Mis Recetas - Planificador Semanal
echo  ====================================
echo.
echo  Instalando dependencias...
pip install flask pymupdf --quiet
echo.
echo  Iniciando servidor en http://localhost:5000
echo  (Las fotos se extraen automaticamente de los PDFs la primera vez)
echo  Presiona Ctrl+C para detener
echo.
start "" http://localhost:5000
python app.py
pause
