:: # /llm_harness/adapters/claude-code/unblock_auto_shell.cmd
echo off
cls
echo Terminal-Only emergency exit: removing the auto-shell hooks from Claude Code (other settings are kept)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0unblock_auto_shell.ps1" %*
echo.
pause
