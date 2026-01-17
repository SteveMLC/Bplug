#!/bin/bash
# Package Blender Pet Model Optimizer addon for installation
# Creates a zip file ready for Blender's Install Add-on feature

echo "========================================"
echo "Packaging Blender Pet Model Optimizer"
echo "========================================"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "ERROR: Python not found!"
        echo "Please install Python first."
        exit 1
    else
        PYTHON_CMD=python
    fi
else
    PYTHON_CMD=python3
fi

# Run the Python packaging script
$PYTHON_CMD package_addon.py
