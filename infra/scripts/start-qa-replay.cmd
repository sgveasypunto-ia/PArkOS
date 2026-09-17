@echo off
REM ============================================================
REM start-qa-replay.cmd
REM Boot the parkos QA replay stack with hard timeouts + retries.
REM Pure cmd.exe (no PowerShell, no bash) for maximum compatibility
REM on Windows PowerShell 5.1 hosts.
REM
REM Boots: api-sucursal container (Sep 17 image) + Vite renderer
REM on apps/electron-sucursal.
REM Every network call has an explicit -m timeout. Every probe has
REM MaxRetries retries with fixed-delay between attempts.
REM
REM USAGE: start-qa-replay.cmd
REM ============================================================

setlocal enabledelayedexpansion

REM ----- Defaults (override via cmdline arg or env var) -----
set "VitePort=5173"
set "ApiPort=8100"
set "ApiTimeoutSec=30"
set "ViteTimeoutSec=15"
set "MaxRetries=3"
set "RetryDelaySec=2"
set "OperadorEmail=operador@parkos.local"
set "OperadorPassword=Pass1234word"
set "ApiImage=parkos:api-sucursal-test"
set "ApiNetwork=parkos-cloud_parkos-cloud-net"
set "BranchDbContainer=parkos-branch-db"
set "BranchUuid=360357ea-3564-4843-a680-7e821dd26383"
set "ApiContainerName=parkos-api-sucursal-run"
set "ViteWorkDir=E:\easypunto_parkos\apps\electron-sucursal"
set "SecretsDir=E:\easypunto_parkos\infra\deploy\secrets"

REM ----- Helpers -----
set "TS=start-qa-replay %date% %time:~0,8%"
echo %TS% [STEP] Pre-flight checks

REM --- Docker daemon reachable ---
docker version >nul 2>&1
if errorlevel 1 (
    echo %TS% [ERR] Docker daemon unreachable. Start Docker Desktop and retry.
    exit /b 1
)
echo %TS% [OK]   Docker daemon reachable

REM ----- Backend -----
echo %TS% [STEP] Backend (api-sucursal on :%ApiPort%)

REM Idempotent: prune leftover standalone container
docker ps -a --filter "name=%ApiContainerName%" --format "{{.Names}}" 2^>nul | findstr /R /C:"%ApiContainerName%" >nul
if not errorlevel 1 (
    echo %TS% [STEP] Removing leftover %ApiContainerName%
    docker stop %ApiContainerName% >nul 2>&1
    docker rm %ApiContainerName% >nul 2>&1
)

REM Probe: check if a running container named %ApiContainerName% exists.
REM (More reliable than Test-NetConnection because docker port-forward
REM zombies can fool a raw socket probe.)
docker ps --filter "name=%ApiContainerName%" --format "{{.Names}}" 2>nul | findstr /R /C:"%ApiContainerName%" >nul
if errorlevel 1 goto :StartContainer
echo %TS% [OK]   Container %ApiContainerName% already running -- reusing it
goto :ContainerReady

:StartContainer
echo %TS% [STEP] Starting %ApiContainerName% (image=%ApiImage%, network=%ApiNetwork%)
docker run -d --name %ApiContainerName% --network %ApiNetwork% -p %ApiPort%:8000 -e PARKOS_DEPLOY=branch -e PARKOS_SYNC_ENGINE=catalog_branch -e PARKOS_SUCURSAL_UUID=%BranchUuid% -e DATABASE_URL=postgresql+psycopg://parkos:parkos@%BranchDbContainer%:5432/parkos -e PARKOS_CLOUD_API_URL=http://api-admin:8000 -e PARKOS_JWT_KEY_PATH=/var/run/parkos/jwt_private.pem -e PARKOS_SYNC_JWT_PATH=/var/run/parkos/sync.jwt -v "%SecretsDir%:/var/run/parkos:ro" %ApiImage% python -m uvicorn parkos_core.api.app_factory:create_app --factory --host 0.0.0.0 --port 8000
if errorlevel 1 (
    echo %TS% [ERR] docker run failed
    exit /b 2
)
echo %TS% [OK]   Container started
REM uvicorn takes ~15-30s to bind inside the container. Wait generously.
echo %TS% [STEP] Waiting 15s for uvicorn boot...
timeout /t 15 /nobreak >nul

:ContainerReady

