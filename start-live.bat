@echo off
chcp 65001 > nul
title 股票即時分析
cd /d "%~dp0"
python scripts\live_server.py
pause
