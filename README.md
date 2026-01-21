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
- **Low-Poly Prep (Pre-Segmentation)**: Gently decimate dense meshes in small, iterative steps before any cuts or splits, with options to preserve sharp features and preview on a duplicate `_lowpoly` copy
- **Body Part Segmentation**: Automatically segment and label body parts (head, body, legs, tail, wings) using vertex groups
- **Mesh Splitting**: Split segmented meshes into separate objects with preserved UV maps, materials, and vertex colors. Creates gaps between parts for post-processing workflow.
- **Post-Split Cleanup**: Smooth cut edges and fill cut faces with material-matched geometry
- **Roblox R6 Joints**: Create Motor6D joints at correct attachment boundaries for proper animation in Roblox Studio
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
2. **In the Segmentation panel** or **Quick Segment (Edge Cuts) panel**, find the "Split Manually" button
3. **Configure Options**:
   - `Keep Original`: Keep the original mesh object (recommended: ON)
   - `Verify Data`: Check for data preservation (recommended: ON)
   - `Create Pivots`: Create attachment point markers (recommended: ON)
   - `Gap Distance`: Distance to separate parts after splitting (default: 0.1). Creates visible gaps for post-processing workflow.
4. **Click "Split Manually"**

**What happens**: 
- **CRITICAL**: Pivot/attachment positions are calculated BEFORE splitting from vertex group boundaries
- Creates separate mesh objects for each vertex group
- Preserves all mesh data (UVs, materials, vertex colors)
- **Creates gaps between parts** (parts move apart for filling/smoothing workflow)
- Stores pivot positions in metadata for Roblox R6 joint creation
- Optionally creates pivot point markers for attachment points

**Important for Roblox R6**: The gaps are for workflow convenience (filling cut faces, smoothing edges). Pivot points are calculated at the actual separation boundaries (where appendage meets body) BEFORE gaps are created. This ensures joints connect at correct attachment points in Roblox Studio.

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

#### 5. Post-Split Cleanup (Edge Smoothing & Cut Filling)

**IMPORTANT**: This step should be done AFTER splitting and creating gaps, but BEFORE creating R6 joints.

After splitting, you'll see gaps between parts. This section helps you:
1. **Smooth the cut edges** for cleaner boundaries
2. **Fill the cut surfaces** with material-matched faces

##### 5a. Clean Edges (Smooth Cut Boundaries)

1. **Select the split part objects** you want to smooth
2. **Open the Post-Split Cleanup panel** (NEW - in Pet Optimizer N-panel)
3. **Edge Cleaning section**:
   - `Iterations`: How many smoothing passes (default: 2, recommended: 2-4)
   - `Smooth Factor`: How aggressive the smoothing (default: 1.0)
   - `Only Boundary Edges`: Only smooth cut edges, not all edges (recommended: ON)
4. **Click "Smooth Cut Edges"**

**What happens**: Smooths the cut boundary edges (edges with only one face) to create cleaner separation surfaces.

**Alternative**: Use "Select Cut Boundaries" to manually select and smooth specific edges in Edit mode.

##### 5b. Fill Cut Faces (Cap Open Boundaries)

1. **Select the split part objects** you want to fill
2. **In the Post-Split Cleanup panel**, find the **Cut Filling section**
3. **Configure Options**:
   - `Use Material Color`: Extract color from existing materials (recommended: ON)
   - `Fallback Color`: Color to use if material extraction fails (default: dark brown)
4. **Click "Fill Cut Faces"**

