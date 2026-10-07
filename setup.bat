@echo off
title ytpick - Setup
echo Installation startet. Bitte warten, das kann einige Minuten dauern ...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
