@echo off
echo =====================================================
echo  Autocomplete Optimization Patch for Custom Scripts
echo =====================================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Make sure Python is on your PATH.
    pause
    exit /b 1
)

python "%~dp0patch.py"
pause
