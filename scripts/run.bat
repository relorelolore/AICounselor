@echo off
REM scripts/run.bat - Windows startup script, CMD equivalent of run.sh
REM
REM Usage:
REM   scripts\run.bat
REM
REM Override host / port, defaults shown:
REM   set HOST=127.0.0.1
REM   set PORT=8080
REM   scripts\run.bat
REM Or one-liner:  set HOST=127.0.0.1&& set PORT=8080&& scripts\run.bat
REM
REM Other env vars respected by the backend, see CLAUDE.md:
REM   LLAMACPP_BASE_URL, MODEL_NAME, EMBED_MODEL, DOCUMENTS_DIR, DATA_DIR,
REM   OFFLINE, CHUNK_SIZE, CHUNK_OVERLAP, RETRIEVE_K, COUNSELOR_ALLOWED_ORIGIN.
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

REM Apply host / port overrides with defaults.
if "%HOST%"=="" set HOST=0.0.0.0
if "%PORT%"=="" set PORT=8000

REM Validate PORT: digits only, in 1-65535. The for /f trick with digit
REM delimiters catches any non-numeric character; if %%c gets assigned,
REM PORT contains something other than 0-9.
set "PORT_CHECK=PASS"
for /f "delims=0123456789" %%c in ("%PORT%") do set "PORT_CHECK=FAIL"
if "%PORT_CHECK%"=="FAIL" (
    echo [run] ERROR: PORT=%PORT% is not a valid port, expected 1-65535
    exit /b 1
)
if %PORT% lss 1 (
    echo [run] ERROR: PORT=%PORT% is out of range, expected 1-65535
    exit /b 1
)
if %PORT% gtr 65535 (
    echo [run] ERROR: PORT=%PORT% is out of range, expected 1-65535
    exit /b 1
)
if "%HOST%"=="" (
    echo [run] ERROR: HOST is empty
    exit /b 1
)

echo [run] starting uvicorn on %HOST%:%PORT%
uv run uvicorn app.main:app --host %HOST% --port %PORT% --reload