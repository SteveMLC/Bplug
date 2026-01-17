# Blender Pet Model Optimizer Plugin

A professional Blender addon that provides mesh optimization, segmentation, and rigging tools for organic animal models. This plugin adapts proven workflows from Roblox Studio to Blender's native mesh editing, vertex groups, and armature systems, making it perfect for preparing pet models for games, animation, and hybrid breeding systems.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
- [Workflow](#workflow)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [License](#license)

## Features

- **Mesh Optimization**: Reduce polygon counts using centroid clustering or QEM edge collapse algorithms
- **Body Part Segmentation**: Automatically segment and label body parts (head, body, legs, tail, wings) using vertex groups
- **Mesh Splitting**: Split segmented meshes into separate objects with preserved UV maps, materials, and vertex colors
- **Rigging Preparation**: Create armatures with bones positioned for animation based on segmentation
- **Part Standardization**: Normalize scales, orientations, and attachment points for compatibility
- **Export Compatibility**: Prepare models for Roblox import with proper naming and structure

## Installation

### Step 1: Locate Your Blender Addons Directory

The addon needs to be placed in Blender's scripts/addons directory. The location depends on your operating system:

#### Windows
```
%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\
```

Full path example:
```
C:\Users\YourName\AppData\Roaming\Blender Foundation\Blender\4.0\scripts\addons\
```

**Quick access**: Press `Win + R`, type `%APPDATA%\Blender Foundation\Blender`, press Enter. Navigate to your Blender version folder.

#### macOS
```
~/Library/Application Support/Blender/<version>/scripts/addons/
```

**Quick access**: In Finder, press `Cmd + Shift + G`, paste: `~/Library/Application Support/Blender/`

#### Linux
```
~/.config/blender/<version>/scripts/addons/
```

**Quick access**: Open terminal and run:
```bash
cd ~/.config/blender/<version>/scripts/addons/
```

### Step 2: Copy the Plugin Folder

1. **Locate the plugin folder**: In this repository, find the `blender_pet_optimizer` folder (not `blender_pet_model_optimizer` - that's the old name).

2. **Copy the entire folder**: Copy the `blender_pet_optimizer` folder to your Blender addons directory.

   **Important**: Copy the folder itself, not its contents. The directory structure should be:
   ```
   addons/blender_pet_optimizer/
   ├── __init__.py
   ├── bl_info.json
   ├── operators/
   ├── ui/
   ├── utils/
   ├── config/
   └── data/
   ```

3. **Verify the structure**: Make sure `bl_info.json` is directly inside `blender_pet_optimizer/`.

### Step 3: Enable the Addon in Blender

1. **Open Blender** (version 3.0 or later)

2. **Open Add-ons Preferences**:
   - Go to `Edit` → `Preferences` (or press `Ctrl + ,` on Windows/Linux, `Cmd + ,` on macOS)
   - Click on the `Add-ons` tab on the left sidebar

3. **Find the Plugin**:
   - In the search box at the top, type: `Pet Model Optimizer`
   - Or browse the `Mesh` category

4. **Enable the Plugin**:
   - Check the checkbox next to "Pet Model Optimizer"
   - You should see a green checkmark confirming it's enabled

5. **Verify Installation**:
   - Open a 3D Viewport (the main window where you see models)
   - Press `N` to open the Properties panel (N-panel) on the right
   - Look for a tab called `Pet Optimizer` at the bottom of the panel
   - You should see the "Pet Model Optimizer" panel with workflow instructions

### Step 4: Troubleshooting Installation

**Plugin not showing up?**
- Check that the folder name is exactly `blender_pet_optimizer`
- Verify `bl_info.json` is in the root of the plugin folder
- Make sure you copied the folder to the correct Blender version directory
- Try restarting Blender completely

**Plugin shows but won't enable?**
- Check Blender's console for errors (Window → Toggle System Console on Windows, or check Terminal on macOS/Linux)
- Ensure you're using Blender 3.0 or later
- Check that all Python files are present and not corrupted

**Can't find the N-panel?**
- Press `N` in the 3D Viewport (not in other editors)
- The panel appears on the right side
- Look for the `Pet Optimizer` tab at the bottom of the panel tabs

## Quick Start

1. **Import or Create a Mesh**:
   - Import your animal model (File → Import → choose your format)
   - Or create a basic mesh to test with
   - Select the mesh object

2. **Open the Plugin Panel**:
   - In the 3D Viewport, press `N` to open the N-panel
   - Click on the `Pet Optimizer` tab

3. **Follow the Workflow**:
   - The panel shows: "Workflow: Segment → Optimize → Rig → Export"
   - Start with segmentation, then optimize, then rig, then export

## Usage Guide

### Accessing the Plugin

The plugin interface is located in the **N-panel** (Properties panel) in the 3D Viewport:

1. Open or switch to a 3D Viewport window
2. Press `N` (or click the tiny `>` arrow on the right edge of the viewport)
3. Look for the `Pet Optimizer` tab at the bottom of the panel tabs
4. Click it to see all plugin sections

### Basic Workflow

#### 1. Segmentation (Identify Body Parts)

1. **Select your mesh object** in the 3D Viewport
2. **Open the Segmentation panel** (expand it in the N-panel)
3. **Choose Pet Type**:
   - `Quadruped`: For four-legged animals (dogs, cats, horses, etc.)
   - `Biped`: For two-legged animals (birds standing upright, humans, etc.)
   - `Flying`: For flying creatures (birds, dragons, etc.)
4. **Configure Options**:
   - `Clear Existing Groups`: Remove old vertex groups before segmenting (recommended: ON)
   - `Auto Split`: Automatically split mesh into separate objects after segmentation (recommended: ON)
5. **Click "Segment Model"**

**What happens**: The plugin creates vertex groups for each body part (Head, Body, Leg_L, Leg_R, Tail, etc.). If Auto Split is enabled, it also creates separate mesh objects for each part.

**Viewing Results**:
- Switch to Edit Mode to see vertex groups highlighted
- In the Outliner, you'll see new objects for each body part (if Auto Split is enabled)
- The panel shows a list of created vertex groups

#### 2. Mesh Optimization (Reduce Polygon Count)

1. **Select a mesh object** you want to optimize
2. **Open the Mesh Optimization panel**
3. **View Current Stats**: The panel shows current face count
4. **Choose Algorithm**:
   - `Auto`: Plugin automatically selects the best algorithm
   - `QEM Edge Collapse`: Best for preserving surface detail
   - `Centroid Clustering`: Faster, good for organic shapes
5. **Set Reduction**: Use the slider (0-90%) to choose how much to reduce
   - 60% = reduces to 40% of original faces (recommended starting point)
6. **Adjust Grid Size** (if using Centroid): Controls clustering granularity (default 0.3 usually works well)
7. **Click "Optimize Mesh"**

**Tips**:
- Start with lower reduction (30-50%) and increase if needed
- Use QEM for detailed models, Centroid for simpler shapes
- Optimization preserves UV maps and vertex colors

#### 3. Manual Mesh Splitting (Alternative to Auto Split)

If you didn't use Auto Split during segmentation, or want to split manually:

1. **Select the original mesh object** (must have vertex groups)
2. **In the Segmentation panel**, find the "Split Manually" button
3. **Configure Options**:
   - `Keep Original`: Keep the original mesh object (recommended: ON)
   - `Verify Data`: Check for data preservation (recommended: ON)
   - `Create Pivots`: Create attachment point markers (recommended: ON)
4. **Click "Split Manually"**

**What happens**: Creates separate mesh objects for each vertex group, preserves all mesh data (UVs, materials, vertex colors), and optionally creates pivot point markers for attachment points.

#### 4. Rigging (Create Armature for Animation)

1. **Select a mesh object** that has been segmented (has vertex groups)
2. **Open the Rigging panel**
3. **Configure Options**:
   - `Bone Prefix`: Prefix for bone names (default: empty, or set to "Pet_" for "Pet_Head", etc.)
   - `Auto Weights`: Automatically assign vertex weights based on segmentation (recommended: ON)
4. **Click "Create Armature"**

**What happens**: Creates an armature object with bones positioned at body part centers. Bones are named according to vertex groups.

5. **Optional - Setup Rig**: Click "Setup Rig" to finalize bone hierarchy and weight painting

**Note**: The mesh must be segmented first (have vertex groups) before creating an armature.

#### 5. Standardization (Normalize Parts for Compatibility)

Useful when preparing parts for a hybrid breeding system where parts need consistent scales and orientations:

1. **Select one or more mesh objects** (body parts)
2. **Open the Standardization panel**
3. **Configure Options**:
   - `Normalize Scale`: Make all parts use a standard scale (recommended: ON)
   - `Reference Part`: When normalizing scale, which part should be reference (usually "Body")
   - `Standardize Orientation`: Align all parts to standard forward/up axes (recommended: ON)
4. **Click "Standardize Selected Parts"**

**Creating Attachment Points**:
- Click "Create Attachment Points" to add markers at standard connection locations (neck, hip, root)
- These appear as Empty objects in the scene

#### 6. Export (Prepare for Roblox or Other Formats)

1. **Select your model or parts**
2. **Open the Export panel**
3. **For Full Model Export**:
   - Choose format: `FBX` (recommended for Roblox) or `OBJ`
   - Check `Include Metadata` to export part compatibility information
   - Click "Export Model"
4. **For Part Library Export**:
   - Choose format: `FBX` or `OBJ`
   - Click "Export Part Library"
   - Exports each part as a separate file with standardized naming

## Workflow

### Complete Workflow Example

Here's a typical workflow for preparing a pet model:

1. **Import Model**: Import your high-poly animal model (e.g., 50,000 faces)

2. **Segment**: 
   - Select mesh → Segmentation panel → Choose pet type → "Segment Model"
   - Creates vertex groups and optionally splits into separate objects

3. **Optimize** (Optional):
   - For each part or the whole model → Mesh Optimization → Set reduction → "Optimize Mesh"
   - Reduces polygon count while preserving shape

4. **Rig**:
   - Select main body mesh → Rigging panel → "Create Armature"
   - Creates bones for animation

5. **Standardize** (If needed):
   - Select all parts → Standardization → Configure options → "Standardize Selected Parts"
   - Ensures compatibility between parts

6. **Export**:
   - Select model → Export panel → Choose format → "Export Model"
   - Ready for import into Roblox or other game engines

### Workflow Diagram

```
Import High-Poly Mesh
        ↓
   Segment Model
   (Create Vertex Groups)
        ↓
   [Optional] Optimize Mesh
   (Reduce Polygon Count)
        ↓
   Split into Objects
   (If not auto-split)
        ↓
   Create Armature
   (Setup Bones)
        ↓
   [Optional] Standardize Parts
   (Normalize Scales/Orientations)
        ↓
   Export Model
   (FBX/OBJ with Metadata)
```

## Troubleshooting

### Common Issues

**"Select a mesh object" error**
- Make sure you have a mesh object selected (not a camera, light, or armature)
- Click on the mesh in the 3D Viewport or Outliner

**Segmentation not working correctly**
- Try a different pet type (Quadruped/Biped/Flying)
- Ensure your model is properly oriented (front facing +Y axis)
- Check that the model has vertices (not empty)

**Optimization creates weird shapes**
- Reduce the reduction percentage (try 30% instead of 60%)
- Try a different algorithm (QEM vs Centroid)
- Check that your mesh is manifold (no holes or non-manifold edges)

**Can't find vertex groups after segmentation**
- Make sure "Clear Existing Groups" wasn't checked if you wanted to keep old groups
- Check the Object Data Properties (green triangle icon) → Vertex Groups section
- Enter Edit Mode and check the vertex group assignments

**Armature creation fails**
- Ensure the mesh has vertex groups (segment first)
- Check that the mesh object is selected (not the armature)
- Verify the mesh has valid geometry

**Export doesn't work**
- Ensure you have write permissions to the export directory
- Check that the format (FBX/OBJ) is available in your Blender installation
- Try exporting to a different location (desktop or documents folder)

### Performance Tips

- **Large Meshes**: For meshes with 100K+ faces, optimization may take a while. Be patient.
- **Multiple Objects**: Processing many objects at once may slow Blender. Process in batches.
- **Undo History**: Blender's undo can use memory. Use `Ctrl + Z` sparingly or clear history (File → New).

### Getting Help

1. **Check Blender Console**: Window → Toggle System Console (Windows) to see error messages
2. **Verify Plugin Status**: Edit → Preferences → Add-ons → Check "Pet Model Optimizer" is enabled
3. **Check Blender Version**: Requires Blender 3.0 or later

## Project Structure

```
blender_pet_optimizer/
├── __init__.py                 # Addon registration and module loading
├── bl_info.json                # Addon metadata (name, version, description)
├── operators/                  # Blender operators (actions)
│   ├── __init__.py
│   ├── mesh_optimizer.py      # Mesh decimation operators
│   ├── segmentation.py        # Body part segmentation
│   ├── mesh_splitter.py       # Split mesh into separate objects
│   ├── rigging.py             # Armature creation and setup
│   ├── standardization.py     # Part normalization
│   └── export.py              # Roblox-compatible export
├── ui/                         # User interface
│   ├── __init__.py
│   ├── panels.py              # N-panel UI components
│   └── preferences.py         # Addon preferences (if any)
├── utils/                      # Utility modules
│   ├── __init__.py
│   ├── algorithms.py          # QEM and centroid clustering algorithms
│   ├── segmentation_templates.py  # Pet type templates
│   ├── bmesh_helpers.py       # bmesh utility functions
│   └── roblox_export.py       # Roblox-specific export helpers
├── config/                     # Configuration files
│   ├── __init__.py
│   ├── templates.py           # Segmentation region templates
│   └── standards.py           # Standard attachment points and scales
└── data/                       # Data files
    └── body_part_labels.json  # Part naming conventions
```

## License

[Your License Here]

---

For detailed feature documentation, see [PLUGIN_DOCUMENTATION.md](PLUGIN_DOCUMENTATION.md)
