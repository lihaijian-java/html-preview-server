@echo off
chcp 65001 >nul
title HTML Preview Server

cd /d "%~dp0"

echo 正在检查虚拟环境...
if not exist "venv" (
    echo 首次运行，正在创建虚拟环境...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo 正在安装依赖...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo 启动服务器...
python main.py
pause