REM --- /health probe with retries ---
echo %TS% [STEP] Probing /health on :%ApiPort%
set "healthOk=0"
set /a "attempt=0"
:HealthLoop
set /a "attempt+=1"
curl -sS -m %ApiTimeoutSec% -o nul -w "%%{http_code}" "http://127.0.0.1:%ApiPort%/health" 2>nul | findstr /R "200" >nul
if not errorlevel 1 (
    echo %TS% [OK]   /health 200 OK after %attempt% attempt^(s^)
    set "healthOk=1"
    goto :HealthDone
)
echo %TS% [WARN] Health attempt %attempt%/%MaxRetries% failed
if %attempt% geq %MaxRetries% goto :HealthDone
echo %TS% [WARN] Waiting %RetryDelaySec%s before retry
timeout /t %RetryDelaySec% /nobreak >nul
goto :HealthLoop
:HealthDone
if %healthOk% neq 1 (
    echo %TS% [ERR]  api-sucursal /health failed after %MaxRetries% attempts
    exit /b 2
)

REM ----- Vite renderer -----
echo %TS% [STEP] Vite renderer on :%VitePort%

REM Free the port if stale process owns it
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%VitePort% " ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

set "outLog=%TEMP%\vite-qa-replay.out"
set "errLog=%TEMP%\vite-qa-replay.err"

REM cd into vite workdir and start detached (start /b true background)
echo %TS% [STEP] Starting Vite detached (workdir=%ViteWorkDir%)
cd /D "%ViteWorkDir%"
start "" /B cmd /c "node_modules\.bin\vite.cmd --port %VitePort% --host 127.0.0.1 --force > %outLog% 2> %errLog%"
cd /D "%~dp0"

echo %TS% [OK]   Vite detached (logs: %outLog% + %errLog%)

REM --- Vite probe with retries ---
echo %TS% [STEP] Probing :%VitePort%
set "viteOk=0"
set /a "viteAttempt=0"
:ViteLoop
set /a "viteAttempt+=1"
curl -sS -m %ViteTimeoutSec% -o nul -w "%%{http_code}" "http://127.0.0.1:%VitePort%" 2>nul | findstr /R "200 304" >nul
if not errorlevel 1 (
    echo %TS% [OK]   Vite responding on :%VitePort% after %viteAttempt% attempt^(s^)
    set "viteOk=1"
    goto :ViteDone
)
echo %TS% [WARN] Vite attempt %viteAttempt%/%MaxRetries% not ready
if %viteAttempt% geq %MaxRetries% goto :ViteDone
echo %TS% [WARN] Waiting %RetryDelaySec%s before retry
timeout /t %RetryDelaySec% /nobreak >nul
goto :ViteLoop
:ViteDone
if %viteOk% neq 1 (
    echo %TS% [ERR]  Vite never became ready after %MaxRetries% attempts. See %errLog%
    exit /b 3
)

REM ----- Smoke login -----
echo %TS% [STEP] Smoke login as %OperadorEmail%
REM Construct JSON body inline (no for /f tokenisation; cmd strips
REM the colons if we pipe through a subshell).
set "loginBody={"email":"%OperadorEmail%","password":"%OperadorPassword%"}"
curl -sS -m 10 -X POST -H "Content-Type: application/json" -d "%loginBody%" -o nul -w "smoke_login_status=%%{http_code}" "http://127.0.0.1:%ApiPort%/api/v1/auth/login" >nul 2>&1
echo %TS% [INFO] login probe completed
REM Re-run to capture the exit code (last curl call's exitcode is what we check)
curl -sS -m 10 -X POST -H "Content-Type: application/json" -d "%loginBody%" -o nul "http://127.0.0.1:%ApiPort%/api/v1/auth/login" >nul 2>&1
if errorlevel 1 (
    echo %TS% [WARN] Login probe failed (curl errorlevel %errorlevel%)
) else (
    echo %TS% [OK]   Login probe sent
)

REM ----- Output -----
echo.
echo ============================================================
echo   PARKOS QA REPLAY STACK READY
echo ============================================================
echo.
echo   Vite renderer:    http://127.0.0.1:%VitePort%
echo   api-sucursal:     http://127.0.0.1:%ApiPort%
echo   Operador login:   %OperadorEmail% / %OperadorPassword%
echo.
echo Next step (chrome-devtools MCP):
echo   navigate_page pageId=1 url="http://127.0.0.1:%VitePort%" timeout=30000
echo.
echo Logs:
echo   Vite stdout:  %outLog%
echo   Vite stderr:  %errLog%
echo.
echo %TS% [OK]   Done.
endlocal
