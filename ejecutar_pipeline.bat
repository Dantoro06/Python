@echo off
chcp 65001 >NUL
title Nueve11 - Pipeline AML v0

echo ============================================
echo Nueve11 - Pipeline AML v0
echo ============================================
echo.

cd /d "%~dp0"

set "ACT1=%~dp0..\venv_riesgo\Scripts\activate.bat"
set "ACT2=%~dp0venv_riesgo\Scripts\activate.bat"

if exist "%ACT1%" (
  call "%ACT1%"
) else (
  if exist "%ACT2%" (
    call "%ACT2%"
  ) else (
    echo [ERROR] No se encontro el entorno virtual.
    echo        Busque: %ACT1%
    echo        o      : %ACT2%
    pause
    exit /b 1
  )
)

if not exist "%~dp0run_pipeline_test.py" (
  echo [ERROR] No existe: %~dp0run_pipeline_test.py
  pause
  exit /b 1
)

python "%~dp0run_pipeline_test.py" %*

echo.
echo ============================================
echo Pipeline finalizado.
echo Presione una tecla para salir...
echo ============================================
pause