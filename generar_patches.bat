@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File ".\generar_patches.ps1"
pause
