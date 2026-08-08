@echo off
echo ====================================
echo Stopping ai-ops-assistant services
echo ====================================
echo.

REM Stop FastAPI service
echo [1/4] Stopping FastAPI service...
taskkill /FI "WINDOWTITLE eq ai-ops-assistant API*" /F >nul 2>&1
if errorlevel 1 (
    echo [Info] FastAPI service is not running.
) else (
    echo [OK] FastAPI service stopped.
)
echo.

REM Stop CLS MCP service
echo [2/4] Stopping CLS MCP service...
taskkill /FI "WINDOWTITLE eq CLS MCP Server*" /F >nul 2>&1
if errorlevel 1 (
    echo [Info] CLS MCP service is not running.
) else (
    echo [OK] CLS MCP service stopped.
)
echo.

REM Stop Monitor MCP service
echo [3/4] Stopping Monitor MCP service...
taskkill /FI "WINDOWTITLE eq Monitor MCP Server*" /F >nul 2>&1
if errorlevel 1 (
    echo [Info] Monitor MCP service is not running.
) else (
    echo [OK] Monitor MCP service stopped.
)
echo.

REM Stop Docker containers
echo [4/4] Stopping Milvus containers...
docker ps --format "{{.Names}}" | findstr "milvus" >nul 2>&1
if not errorlevel 1 (
    docker compose -f vector-database.yml down
    if errorlevel 1 (
        echo [Error] Docker containers could not be stopped.
    ) else (
        echo [OK] Milvus containers stopped.
    )
) else (
    echo [Info] Milvus containers are not running.
)
echo.

echo ====================================
echo All services stopped.
echo ====================================
echo.
echo Note:
echo   - To remove Docker data volumes as well, run:
echo     docker compose -f vector-database.yml down -v
echo.
pause
