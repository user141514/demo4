@echo off
chcp 65001 >nul
echo ============================================
echo   领导力建模智能体 — 一键启动
echo ============================================
echo.

cd /d "%~dp0"

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [✗] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM 安装依赖
echo [1/2] 检查并安装 Python 依赖...
pip install -r backend\requirements.txt -q
if %errorlevel% neq 0 (
    echo [✗] 依赖安装失败
    pause
    exit /b 1
)

REM 启动后端
echo [2/2] 启动后端服务 http://localhost:8000 ...
echo.
start "" http://localhost:8000
python -m backend.app

pause
