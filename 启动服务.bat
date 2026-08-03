@echo off
rem 一键启动 萌新杯音游比赛网站（双击本文件即可）
title 萌新杯音游比赛网站 - 一键启动
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
pause
