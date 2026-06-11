@echo off
setlocal

cd /d "%~dp0"

echo Classic OwnSkinTool flow.
echo Use this before the League of Legends game process loads the match.
echo.
set /p SKIN_ID=Enter cached skin ID, for example 145058: 
if "%SKIN_ID%"=="" (
  echo No skin ID entered.
  pause
  exit /b 1
)

python "%~dp0ownskin.py" import-cache "%SKIN_ID%" --name "skin_%SKIN_ID%" --force
if errorlevel 1 (
  echo Import failed.
  pause
  exit /b 1
)

python "%~dp0ownskin.py" run "skin_%SKIN_ID%"
pause
