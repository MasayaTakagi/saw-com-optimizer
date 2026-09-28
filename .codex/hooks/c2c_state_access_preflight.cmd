@echo off
setlocal
set "PROJECT_ROOT=%~dp0..\.."
set "HOOK_SCRIPT=%~dp0c2c_state_access_preflight.py"

if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" goto venv
where py >nul 2>&1
if not errorlevel 1 goto pylauncher
where python >nul 2>&1
if not errorlevel 1 goto python
>&2 echo No Python interpreter found for C2C state access preflight.
exit /b 1

:venv
"%PROJECT_ROOT%\.venv\Scripts\python.exe" "%HOOK_SCRIPT%" %*
exit /b %ERRORLEVEL%

:pylauncher
py -3 "%HOOK_SCRIPT%" %*
exit /b %ERRORLEVEL%

:python
python "%HOOK_SCRIPT%" %*
exit /b %ERRORLEVEL%
