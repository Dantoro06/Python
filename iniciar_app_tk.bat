@echo off
chcp 65001 >nul
title Nueve11 - Motor de Riesgo (App TK)

echo ============================================
echo Nueve11 - Herramienta de Analisis de Riesgo
echo Interfaz Grafica (TK)
echo ============================================
echo.

REM Asegurar ejecucion desde la carpeta Motor Riesgo
cd /d "%~dp0"

REM Activar entorno virtual
call ..\venv_riesgo\Scripts\activate.bat

REM Ejecutar aplicacion TK
python src\gui\app_hidding_bonus_tk.py

echo.
echo ============================================
echo La aplicacion se cerro.
echo Presione una tecla para salir...
echo ============================================
pause
