@echo off
REM ============================================================
REM start-qa-admin.cmd
REM Thin dispatcher to start-qa-admin.ps1 for PowerShell-5.1-only hosts
REM that still want a .cmd entry point (matching the start-qa-replay
REM .ps1/.cmd pair convention).
REM
REM Unlike start-qa-replay.cmd (a single `docker run` + vite launch,
REM reimplementable in pure batch), start-qa-admin's job is a multi-stage
REM docker-compose orchestration with bounded-retry Alembic migrations,
REM a generalized SQL partition/grant fixup, and a two-pass Python
REM bootstrap -- all of which need real control flow, JSON/record
REM handling and string manipulation that cmd.exe does not have. A batch
REM reimplementation would be a second, drifting copy of that logic.
REM Dispatching to the .ps1 keeps a single source of truth; cmd.exe is
REM only responsible for locating powershell.exe and forwarding args.
REM
REM USAGE: start-qa-admin.cmd [-FreshVolumes] [-DianProviderUrl ...] [-BranchUuid ...]
REM ============================================================

setlocal

set "SCRIPT_DIR=%~dp0"

where pwsh >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    pwsh -ExecutionPolicy Bypass -NoProfile -File "%SCRIPT_DIR%start-qa-admin.ps1" %*
) else (
    powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%SCRIPT_DIR%start-qa-admin.ps1" %*
)

exit /b %ERRORLEVEL%
