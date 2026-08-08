@echo off
setlocal EnableExtensions

echo ====================================
echo Starting ai-ops-assistant services
echo ====================================
echo.

cd /d "%~dp0"

REM Prefer an existing project venv (Python 3.11-3.13). Avoid system Python 3.14.
echo [1/6] Checking Python environment...
set "PYTHON_CMD="
if exist ".venv\Scripts\python.exe" (
    for /f "tokens=2 delims= " %%v in ('.venv\Scripts\python.exe -c "import sys; print(sys.version.split()[0])"') do set "VENV_PY_VER=%%v"
    echo [Info] Found .venv Python %VENV_PY_VER%
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else (
    echo [Info] .venv not found, will create one.
)

if not defined PYTHON_CMD (
    where uv >nul 2>&1
    if not errorlevel 1 (
        echo [2/6] Creating venv with uv ^(Python 3.13^)...
        uv sync --python 3.13
        if errorlevel 1 (
            echo [Error] uv sync failed.
            pause
            exit /b 1
        )
        set "PYTHON_CMD=.venv\Scripts\python.exe"
    ) else (
        echo [2/6] Creating venv with python -m venv...
        where py >nul 2>&1
        if not errorlevel 1 (
            py -3.13 -m venv .venv 2>nul
            if errorlevel 1 py -3.12 -m venv .venv 2>nul
            if errorlevel 1 py -3.11 -m venv .venv
        ) else (
            python -m venv .venv
        )
        if errorlevel 1 (
            echo [Error] Could not create .venv. Install Python 3.11-3.13.
            pause
            exit /b 1
        )
        .venv\Scripts\python.exe -m pip install -U pip
        .venv\Scripts\python.exe -m pip install -e .
        if errorlevel 1 (
            echo [Error] Dependency installation failed.
            echo [Hint] System Python 3.14 is not supported. Use 3.11-3.13.
            pause
            exit /b 1
        )
        set "PYTHON_CMD=.venv\Scripts\python.exe"
    )
) else (
    echo [2/6] Using existing virtual environment.
)

if not exist "%PYTHON_CMD%" (
    echo [Error] Python executable not found: %PYTHON_CMD%
    pause
    exit /b 1
)
echo [OK] Virtual environment is ready: %PYTHON_CMD%
echo.

REM Start the vector database if it is not already running.
echo [3/6] Starting Milvus vector database...
docker ps --format "{{.Names}}" | findstr /X "milvus-standalone" >nul 2>&1
if errorlevel 1 (
    docker compose -f vector-database.yml up -d
    if errorlevel 1 (
        echo [Error] Docker startup failed. Ensure Docker Desktop is running.
        pause
        exit /b 1
    )
    echo [Info] Waiting 10 seconds for Milvus...
    timeout /t 10 /nobreak >nul
) else (
    echo [Info] Milvus is already running.
)
echo [OK] Vector database is ready.
echo.

REM Start MCP servers. Default: local mock CLS (mcp_servers/cls_server.py, :8383).
REM To use the real Tencent CLS MCP instead, edit .env (MCP_CLS_URL=http://localhost:3000/sse)
REM and start it manually (npx -y cls-mcp-server@latest) before this script.
echo [4/6] Starting CLS MCP server (local mock :8383)...
start "CLS MCP Server" /min "%PYTHON_CMD%" "%~dp0mcp_servers\cls_server.py"
timeout /t 3 /nobreak >nul

echo [5/6] Starting Monitor MCP server (:8384)...
start "Monitor MCP Server" /min "%PYTHON_CMD%" mcp_servers\monitor_server.py
timeout /t 2 /nobreak >nul

REM Start the FastAPI application.
echo [6/6] Starting FastAPI service...
netstat -ano | findstr /R /C:":9900 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [Error] Port 9900 is already occupied by an existing API process.
    echo [Hint] Stop the old ai-ops-assistant API first, then run this script again.
    pause
    exit /b 1
)
start "ai-ops-assistant API" "%PYTHON_CMD%" -m uvicorn app.main:app --host 0.0.0.0 --port 9900
echo [Info] Waiting 15 seconds for the API...
timeout /t 15 /nobreak >nul

curl -s http://localhost:9900/health >nul 2>&1
if errorlevel 1 (
    echo [Warning] The API may still be starting. Check logs\app_*.log.
) else (
    echo [OK] FastAPI service is running.
    echo [Info] Uploading Markdown files from aiops-docs...
    for %%f in (aiops-docs\*.md) do (
        echo   Uploading %%~nxf
        curl -s -X POST http://localhost:9900/api/upload -F "file=@%%f" >nul 2>&1
    )
    echo [OK] Knowledge files uploaded.
)

echo.
echo ====================================
echo Startup command completed.
echo Web UI:    http://localhost:9900
echo API docs:  http://localhost:9900/docs
echo CLS MCP:   http://localhost:8383/mcp
echo Monitor:   http://localhost:8384/mcp
echo Stop:      stop-windows.bat
echo ====================================
pause
endlocal
