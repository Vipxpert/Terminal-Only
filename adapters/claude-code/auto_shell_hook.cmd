:: # /llm_harness/adapters/claude-code/auto_shell_hook.cmd
rem Terminal-Only auto-shell hook front for Claude Code, run as: cmd /d /q /c auto_shell_hook.cmd prompt^|pretool
rem It looks for a Terminal-Only project from the working folder and every parent (never the install or home folder). Outside a project it exits at once, so ordinary projects never start PowerShell or Python. Inside one, or when the working folder is home or temp (where Claude Code falls back when the real folder is gone), it hands the untouched input to auto_shell_hook.ps1, which reads the real cwd and decides.
setlocal EnableExtensions
set "MODE=%~1"
if /i "%CD%"=="%USERPROFILE%" goto :hand
if /i "%CD%"=="%TEMP%" goto :hand
if /i "%CD%"=="%TMP%" goto :hand
set "DIR=%CD%"
:walk
if exist "%DIR%\.llm_harness\harness.py" goto :up
if /i "%DIR%"=="%USERPROFILE%" goto :up
if exist "%DIR%\.llm_harness\" goto :hand
if exist "%DIR%\.git\llm_harness\" goto :hand
:up
for %%I in ("%DIR%\..") do set "PARENT=%%~fI"
if /i "%PARENT%"=="%DIR%" exit /b 0
set "DIR=%PARENT%"
goto :walk
:hand
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0auto_shell_hook.ps1" %MODE%
exit /b %ERRORLEVEL%
