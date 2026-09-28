@echo off
setlocal
set "PROJECT_ROOT=%~dp0..\.."
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "HOOK_SCRIPT=%~dp0git_workspace_preflight.py"

if not exist "%PYTHON%" (
  >&2 echo Project virtual environment missing: "%PYTHON%"
  exit /b 2
)
"%PYTHON%" "%HOOK_SCRIPT%" %*
exit /b %ERRORLEVEL%
