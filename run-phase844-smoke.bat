@echo off
setlocal
cd /d "%~dp0"

echo LeadFlow - Phase 8.4.4 Smoke Test
echo.
echo This runs only 3 leads and captures a replay snapshot for fast local iteration.
echo It may consume a small amount of Tavily/Gemini quota.
echo.
choice /C YN /N /M "Run marcenaria - Praia Grande/SP smoke test? [Y/N] "
if errorlevel 2 exit /b 0

echo.
python scripts\run_benchmark.py --case marcenaria-praia-grande-sp --smoke --refresh-cache
set EXIT_CODE=%ERRORLEVEL%
echo.
if not "%EXIT_CODE%"=="0" (
  echo Smoke test failed with exit code %EXIT_CODE%.
) else (
  echo Smoke test finished. Snapshot saved under benchmarks\smoke\.
  echo Future deterministic changes can be checked with run-phase844-replay.bat.
)
echo.
pause
exit /b %EXIT_CODE%
