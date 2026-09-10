@echo off
chcp 65001 >nul
title Nueve11 - Dashboard de Riesgo (Streamlit)

echo ============================================
echo Nueve11 - Dashboard de Riesgo (Streamlit)
echo ============================================
echo.

REM Asegura que el BAT se ejecute desde Motor Riesgo
cd /d "%~dp0"

REM Activar entorno virtual
call .\.venv\Scripts\activate.bat

REM Ejecutar dashboard Streamlit
streamlit run dashboard_pro\Dashboard.py

echo.
echo ============================================
echo Dashboard finalizado o se cerro la ventana.
echo ============================================
pause
