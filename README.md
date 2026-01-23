# Blender Pet Model Optimizer Plugin

A professional Blender addon that provides mesh optimization, segmentation, and rigging tools for organic animal models. This plugin adapts proven workflows from Roblox Studio to Blender's native mesh editing, vertex groups, and armature systems, making it perfect for preparing pet models for games, animation, and hybrid breeding systems.

## Features

- **Mesh Optimization**: Reduce polygon counts using centroid clustering or QEM edge collapse algorithms
- **Low-Poly Prep**: Gently decimate dense meshes in small, iterative steps before segmentation
- **Body Part Segmentation**: Automatically segment and label body parts (head, body, legs, tail, wings) using vertex groups
- **Multiple Segmentation Methods**: Automatic spatial detection, edge-cut segmentation, and manual wizard
- **Mesh Splitting**: Split segmented meshes into separate objects with preserved UV maps, materials, and vertex colors
- **Post-Split Cleanup**: Smooth cut edges and fill cut faces with material-matched geometry
- **Roblox R6 Joints**: Create Motor6D joints at correct attachment boundaries for proper animation in Roblox Studio
- **Rigging Preparation**: Create armatures with bones positioned for animation based on segmentation
- **Symmetry Tools**: Detect symmetry, mirror selections, and symmetrize vertex groups
- **Part Standardization**: Normalize scales, orientations, and attachment points for compatibility
- **Export Compatibility**: Prepare models for Roblox import with proper naming and structure
- **Batch Operations**: Process multiple models automatically

## Quick Installation

1. **Locate Blender Addons Directory**:
   - Windows: `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\`
   - macOS: `~/Library/Application Support/Blender/<version>/scripts/addons/`
   - Linux: `~/.config/blender/<version>/scripts/addons/`

2. **Copy Plugin Folder**: Copy the entire `blender_pet_optimizer` folder to your addons directory

3. **Enable in Blender**: 
   - Open `Edit` → `Preferences` → `Add-ons`
   - Search for "Pet Model Optimizer"
   - Check the checkbox to enable

4. **Access Plugin**: Press `N` in the 3D Viewport, look for the `Pet Optimizer` tab

For detailed installation instructions, see [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Quick Start

1. **Import or Create a Mesh**: Import your animal model or create a test mesh
2. **Open Plugin Panel**: Press `N` in 3D Viewport → Click `Pet Optimizer` tab
3. **Follow Workflow**: Segment → Optimize → Rig → Export

### Basic Workflow

```
Import High-Poly Mesh
        ↓
[Optional] Low-Poly Prep (gentle reduction)
        ↓
   Segment Model (create vertex groups)
        ↓
   Split Into Parts (creates objects + gaps)
        ↓
   Clean Cut Edges (smooth boundaries)
        ↓
   Fill Cut Faces (material-matched caps)
        ↓
   Create R6 Joints (uses stored pivot positions)
        ↓
   Export Model (FBX + JSON metadata)
```

For the complete workflow guide with detailed steps, see [docs/WORKFLOW_GUIDE.md](docs/WORKFLOW_GUIDE.md).

## Documentation

- **[Installation Guide](docs/INSTALLATION.md)** - Detailed installation instructions and troubleshooting
- **[Workflow Guide](docs/WORKFLOW_GUIDE.md)** - Complete step-by-step workflow for Roblox R6 models
- **[Feature Reference](docs/FEATURE_REFERENCE.md)** - Complete documentation of all features and operators
- **[Optimization Guide](docs/OPTIMIZATION.md)** - Deep dive into mesh optimization techniques

## Key Concepts

### Pivot Point Logic (Critical for Roblox R6)

**⚡ WHERE APPENDAGE SEPARATES FROM BODY = WHERE PIVOT POINT MUST BE**

- Pivot points are calculated **BEFORE gaps are created** (from vertex group boundaries)
- Stored in object metadata for R6 joint creation
- **NOT recalculated after gaps** (would place in gap center - WRONG)
- This ensures Motor6D joints connect at correct attachment boundaries in Roblox Studio

See [docs/WORKFLOW_GUIDE.md](docs/WORKFLOW_GUIDE.md#critical-principle-pivot-point-logic) for detailed explanation.

## System Requirements

- **Blender**: Version 3.0 or later (3.5+ recommended)
- **Python**: Included with Blender (no separate installation needed)
- **OS**: Windows, macOS, or Linux

## Troubleshooting

**Plugin not showing?**
- Check folder name is exactly `blender_pet_optimizer`
- Verify `__init__.py` exists in plugin root
- Try restarting Blender

**Can't find N-panel?**
- Press `N` in the 3D Viewport (not other editors)
- Look for `Pet Optimizer` tab at bottom of panel tabs

**R6 joints not at correct positions?**
- Ensure "Use Stored Pivot Positions" is enabled in R6 Joints panel
- Pivot positions are calculated during split operation (before gaps)
- Re-split the model if joints appear in gap centers

For more troubleshooting help, see [docs/INSTALLATION.md](docs/INSTALLATION.md#troubleshooting) and [docs/WORKFLOW_GUIDE.md](docs/WORKFLOW_GUIDE.md#troubleshooting).

## Project Structure

```
blender_pet_optimizer/
├── __init__.py                 # Addon registration and module loading
├── bl_info.json                # Addon metadata (name, version, description)
├── operators/                  # Blender operators (actions)
│   ├── mesh_optimizer.py      # Mesh decimation operators
│   ├── segmentation.py        # Body part segmentation
│   ├── mesh_splitter.py       # Split mesh into separate objects
│   ├── rigging.py             # Armature creation and setup
│   ├── standardization.py     # Part normalization
│   └── export.py              # Roblox-compatible export
├── ui/                         # User interface
│   ├── panels.py              # N-panel UI components
│   └── preferences.py         # Addon preferences
├── utils/                      # Utility modules
│   ├── algorithms.py          # QEM and centroid clustering algorithms
│   ├── bmesh_helpers.py       # bmesh utility functions
│   └── roblox_export.py       # Roblox-specific export helpers
├── config/                     # Configuration files
│   ├── templates.py           # Segmentation region templates
│   └── standards.py           # Standard attachment points and scales
└── data/                       # Data files
    └── body_part_labels.json  # Part naming conventions
```

## License

[Your License Here]

---

**Ready to get started?** See [docs/INSTALLATION.md](docs/INSTALLATION.md) for installation, then [docs/WORKFLOW_GUIDE.md](docs/WORKFLOW_GUIDE.md) for the complete workflow.
