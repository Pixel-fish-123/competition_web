@echo off
rem ASCII-only launcher (no Chinese - avoids GBK/UTF-8 codepage issues)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_server.ps1"
