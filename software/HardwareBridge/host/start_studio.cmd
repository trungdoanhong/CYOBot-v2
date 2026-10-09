@echo off
cd /d "%~dp0"
python -B studio.py --open
if errorlevel 1 pause
