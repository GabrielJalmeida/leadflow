@echo off
setlocal
cd /d "%~dp0"

echo LeadFlow - Phase 8.4.4 Fast Replay
echo.
echo Replays scoring, filters, ranking and current investigation selection locally.
echo No Tavily/Gemini calls are made.
echo.
set /p SNAPSHOT="Paste benchmark result folder or run.json path: "
if "%SNAPSHOT%"=="" exit /b 0

echo.
python scripts\run_benchmark.py --replay "%SNAPSHOT%" --replay-stage post_audits
set EXIT_CODE=%ERRORLEVEL%
echo.
if not "%EXIT_CODE%"=="0" (
  echo Replay failed with exit code %EXIT_CODE%.
) else (
  echo Replay finished with zero provider calls.
)
echo.
pause
exit /b %EXIT_CODE%
