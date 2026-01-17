@echo off
REM Package Blender Pet Model Optimizer addon for installation
REM Creates a zip file ready for Blender's Install Add-on feature

echo ========================================
echo Packaging Blender Pet Model Optimizer
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python or use the Python script directly.
    pause
    exit /b 1
)

REM Run the Python packaging script
python package_addon.py

REM Pause to see results
echo.
pause
