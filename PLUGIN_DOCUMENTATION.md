# Pet Model Optimizer Plugin - Feature Documentation

Complete documentation of all features, operators, and functionality available in the Pet Model Optimizer plugin for Blender.

## Table of Contents

- [Overview](#overview)
- [Feature Categories](#feature-categories)
  - [Mesh Optimization](#mesh-optimization)
  - [Body Part Segmentation](#body-part-segmentation)
  - [Mesh Splitting](#mesh-splitting)
  - [Rigging](#rigging)
  - [Part Standardization](#part-standardization)
  - [Export](#export)
- [Technical Details](#technical-details)
- [Naming Conventions](#naming-conventions)
- [Data Preservation](#data-preservation)
- [Compatibility](#compatibility)

## Overview

The Pet Model Optimizer is a comprehensive Blender addon designed specifically for preparing organic animal models for games, animation, and hybrid breeding systems. It provides a complete workflow from high-poly meshes to optimized, segmented, and rigged models ready for export.

### Key Capabilities

- **Automatic Body Part Detection**: Intelligently segments meshes into anatomically correct parts
- **Advanced Decimation**: Two sophisticated algorithms for polygon reduction
- **Non-Destructive Workflow**: Uses vertex groups to preserve original geometry
- **Roblox-Ready**: Exports models compatible with Roblox Studio workflows
- **Data Preservation**: Maintains UV maps, materials, vertex colors, and custom data

## Feature Categories

### Mesh Optimization

**Purpose**: Reduce polygon counts while preserving organic shapes and important surface details.

#### Algorithms

##### 1. QEM Edge Collapse (Quadric Error Metric)

**Best For**: High-detail models where surface quality is critical

**How It Works**:
- Calculates a quadric error metric for each edge
- Collapses edges with lowest error impact first
- Preserves surface curvature and boundaries
- Maintains edge flow and topology

**Settings**:
- **Reduction**: Target face reduction (0-90%)
  - Lower values (30-50%): Better quality preservation
  - Higher values (70-90%): Maximum reduction, may lose detail

**When to Use**:
- Detailed models with important surface features
- Models with complex topology
- When preserving edge flow is critical
- Final optimization pass after centroid clustering

##### 2. Centroid Clustering

**Best For**: Organic shapes, fast processing, large meshes

**How It Works**:
- Divides space into a 3D grid
- Clusters vertices within each grid cell
- Moves vertices to cell centroids
- Removes degenerate geometry

**Settings**:
- **Reduction**: Target face reduction (0-90%)
- **Grid Size**: Spatial cell size for clustering
  - Smaller values (0.1-0.2): More detail preserved, slower
  - Larger values (0.4-0.8): Faster, more aggressive reduction
  - Default (0.3): Balanced for most organic meshes

**When to Use**:
- Large meshes (100K+ faces) that need quick reduction
- Organic animal shapes without sharp edges
- Initial optimization pass before QEM refinement
- When processing time is a concern

##### 3. Auto Selection

**How It Works**:
- Analyzes mesh characteristics (face count, topology, shape)
- Automatically selects best algorithm (QEM or Centroid)
- Optimizes parameters based on mesh properties

**When to Use**:
- When unsure which algorithm to choose
- For batch processing multiple different meshes
- Quick optimization without parameter tuning

#### Data Preservation

The optimization process preserves:
- ✅ UV maps (all UV layers)
- ✅ Vertex color attributes
- ✅ Material assignments
- ✅ Custom vertex groups (existing groups not related to segmentation)
- ✅ Mesh topology connectivity

#### Limitations

- May create non-manifold geometry at high reduction levels
- Sharp edges may become rounded with centroid clustering
- Very complex meshes may require multiple passes
- Some degenerate faces may need manual cleanup

---

### Body Part Segmentation

**Purpose**: Automatically identify and label body parts in animal meshes using spatial region analysis.

#### Pet Type Templates

##### Quadruped Template

**For**: Dogs, cats, horses, cows, most four-legged animals

**Detected Parts**:
- `Head`: Upper portion of mesh (typically Y-axis top 30%)
- `Body`: Central torso region
- `Leg_L` / `Leg_R`: Left and right leg pairs (front and back combined)
- `Tail`: Posterior extension from body

**Spatial Regions**:
- Uses Y-axis (height) for head/body separation
- Uses X/Z axes for leg detection (left/right, front/back)
- Detects tail as protrusion from body rear

##### Biped Template

**For**: Standing birds, humans, two-legged creatures

**Detected Parts**:
- `Head`: Top portion
- `Body`: Torso region
- `Leg_L` / `Leg_R`: Left and right legs
- `Tail`: If present (birds, etc.)
- `Wing_L` / `Wing_R`: If present (birds with wings)

**Spatial Regions**:
- Vertical segmentation for head/body
- Lateral separation for legs
- Wing detection via mesh connectivity analysis

##### Flying Template

**For**: Birds in flight, dragons, flying creatures

**Detected Parts**:
- `Head`: Front/upper portion
- `Body`: Central core
- `Wing_L` / `Wing_R`: Wing structures
- `Tail`: Rear extension
- `Leg_L` / `Leg_R`: Legs (may be retracted/folded)

**Spatial Regions**:
- Emphasizes wing detection via protrusion analysis
- Different body proportions than grounded templates
- Accounts for flight pose geometry

#### Segmentation Process

1. **Bounding Box Analysis**: Calculates mesh bounds in world space
2. **Spatial Mapping**: Normalizes vertex positions to 0-1 range within bounds
3. **Region Detection**: Assigns vertices to regions based on template rules
4. **Connectivity Refinement**: Uses mesh connectivity to refine boundaries
5. **Vertex Group Creation**: Creates Blender vertex groups for each part
6. **Labeling**: Applies standardized naming from `body_part_labels.json`

#### Options

- **Clear Existing Groups**: Removes all existing vertex groups before segmentation (recommended for clean results)
- **Auto Split**: Automatically splits mesh into separate objects after segmentation (creates independent meshes per part)

#### Result

Creates vertex groups with names:
- `Head`
- `Body`
- `Leg_L`, `Leg_R`
- `Tail`
- `Wing_L`, `Wing_R` (if applicable)

Each vertex can belong to multiple groups (with weights), allowing smooth transitions at boundaries.

---

### Mesh Splitting

**Purpose**: Convert vertex groups into separate mesh objects while preserving all mesh data.

#### Functionality

Splits a segmented mesh into individual objects based on vertex groups. Each part becomes an independent mesh object that can be moved, modified, or exported separately.

#### Data Preservation

The splitter preserves:
- ✅ **UV Maps**: All UV layers transferred to split objects
- ✅ **Materials**: Material slots and assignments maintained
- ✅ **Vertex Colors**: All color attributes preserved
- ✅ **Face Normals**: Surface normals maintained
- ✅ **Vertex Positions**: Accurate geometry separation
- ✅ **Custom Properties**: Object and mesh custom properties copied

#### Options

- **Keep Original**: Retains the original combined mesh object (recommended for non-destructive workflow)
- **Verify Data**: Validates data preservation before splitting (checks for UV layers, materials, etc.)
- **Create Pivots**: Generates Empty objects at attachment points between parts

#### Attachment Points (Pivots)

When "Create Pivots" is enabled, the splitter creates Empty objects at standard connection locations:

- **NeckAttachment**: Connection between head and body
- **HipAttachment**: Connection between body and legs
- **RootAttachment**: Base connection point

These pivot points:
- Are positioned at geometric boundaries between parts
- Include custom properties (`pet_pivot_type`, `pet_source_part`, `pet_target_part`)
- Can be used for rigging or export metadata
- Appear in a collection named `{ObjectName}_Pivots`

#### Use Cases

- **Part Library Creation**: Split model into reusable parts for hybrid systems
- **Individual Optimization**: Optimize each part separately with different settings
- **Export Preparation**: Export parts as separate files
- **Selective Modification**: Edit parts independently without affecting others

---

### Rigging

**Purpose**: Create armatures with bones positioned and named based on body part segmentation.

#### Armature Creation

**Process**:
1. Analyzes vertex groups from segmentation
2. Calculates centroid (center point) of each vertex group
3. Creates bones positioned at part centroids
4. Sets up bone hierarchy (root → body → parts)
5. Names bones according to naming conventions

#### Bone Naming

Bones follow the pattern defined in `body_part_labels.json`:

- **Root**: `Root` (or `{Prefix}Root` if prefix specified)
- **Body**: `Body` (or `{Prefix}Body`)
- **Parts**: `Head`, `Leg_L_01`, `Leg_R_01`, `Tail_01`, etc.

If a bone prefix is specified (e.g., "Pet_"), all bones get that prefix:
- `Pet_Root`, `Pet_Body`, `Pet_Head`, etc.

#### Bone Hierarchy

```
Root (root bone)
├── Body (central bone)
    ├── Head
    ├── Leg_L_01, Leg_L_02, ... (if multiple leg segments)
    ├── Leg_R_01, Leg_R_02, ...
    ├── Tail_01, Tail_02, ... (if multiple tail segments)
    └── Wing_L, Wing_R (if present)
```

#### Weight Painting

**Auto Weights**: When enabled, automatically assigns vertex weights based on vertex group membership:

- Vertices in a part's vertex group get full weight (1.0) for that bone
- Boundary vertices may have weights split between adjacent parts
- Creates smooth deformation at joints

**Manual Weight Painting**: After creation, weights can be painted manually using Blender's Weight Paint mode for fine-tuning.

#### Options

- **Bone Prefix**: Optional prefix for all bone names (useful for multiple rigs in one scene)
- **Auto Weights**: Automatically assign weights from vertex groups (recommended: ON)

#### Setup Rig Operator

The "Setup Rig" operator performs additional rigging tasks:
- Finalizes bone hierarchy relationships
- Applies constraint setups (if needed)
- Optimizes weight distribution
- Validates rig integrity

---

### Part Standardization

**Purpose**: Normalize parts for compatibility in hybrid breeding systems and consistent scaling.

#### Scale Normalization

**Purpose**: Ensure all parts use a consistent scale reference.

**Process**:
1. Identifies reference part (typically "Body")
2. Calculates scale factor for reference part
3. Applies relative scaling to all other parts
4. Maintains proportional relationships

**Reference Part Options**:
- `Body`: Body part is reference (1.0 scale)
- Other parts: Use specific part as reference

**Result**: All parts scale relative to the reference, ensuring compatible sizes when mixing parts from different models.

#### Orientation Standardization

**Purpose**: Align all parts to standard coordinate axes.

**Standard Axes**:
- **Forward**: +Y axis
- **Up**: +Z axis
- **Right**: +X axis

**Process**:
1. Analyzes part orientation
2. Calculates rotation to align with standard axes
3. Applies rotation to part geometry and bones
4. Updates transformation matrices

**Result**: All parts face the same direction and have consistent orientation, simplifying attachment and animation.

#### Attachment Point Creation

Creates Empty objects at standard attachment locations:

- **NeckAttachment**: Between head and body
- **HipAttachment**: Between body and legs/tail
- **RootAttachment**: Base of model (ground contact)

**Properties**:
- Positioned at geometric boundaries
- Named according to Roblox conventions
- Include metadata (custom properties) for export
- Visible in viewport for manual adjustment

#### Use Cases

- **Hybrid Breeding**: Prepare parts from different models to be compatible
- **Part Library**: Standardize library of reusable parts
- **Animation Setup**: Ensure consistent orientation for animation
- **Export Preparation**: Meet requirements for game engine import

---

### Export

**Purpose**: Export models and parts in formats compatible with Roblox and other game engines.

#### Model Export

Exports the complete model (mesh + armature + metadata) as a single file.

**Formats**:
- **FBX**: Recommended for Roblox Studio
  - Preserves armature and bone hierarchy
  - Includes animation data
  - Maintains material assignments
- **OBJ**: Universal mesh format
  - Simple geometry only
  - No armature or animation
  - Good for static models

**Metadata** (when enabled):
- Part naming conventions
- Attachment point locations
- Scale and orientation information
- Compatibility data for hybrid systems

**Export Location**: User-selected file path via Blender's file browser.

#### Part Library Export

Exports each body part as a separate file, useful for creating part libraries.

**Process**:
1. Identifies all segmented parts (from vertex groups or split objects)
2. Exports each part as individual file
3. Applies standardized naming: `{AnimalType}_{PartName}.{ext}`
4. Creates metadata file listing all parts

**File Structure**:
```
export_directory/
├── Cat_Head.fbx
├── Cat_Body.fbx
├── Cat_Leg_L.fbx
├── Cat_Leg_R.fbx
├── Cat_Tail.fbx
└── parts_metadata.json
```

**Metadata File** (`parts_metadata.json`):
```json
{
  "animal_type": "Cat",
  "parts": [
    {"name": "Head", "file": "Cat_Head.fbx", "attachment": "NeckAttachment"},
    {"name": "Body", "file": "Cat_Body.fbx", "attachments": ["NeckAttachment", "HipAttachment"]},
    ...
  ],
  "scale_reference": "Body",
  "orientation": {"forward": "+Y", "up": "+Z"}
}
```

#### Options

- **Format**: FBX or OBJ
- **Include Metadata**: Export compatibility and naming information (JSON file)

---

## Technical Details

### Algorithm Implementations

#### QEM Edge Collapse

**Complexity**: O(n log n) where n = number of edges

**Data Structures**:
- Priority queue for edge collapse order
- Quadric matrices for error calculation
- Edge adjacency lists

**Preservation**:
- Boundary edges flagged and protected
- Feature edges (sharp angles) preserved
- UV seam boundaries maintained

#### Centroid Clustering

**Complexity**: O(n) where n = number of vertices

**Passes**:
1. **Spatial Hashing**: O(n) - Assign vertices to grid cells
2. **Centroid Calculation**: O(n) - Calculate cell centroids
3. **Vertex Remapping**: O(n) - Move vertices to centroids
4. **Degeneracy Removal**: O(m) - Remove degenerate faces, m = number of faces

**Grid Size Selection**:
- Based on mesh bounding box diagonal
- Default: 3% of bounding box size
- User-adjustable for fine control

### Vertex Group System

Blender's vertex groups are used for segmentation:
- **Non-destructive**: Original geometry unchanged
- **Weighted**: Vertices can belong to multiple groups
- **Editable**: Can be painted manually in Edit/Weight Paint mode
- **Compatible**: Works with Blender's armature system

### Mesh Data Preservation

The plugin uses Blender's mesh data API to preserve:
- `mesh.uv_layers`: UV mapping data
- `mesh.vertex_colors`: Color attributes
- `mesh.materials`: Material slots and assignments
- `mesh.polygons`: Face data and normals
- Custom properties on mesh and object

### Coordinate Systems

- **Blender Standard**: Y-forward, Z-up (applied internally)
- **Export Standard**: Converts to target format conventions
- **Roblox Compatibility**: Y-forward, Z-up maintained

---

## Naming Conventions

All naming follows standards defined in `data/body_part_labels.json`:

### Vertex Groups
- `Head`, `Body`, `Leg_L`, `Leg_R`, `Tail`, `Wing_L`, `Wing_R`

### Object Names
- Pattern: `{AnimalType}_{PartName}`
- Example: `Cat_Head`, `Dog_Body`, `Bird_Wing_L`

### Bone Names
- Root: `Root` or `{Prefix}Root`
- Parts: `Head`, `Body`, `Leg_L_01`, `Leg_R_01`, `Tail_01`
- With prefix: `Pet_Head`, `Pet_Body`, etc.

### Attachment Points
- `NeckAttachment`: Head-to-body connection
- `HipAttachment`: Body-to-legs/tail connection
- `RootAttachment`: Base/ground connection

### Collections
- Pivot points: `{ObjectName}_Pivots`
- Split parts: Same collection as original (or user-selected)

---

## Data Preservation

The plugin is designed to preserve all mesh data throughout the workflow:

### Preserved Data Types

1. **UV Maps**: All UV layers maintained through optimization, splitting, and export
2. **Vertex Colors**: Color attributes preserved (RGBA, multiple layers)
3. **Materials**: Material slots, assignments, and properties
4. **Custom Properties**: User-defined properties on objects and meshes
5. **Shape Keys**: Morph targets (if present) maintained where possible
6. **Vertex Groups**: Existing groups preserved (unless cleared during segmentation)

### Verification

The plugin includes verification steps:
- Checks for UV layers before/after operations
- Validates material assignments
- Confirms vertex color preservation
- Reports data loss (if any) in operator results

---

## Compatibility

### Blender Versions

- **Minimum**: Blender 3.0
- **Recommended**: Blender 3.5 or later
- **Tested**: Blender 3.0 - 4.0+

### Export Formats

- **FBX**: Compatible with Roblox Studio, Unity, Unreal Engine, Maya, 3ds Max
- **OBJ**: Universal format, compatible with all 3D software

### Roblox Studio

Exported models are compatible with Roblox Studio:
- Proper bone naming for Motor6D setup
- Attachment point naming conventions
- Scale and orientation standards
- Metadata for automated import workflows

### Workflow Integration

- **Non-destructive**: Can be used in any order, with undo support
- **Compatible with other addons**: Uses standard Blender APIs
- **Scriptable**: All operators can be called from Python scripts
- **Batch processing**: Can process multiple objects in sequence

---

## Performance Considerations

### Optimization Performance

- **Small meshes** (<10K faces): <1 second
- **Medium meshes** (10K-50K faces): 1-5 seconds
- **Large meshes** (50K-200K faces): 5-30 seconds
- **Very large meshes** (200K+ faces): 30+ seconds, may require multiple passes

### Segmentation Performance

- Typically <5 seconds for most meshes
- Complex meshes with many protrusions may take longer
- Auto-split adds processing time proportional to number of parts

### Memory Usage

- Scales with mesh size
- Large meshes (>500K faces) may require significant RAM
- Splitting creates copies of mesh data (consider "Keep Original" = OFF for memory-constrained systems)

---

For installation and usage instructions, see [README.md](README.md)
