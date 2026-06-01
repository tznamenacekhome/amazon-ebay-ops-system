@echo off
cd /d C:\Dev\amazon-ebay-ops-system

if not exist logs mkdir logs
if not exist exports mkdir exports

echo ================================ >> logs\inventory_source_balance_audit.log
echo Starting Inventory Source Balance Audit at %date% %time% >> logs\inventory_source_balance_audit.log
echo Arguments: %* >> logs\inventory_source_balance_audit.log

.venv\Scripts\python.exe integrations\inventory_source_balance_audit.py %* >> logs\inventory_source_balance_audit.log 2>&1

echo Finished Inventory Source Balance Audit at %date% %time% >> logs\inventory_source_balance_audit.log
echo Exit code: %ERRORLEVEL% >> logs\inventory_source_balance_audit.log
echo ================================ >> logs\inventory_source_balance_audit.log
