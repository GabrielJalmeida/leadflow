@echo off
setlocal
cd /d "%~dp0"

echo LeadFlow - Phase 8.4.4 Fast Capture
echo.
echo Development fixture capture only:
echo   - up to 2 real search calls
echo   - 0 Gemini calls
echo   - 0 Investigator calls
echo   - 0 website/browser/visual audits
echo.
echo It is NOT an official benchmark and should finish much faster than smoke mode.
echo.
choice /C YN /N /M "Capture marcenaria - Praia Grande/SP candidates now? [Y/N] "
if errorlevel 2 exit /b 0

echo.
python scripts\run_benchmark.py --case marcenaria-praia-grande-sp --capture-only --refresh-cache
set EXIT_CODE=%ERRORLEVEL%
echo.
if not "%EXIT_CODE%"=="0" (
  echo Fast capture failed with exit code %EXIT_CODE%.
) else (
  echo Fast capture finished. Snapshot saved under benchmarks\captures\.
  echo Use run-phase844-replay.bat for local iteration after this.
)
echo.
pause
exit /b %EXIT_CODE%
