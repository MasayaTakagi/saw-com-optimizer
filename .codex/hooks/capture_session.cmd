@echo off
setlocal
set "PROJECT_ROOT=%~dp0..\.."
set "HOOK_SCRIPT=%~dp0capture_session.py"

if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    "%PROJECT_ROOT%\.venv\Scripts\python.exe" "%HOOK_SCRIPT%"
    exit /b %ERRORLEVEL%
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%HOOK_SCRIPT%"
    exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if not errorlevel 1 (
    python "%HOOK_SCRIPT%"
    exit /b %ERRORLEVEL%
)

>&2 echo No Python interpreter found for Codex session capture.
exit /b 1
