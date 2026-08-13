@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip show customtkinter >nul 2>&1 || python -m pip install -r requirements-client.txt
python -m client
