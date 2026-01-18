# Blender Pet Model Optimizer Plugin

## Overview
A professional Blender addon for mesh optimization, segmentation, and rigging of organic animal models. Optimized for processing AI-generated 3D models (like Huanyuan) and preparing them for Roblox import with R6 joint support.

## Current State
- Fully functional Blender addon with enhanced features
- Edge-cut segmentation for fast batch processing
- Roblox R6 Motor6D joint system
- Batch export for 100+ models
- Ready for Blender 3.0+

## Key Features

### Quick Segment (Edge Cuts)
Fast workflow for batch processing:
1. Select edge loops around appendages (head, legs, tail, wings)
2. Mark each cut with segment name
3. Apply - remaining mesh becomes body automatically

### Roblox R6 Joints
Motor6D-compatible pivot points:
- Proper joint naming (Neck, LeftFrontHip, etc.)
- C0/C1 offset transforms
- JSON metadata export for Roblox import scripts
- Hierarchy visualization

### Batch Operations
For processing 100+ models:
- Auto-segment all meshes
- Split all segmented meshes
- Create R6 joints for all
- Export all with manifest

### Mesh Optimization
- QEM edge collapse algorithm
- Centroid clustering
- UV/material/color preservation

## Project Structure
```
blender_pet_optimizer/
├── __init__.py                     # Addon registration
├── bl_info.json                    # Addon metadata
├── operators/
│   ├── mesh_optimizer.py           # Polygon reduction
│   ├── segmentation.py             # Auto-segmentation
│   ├── edge_cut_segmentation.py    # NEW: Edge-loop based cuts
│   ├── mesh_splitter.py            # Split by vertex groups
│   ├── roblox_r6_joints.py         # NEW: R6 joint system
│   ├── batch_export.py             # NEW: Batch export
│   ├── rigging.py                  # Armature creation
│   ├── standardization.py          # Part normalization
│   └── export.py                   # FBX/OBJ export
├── ui/
│   └── panels.py                   # N-panel interface
├── utils/
│   ├── algorithms.py               # Optimization algorithms
│   ├── bmesh_helpers.py            # Mesh utilities
│   └── segmentation_templates.py   # Pet type templates
├── config/
│   └── standards.py                # R6 joint configuration
└── data/
    └── body_part_labels.json       # Part naming

package_addon.py                    # Creates installable zip
```

## Workflow for AI-Generated Models

### Single Model (Manual)
1. Import model into Blender
2. Switch to Edit mode, select edge loops at appendage boundaries
3. Use Quick Segment panel to mark cuts (Head, Legs, Tail, etc.)
4. Click "Apply Cuts & Create Groups"
5. Click "Split Into Parts"
6. Open R6 Joints panel, click "Create R6 Joints"
7. Export as FBX + R6 metadata JSON

### Batch Processing (100+ Models)
1. Import all models into scene
2. Open Batch Operations panel
3. Click "Auto-Segment All" (or manually segment each)
4. Click "Split All Segmented"
5. Click "Create All R6 Joints"
6. Click "Export All Models"

## Install in Blender
1. Run "Package Addon" workflow in Replit
2. Download `blender_pet_optimizer.zip`
3. Open Blender → Edit → Preferences → Add-ons
4. Click "Install..." and select the zip
5. Enable "Pet Model Optimizer"
6. Access via N-panel (press N) → Pet Optimizer tab

## Roblox Import
The exported JSON metadata contains:
- Part names and dimensions
- Motor6D joint configuration (C0, C1 transforms)
- Attachment point positions

Use with a Roblox Studio import script to create Motor6D joints automatically.

## User Preferences
- Quadruped models (dogs, cats, horses)
- Fast edge-cut workflow preferred
- R6 joint compatibility required for Roblox

## Recent Changes
- Added Manual Segment panel for hands-on vertex selection workflow
- Added Quick Decimate tool to reduce 300k+ vertex models before cutting
- Implemented selection refinement tools: Grow, Shrink, Smooth Boundary
- Created one-click segment assignment buttons (Head, Legs, Tail, Wings)
- Added "Assign Remaining as Body" for quick body assignment
- Added segment preview with color-coded vertex visualization
- Added edge-loop based segment marking
- Implemented Roblox R6 Motor6D joint system with full CFrame data (position + rotation + 4x4 matrix)
- Created batch processing for 100+ models
- Enhanced UI with Quick Segment panel
- Added R6 Joints panel with visualization
- Added Batch Operations panel
- Fixed C0/C1 transform computation to use part-local space for Motor6D compatibility
- Updated batch export to handle unsplit models with proper manifest counts
- Improved joint orientation calculation based on part directions

## R6 Joint Data Format
The exported JSON includes for each joint:
- `c0`/`c1`: Position, rotation (Euler), and full 4x4 matrix
- `world_position`/`world_rotation`: Joint location in world space
- `part0`/`part1`: Connected part names

Use the matrix for exact CFrame reconstruction in Roblox import scripts.
