@echo off
setlocal
cd /d "%~dp0"

echo LeadFlow - Phase 8.4.4 Real-World Quality Validation
echo.
echo This benchmark performs fresh Tavily/Gemini provider calls and may consume API quota.
echo It will run the official first case: marcenaria - Praia Grande/SP - target 10.
echo.
choice /C YN /N /M "Continue? [Y/N] "
if errorlevel 2 exit /b 0

echo.
python scripts\run_benchmark.py --case marcenaria-praia-grande-sp --refresh-cache
set EXIT_CODE=%ERRORLEVEL%

echo.
if not "%EXIT_CODE%"=="0" (
  echo Benchmark failed with exit code %EXIT_CODE%.
  echo Check provider keys, internet access, and the error shown above.
) else (
  echo Benchmark finished.
  echo Open benchmarks\results\ and review the newest review.csv file.
  echo Fill manual fields with PASS, FAIL or UNCERTAIN before summarizing.
)

echo.
pause
exit /b %EXIT_CODE%