**What happens**:
- Detects open boundary loops (cut surfaces)
- Extracts primary material color from the original mesh
- Creates new faces to cap the open boundaries
- Assigns material to new faces (matching model's primary color)
- Falls back to brown/gray if material extraction fails

**Material Detection**: The operator tries to extract color from:
1. Principled BSDF base color in material nodes
2. Material diffuse color (legacy materials)
3. Vertex colors (sampled average)
4. Falls back to configured fallback color

#### 6. Create Roblox R6 Joints (Set Pivot Points)

**CRITICAL FOR ROBLOX**: This step creates Motor6D joints at the correct attachment boundaries for animation.

1. **Select the split mesh parts** (body and appendages)
2. **Open the Roblox R6 Joints panel**
3. **Verify Scene Status**: Panel shows detected body and segment meshes
4. **Configure Options**:
   - `Joint Scale`: Size of joint visualization (default: 0.1)
   - `Use Stored Pivot Positions`: Use pivot positions from split operation (recommended: ON) ⚠️
   - `Calculate Offsets from Mesh`: Calculate C0/C1 from actual boundaries (recommended: ON)
5. **Click "Create R6 Joints"**

**What happens**:
- **Uses stored pivot positions** (calculated BEFORE gaps were created)
- Pivot points are at actual separation boundaries (where appendage meets body)
- Creates Motor6D joints with correct C0/C1 transforms for Roblox
- Joints appear as Empty objects in the "R6_Joints" collection
- Each joint includes metadata for Roblox import scripts

**Why This Matters**: 
- Pivot points MUST be at the separation boundary (not in gap center)
- This enables correct animation joints in Roblox Studio
- Parts rotate around attachment points correctly
- Motor6D joints connect at proper locations

**Export R6 Metadata**:
- Click "Export R6 Metadata (JSON)" to save joint information
- Use with Roblox import scripts for automated setup

#### 7. Standardization (Normalize Parts for Compatibility)

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

#### 8. Export (Prepare for Roblox or Other Formats)

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

### Complete Workflow Example for Roblox R6 Models

Here's the complete workflow for preparing a pet model ready for Roblox Studio:

#### **Step 1: Import Model**
Import your high-poly animal model (e.g., 50,000+ faces)

#### **Step 2: Low-Poly Prep (Recommended for Dense Meshes)**
- Select the mesh → Mesh Optimization panel → Low-Poly Prep
- Use a small **Step Reduction** (5–15%) and enable **Preserve Sharp Features**
- Click **Preview Low-Poly** to create a `_lowpoly` duplicate and visually compare
- Repeat **Apply Step** until the model is comfortable to work with (typically 10K-50K faces)

#### **Step 3: Segment Model**
Choose ONE method:

**Method A: Quick Segment (Edge Cuts) - Recommended for Clean Models**
1. Select mesh → Quick Segment (Edge Cuts) panel
2. Enter Edit Mode, select edge loops around appendages
3. Click segment buttons (Head, Legs, Tail, Wings) to mark each cut
4. Click **"Apply Cuts & Create Groups"** → Creates vertex groups
5. Click **"Split Into Parts"** → Creates separate objects with gaps

**Method B: Automatic Segmentation**
1. Select mesh → Segmentation panel → Choose pet type
2. Click **"Segment Model"** → Creates vertex groups
3. Click **"Split Manually"** → Creates separate objects with gaps

**Method C: Manual Vertex Assignment**
1. Select mesh → Manual Segment panel
2. Enter Edit Mode, select vertices for each part
3. Click part buttons (Head, Legs, etc.) to assign
4. Click **"Assign Remaining as Body"**
5. Use **"Split Into Parts"** from Segmentation panel

#### **Step 4: Post-Split Cleanup (NEW - Critical for Quality)**

After splitting, parts are separated with gaps for workflow convenience:

**4a. Clean Cut Edges**
1. Select all split parts
2. Post-Split Cleanup panel → Edge Cleaning
3. Click **"Smooth Cut Edges"** → Smooths boundary edges
4. Adjust iterations if needed (2-4 usually sufficient)

**4b. Fill Cut Faces**
1. Select all split parts
2. Post-Split Cleanup panel → Cut Filling
3. Ensure **"Use Material Color"** is ON
4. Click **"Fill Cut Faces"** → Creates material-matched caps on cut surfaces

**Why Gaps?**: 
- Gaps make it easier to access cut edges for smoothing
- Provide space to create fill faces
- Allow visual verification that parts are truly separated
- **Note**: Gaps are workflow-only. Pivot points are at original boundaries.

#### **Step 5: Create Roblox R6 Joints (CRITICAL)**

**⚠️ IMPORTANT**: Pivot positions were calculated BEFORE gaps were created. This ensures joints connect at actual attachment boundaries, not gap centers.

1. Select all split parts (body + appendages)
2. Roblox R6 Joints panel
3. Ensure **"Use Stored Pivot Positions"** is ON ⚠️
4. Click **"Create R6 Joints"**
5. Joints are created at separation boundaries (where appendage meets body)

**What This Does**:
- Creates Motor6D joints with correct C0/C1 transforms
- Pivot points enable animation in Roblox Studio
- Parts rotate correctly around attachment points
- Joints appear in "R6_Joints" collection

#### **Step 6: Export R6 Metadata (Optional)**
1. Roblox R6 Joints panel → Export section
2. Click **"Export R6 Metadata (JSON)"**
3. Use with Roblox import scripts for automated setup

#### **Step 7: Export Model**
1. Select all parts (or just the ones you need)
2. Export panel → Choose FBX format
3. Click **"Export Model"** → Ready for Roblox Studio

### Complete Workflow Diagram

```
Import High-Poly Mesh
        ↓
[Optional] Low-Poly Prep
   (Gentle reduction in steps)
        ↓
   Segment Model
   (Create Vertex Groups)
        ↓
   Split Into Parts
   (Creates objects + gaps)
   ⚠️ Pivot positions calculated HERE (before gaps)
        ↓
   Clean Cut Edges
   (Smooth boundaries)
        ↓
   Fill Cut Faces
   (Material-matched caps)
        ↓
   Create R6 Joints
   (Uses stored pivot positions)
   ⚠️ Joints at actual boundaries
        ↓
   Export Model
   (FBX + JSON metadata)
        ↓
   Import to Roblox Studio
   ✅ Joints connect correctly
   ✅ Animation works properly
```

### Key Workflow Principles for Roblox R6

1. **Pivot Point Logic (CRITICAL)**:
   - **Where appendage separates from body = Where pivot point must be**
   - Calculated BEFORE gaps are created (from vertex group boundaries)
   - Stored in metadata for R6 joint creation
   - NOT recalculated after gaps (would place in gap center - WRONG)

2. **Gap Purpose**:
   - Workflow convenience only (filling, smoothing, testing)
   - Parts can be moved together later if needed
   - Gaps do NOT affect pivot positions

3. **Workflow Order**:
   - Segment → Split (with gaps) → Clean → Fill → Joints → Export
   - Each step builds on the previous
   - Can't create joints before splitting (needs stored pivot positions)

4. **Roblox Compatibility**:
   - Motor6D joints require correct C0/C1 transforms
   - Pivot points must be at attachment boundaries
   - Joints enable proper animation in Roblox Studio

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

**R6 joints not at correct positions**
- Ensure "Use Stored Pivot Positions" is enabled in R6 Joints panel
- Pivot positions are calculated during split operation (before gaps)
- If joints appear in gap centers, stored positions may be missing - re-split the model

**Cut faces not filling correctly**
- Make sure parts have gaps (check "Gap Distance" > 0 in split operator)
- Try adjusting "Fallback Color" if material extraction fails
- Ensure parts have open boundary loops (edges with only one face)

**Gaps too large/small**
- Adjust "Gap Distance" parameter in Split operator (default: 0.1)
- Gaps are workflow-only and don't affect final Roblox model
- Can manually move parts together later if needed

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
