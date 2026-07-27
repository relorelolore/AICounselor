@echo off
REM scripts/run.bat - Windows startup script, CMD equivalent of run.sh
REM Usage:  scripts\run.bat  or double-click
REM Env:    HOST default 0.0.0.0,  PORT default 8000
REM
REM IMPORTANT: This file is ASCII-only on purpose. Some Windows CMD builds
REM mis-parse REM lines that contain CJK characters, treating them as
REM commands, so all comments and echo messages here are English-only.
REM Also, parens are avoided in comments because CMD counts unbalanced
REM parens when locating if-block boundaries, which can confuse the parser.

setlocal
cd /d "%~dp0\.."

if not exist data mkdir data

REM One-time migration: drop legacy per-session checkpoint DB.
REM The backend is now stateless; persistence lives in the browser's
REM localStorage. Safe to leave - acts only when the file exists.
if exist data\checkpoints.db del /f /q data\checkpoints.db

REM First run: build the index automatically.
if not exist data\chroma (
    echo [run] first run, building index...
    uv run python -m ingest
)

REM Frontend artifact check: web\dist is the Vue SPA build output,
REM committed to the repo. If missing, tell the user how to rebuild
REM instead of starting the server and serving 404s.
if not exist web\dist\index.html (
    echo [run] ERROR: web\dist\index.html is missing; frontend build artifact absent.
    echo        To rebuild, run:  cd frontend ^&^& pnpm install ^&^& pnpm build
    exit /b 1
)

if "%HOST%"=="" set HOST=0.0.0.0
if "%PORT%"=="" set PORT=8000
echo [run] starting uvicorn on %HOST%:%PORT%
uv run uvicorn app.main:app --host %HOST% --port %PORT% --reload