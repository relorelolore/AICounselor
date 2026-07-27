@echo off
REM scripts/run.bat -- Windows 启动脚本（run.sh 的 CMD 等价物）
REM 用法：scripts\run.bat （或双击）
REM 环境变量：HOST（默认 0.0.0.0）、PORT（默认 8000）

setlocal
cd /d "%~dp0\.."

if not exist data mkdir data

REM 一次性迁移：删除旧的 per-session checkpoint DB。
REM 后端已无状态，持久化完全在前端 localStorage；保留无害，仅在文件存在时清理。
if exist data\checkpoints.db del /f /q data\checkpoints.db

REM 首启：自动入索引（依赖 uv 管理的 .venv，无需手动激活）
if not exist data\chroma (
    echo [run] first run, building index...
    uv run python -m ingest
)

REM 前端产物检查：web\dist 是 Vue SPA 的构建输出（已随仓库提交）。
REM 缺失时（如手工清理过）提示如何重建，而不是启动后 404。
if not exist web\dist\index.html (
    echo [run] ERROR: web\dist\index.html 不存在（前端产物缺失）。
    echo        请执行: cd frontend ^&^& pnpm install ^&^& pnpm build
    exit /b 1
)

if "%HOST%"=="" set HOST=0.0.0.0
if "%PORT%"=="" set PORT=8000
echo [run] starting uvicorn on %HOST%:%PORT%
uv run uvicorn app.main:app --host %HOST% --port %PORT% --reload