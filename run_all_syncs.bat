@echo off
setlocal EnableDelayedExpansion
cd /d C:\Dev\amazon-ebay-ops-system

if not exist logs mkdir logs

set "LOG_FILE=logs\scheduler.log"
set "STAMP=%DATE%_%TIME%"
set "STAMP=%STAMP:/=-%"
set "STAMP=%STAMP::=-%"
set "STAMP=%STAMP:.=-%"
set "STAMP=%STAMP: =_%"
set "RUN_LOG=logs\scheduler_%STAMP%_%RANDOM%.tmp"

echo ================================ >> "%RUN_LOG%"
echo Starting sync at %date% %time% >> "%RUN_LOG%"
echo Arguments: %* >> "%RUN_LOG%"

.venv\Scripts\python.exe run_all_syncs.py %* >> "%RUN_LOG%" 2>&1
set "SYNC_EXIT_CODE=!ERRORLEVEL!"

echo Finished sync at %date% %time% >> "%RUN_LOG%"
echo Exit code: !SYNC_EXIT_CODE! >> "%RUN_LOG%"
echo ================================ >> "%RUN_LOG%"

call :append_log_with_retry "%RUN_LOG%" "%LOG_FILE%"
if "!APPEND_OK!"=="1" (
  del "%RUN_LOG%" >nul 2>&1
) else (
  echo Could not append %RUN_LOG% to %LOG_FILE%; temp log preserved.
)

exit /b !SYNC_EXIT_CODE!

:append_log_with_retry
set "SOURCE_LOG=%~1"
set "TARGET_LOG=%~2"
set "APPEND_OK=0"
for /L %%I in (1,1,10) do (
  type "%SOURCE_LOG%" >> "%TARGET_LOG%" 2>nul
  if !ERRORLEVEL! EQU 0 (
    set "APPEND_OK=1"
    goto :eof
  )
  timeout /t 2 /nobreak >nul
)
goto :eof
