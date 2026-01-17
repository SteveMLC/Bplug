# Blender Pet Model Optimizer Plugin

A Blender addon that provides professional mesh optimization, segmentation, and rigging tools for organic animal models. Adapts the proven workflow from the Roblox Studio plugin to Blender's native mesh editing, vertex groups, and armature systems.

## Features

- **Mesh Optimization**: Reduce polygon counts using centroid clustering or QEM edge collapse
- **Body Part Segmentation**: Automatically segment and label body parts (head, body, legs, tail, wings)
- **Rigging Preparation**: Create armatures with bones positioned for animation
- **Part Standardization**: Normalize scales, orientations, and attachment points
- **Export Compatibility**: Prepare models for Roblox import with proper naming and structure

## Installation

1. Copy the `blender_pet_optimizer` folder to your Blender addons directory:
   - Windows: `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\`
   - macOS: `~/Library/Application Support/Blender/<version>/scripts/addons/`
   - Linux: `~/.config/blender/<version>/scripts/addons/`

2. Open Blender and go to Edit > Preferences > Add-ons
3. Search for "Pet Model Optimizer" and enable it
4. Find the panel in the N-panel (press N in 3D Viewport)

## Project Structure

```
blender_pet_optimizer/
├── __init__.py                 # Addon registration
├── bl_info.json                # Addon metadata
├── operators/                  # Blender operators
│   ├── mesh_optimizer.py      # Decimation operators
│   ├── segmentation.py        # Body part segmentation
│   ├── rigging.py             # Armature creation
│   ├── standardization.py     # Part normalization
│   └── export.py              # Roblox export
├── ui/                         # User interface
│   ├── panels.py              # N-panel UI
│   └── preferences.py         # Addon preferences
├── utils/                      # Utility modules
│   ├── algorithms.py          # QEM, centroid clustering
│   ├── segmentation_templates.py  # Pet type templates
│   └── bmesh_helpers.py       # bmesh utilities
├── config/                     # Configuration
│   ├── templates.py           # Segmentation templates
│   └── standards.py           # Standard attachment points
└── data/                       # Data files
    └── body_part_labels.json  # Part naming conventions
```

## Development Status

This is the foundation structure for the plugin. Implementation is in progress following the plan document.

## License

[Your License Here]

## Contributing

[Contributing Guidelines Here]
