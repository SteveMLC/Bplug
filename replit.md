# Blender Pet Model Optimizer Plugin

## Overview
This is a Blender addon (Python plugin) that provides mesh optimization, segmentation, and rigging tools for organic animal models. The plugin adapts proven workflows from Roblox Studio to Blender's native mesh editing, vertex groups, and armature systems.

**Important**: This is NOT a web application. It's a Blender plugin that must be installed into Blender.

## Current State
- Fully functional Blender addon
- Packaging script works and creates installable zip file
- Ready for installation into Blender 3.0+

## Project Structure
```
blender_pet_optimizer/     # Main addon folder (install this in Blender)
├── __init__.py            # Addon registration
├── bl_info.json           # Addon metadata
├── operators/             # Blender operators
├── ui/                    # User interface panels
├── utils/                 # Utility functions
├── config/                # Configuration
└── data/                  # Data files

package_addon.py           # Script to create installable zip
package_addon.sh           # Shell wrapper
package_addon.bat          # Windows wrapper
```

## How to Use

### In Replit
Run the "Package Addon" workflow to create `blender_pet_optimizer.zip`.

### Install in Blender
1. Download the generated `blender_pet_optimizer.zip`
2. Open Blender → Edit → Preferences → Add-ons
3. Click "Install..." and select the zip file
4. Enable "Pet Model Optimizer" in the addon list
5. Access via N-panel (press N in 3D Viewport) → Pet Optimizer tab

## Features
- Mesh Optimization (polygon reduction)
- Body Part Segmentation
- Mesh Splitting
- Rigging Preparation
- Part Standardization
- Roblox-compatible Export

## Requirements
- Blender 3.0 or later
- Python 3.11 (for running package script in Replit)
