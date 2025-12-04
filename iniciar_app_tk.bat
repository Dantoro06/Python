@echo off
echo ==========================================
echo     Nueve11 - App Hidding Bonus TK
echo ==========================================
echo.

REM Ir a la carpeta del proyecto
cd "C:\Users\Administrador\OneDrive - Nueve11\Documentos\nueve11\Python"

REM Permitir scripts SOLO para esta sesión
powershell -Command "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass"

REM Activar entorno virtual
call venv_riesgo\Scripts\activate

echo.
echo Ejecutando interfaz gráfica TK...
echo.

REM Ejecutar la aplicación Tkinter
python app_hidding_bonus_tk.py

echo.
echo Proceso finalizado.
pause
