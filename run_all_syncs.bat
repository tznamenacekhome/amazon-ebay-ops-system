@echo off
cd /d C:\Dev\amazon-ebay-ops-system

if not exist logs mkdir logs

echo ================================ >> logs\scheduler.log
echo Starting sync at %date% %time% >> logs\scheduler.log
echo Arguments: %* >> logs\scheduler.log

.venv\Scripts\python.exe run_all_syncs.py %* >> logs\scheduler.log 2>&1

echo Finished sync at %date% %time% >> logs\scheduler.log
echo Exit code: %ERRORLEVEL% >> logs\scheduler.log
echo ================================ >> logs\scheduler.log
