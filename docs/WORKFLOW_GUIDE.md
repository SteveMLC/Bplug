# Complete Workflow Guide: Segmentation to Roblox R6 Ready

This guide explains the complete workflow for preparing pet models for Roblox Studio, with emphasis on the critical pivot point logic for R6 rigging.

## Overview

The workflow consists of 8 main steps, designed to preserve mesh fidelity and ensure proper Roblox R6 joint placement:

1. **Vertex Assignment / Segmentation** → Create vertex groups
2. **Split Into Parts** → Separate mesh objects + create gaps + **store pivot positions**
3. **Clean Edges** → Smooth cut boundaries
4. **Fill Cuts** → Cap open surfaces with material
5. **Create R6 Joints** → Use stored pivot positions for correct attachment points
6. **Export** → FBX + JSON metadata

## Critical Principle: Pivot Point Logic

**⚡ WHERE APPENDAGE SEPARATES FROM BODY = WHERE PIVOT POINT MUST BE**

This is the most important concept for Roblox R6 rigging:

- **Pivot points enable animation**: Parts rotate around these points in Roblox
- **Must be at attachment boundary**: Where appendage physically connects to body
- **Calculated BEFORE gaps**: Uses vertex group boundaries (original mesh state)
- **NOT recalculated after gaps**: Would place pivots in gap center (WRONG)

### Why This Matters

When you import to Roblox Studio:
- Motor6D joints connect at pivot positions
- If pivot is in gap center → joint connects incorrectly → animation breaks
- If pivot is at boundary → joint connects correctly → animation works

## Step-by-Step Workflow

### Step 1: Segment Model

**Goal**: Create vertex groups that define body parts.

**Methods**:

#### Method A: Quick Segment (Edge Cuts) - Recommended

1. Select mesh → **Quick Segment (Edge Cuts)** panel
2. Enter **Edit Mode**, select edge loops around appendages
3. Click segment buttons (Head, Legs, Tail, Wings) to mark each cut
4. Click **"Apply Cuts & Create Groups"** → Creates vertex groups
5. Result: Vertex groups created (mesh still whole)

#### Method B: Automatic Segmentation

1. Select mesh → **Segmentation** panel
2. Choose pet type (Quadruped/Biped/Flying)
3. Click **"Segment Model"**
4. Result: Vertex groups created automatically

#### Method C: Manual Vertex Assignment

1. Select mesh → **Manual Segment** panel
2. Enter Edit Mode, manually select vertices for each part
3. Click part buttons to assign
4. Click **"Assign Remaining as Body"**
5. Result: Vertex groups created manually

#### Segmentation Button Functions

**Preview Button** (Eye Icon):
- **Purpose**: Preview segmentation results BEFORE finalizing or splitting
- **What it does**:
  - Creates vertex groups based on current settings
  - Switches to **Weight Paint mode** automatically
  - Selects the first vertex group for visualization
  - Shows vertex groups in the Results section
  - Does NOT split the mesh (non-destructive)
- **How to use**:
  1. Adjust settings (Pet Type, Detection Method, Sensitivity, etc.)
  2. Click **"Preview"**
  3. View results in Weight Paint mode
  4. Switch between vertex groups in the Properties panel (Object Data → Vertex Groups) to see each part highlighted
  5. Adjust settings and preview again if needed

**Segment Model Button** (Gear Icon):
- **Purpose**: Finalize segmentation and optionally auto-split
- **What it does**:
  - Creates vertex groups (same as Preview)
  - Stores metrics (parts detected, vertex counts, processing time)
  - If "Auto Split" is enabled: Automatically splits mesh into separate objects
  - If "Auto Split" is disabled: Only creates vertex groups (recommended workflow)
- **Recommended Settings**:
  - ✅ **Auto Split: OFF** (default) - Preview first, then split manually when satisfied
  - ✅ **Clear Existing Groups: ON** - Start fresh each time
- **How to use**:
  1. Preview first to check results
  2. Adjust settings if needed
  3. Click **"Segment Model"** to finalize
  4. Review results in the Results section
  5. Use "Split Manually" button when ready to split

**Visualization Tips**:
- In Weight Paint mode, each vertex group shows as a colored overlay
- Switch vertex groups in Properties panel (Object Data Properties → Vertex Groups dropdown)
- Red = selected vertex group, Blue = other groups
- You can paint/adjust vertex groups directly in Weight Paint mode

### Step 2: Split Into Parts (CRITICAL: Pivot Calculation)

**Goal**: Separate mesh into objects, create gaps, **store pivot positions**.

1. **Select the segmented mesh** (must have vertex groups)
2. **Segmentation** or **Quick Segment** panel → **"Split Manually"** button
3. **Configure Options**:
   - `Keep Original`: ON (recommended)
   - `Verify Data`: ON (recommended)
   - `Gap Distance`: 0.1 (default, adjustable)
   - `Create Pivots`: ON (for visualization)
4. **Click "Split Manually"**

**What Happens (In Order)**:

1. ✅ **Pivot positions calculated FIRST** (from vertex group boundaries)
   - Uses `calculate_attachment_points_from_vertex_groups()`
   - Finds exact boundaries where appendage meets body
   - **Stores in object metadata** as `pet_stored_attachment_points`

2. ✅ **Mesh split into separate objects**
   - Each vertex group → separate mesh object
   - Data preserved (UVs, materials, vertex colors)

3. ✅ **Gaps created** (parts moved apart)
   - Body stays in place
   - Appendages move away from body by `gap_distance`
   - Original positions stored in `pet_original_location`

4. ✅ **Pivot markers created** (if enabled)
   - Empty objects at stored pivot positions
   - For visualization only (R6 joints use stored positions)

**Important**: 
- Gaps are **workflow-only** (for filling/smoothing)
- Pivot positions **NOT affected by gaps**
- Stored positions used later for R6 joints

**When to use**: After you've previewed and are satisfied with segmentation, when you're ready to work with separate parts, before rigging or exporting.

### Step 3: Clean Edges (Post-Split Cleanup)

**Goal**: Smooth cut boundary edges for cleaner surfaces.

1. **Select all split parts**
2. **Post-Split Cleanup** panel → **Edge Cleaning** section
3. **Configure**:
   - `Iterations`: 2-4 (default: 2)
   - `Smooth Factor`: 1.0 (default)
   - `Only Boundary Edges`: ON (recommended)
4. **Click "Smooth Cut Edges"**

**What Happens**:
- Selects boundary edges (edges with only one face)
- Applies smoothing iterations
- Creates cleaner cut surfaces

**Alternative**: Use **"Select Cut Boundaries"** to manually select edges, then smooth.

### Step 4: Fill Cut Faces (Post-Split Cleanup)

**Goal**: Cap open cut surfaces with material-matched faces.

1. **Select all split parts**
2. **Post-Split Cleanup** panel → **Cut Filling** section
3. **Configure**:
   - `Use Material Color`: ON (recommended)
   - `Fallback Color`: Dark brown (0.4, 0.25, 0.15) or gray
4. **Click "Fill Cut Faces"**

**What Happens**:
- Detects open boundary loops (cut surfaces)
- Extracts primary material color (in order):
  1. Principled BSDF base color
  2. Material diffuse color
  3. Vertex colors (average)
  4. Fallback color
- Creates new faces to cap boundaries
- Assigns material to new faces
- Recalculates normals

**Result**: All cut surfaces are capped with matching material.

### Step 5: Create Roblox R6 Joints (CRITICAL)

**Goal**: Create Motor6D joints at correct attachment boundaries.

1. **Select all split parts** (body + appendages)
2. **Roblox R6 Joints** panel
3. **Verify Scene Status**: Should show body and segments found
4. **Configure Options**:
   - `Joint Scale`: 0.1 (visualization size)
   - **`Use Stored Pivot Positions`: ON** ⚠️ **CRITICAL**
   - `Calculate Offsets from Mesh`: ON (recommended)
5. **Click "Create R6 Joints"**

**What Happens**:
- ✅ **Reads stored pivot positions** from object metadata
- ✅ **Uses positions calculated BEFORE gaps** (at actual boundaries)
- ✅ Creates Motor6D joints with correct C0/C1 transforms
- ✅ Joints placed where appendage meets body (not in gap center)
- ✅ Creates Empty objects in "R6_Joints" collection

**Why "Use Stored Pivot Positions" is Critical**:
- If ON: Uses positions from Step 2 (at actual boundaries) ✅
- If OFF: Recalculates after gaps (places in gap center) ❌

**C0/C1 Transforms**:
- **C0**: Transform from Part0 (body) center to joint in body's local space
- **C1**: Transform from Part1 (appendage) center to joint in appendage's local space
- Both calculated using stored pivot positions (correct boundaries)

### Step 6: Export R6 Metadata (Optional)

**Goal**: Export joint information for Roblox import scripts.

1. **Roblox R6 Joints** panel → **Export for Roblox** section
2. **Click "Export R6 Metadata (JSON)"**
3. **Choose file location**

**What's Exported**:
- Joint names, types, positions
- C0/C1 transforms (matrices)
- Part associations
- Attachment point data

**Use**: Import this JSON in Roblox Studio with import scripts to automatically create Motor6D joints.

### Step 7: Export Model

**Goal**: Export parts as FBX for Roblox Studio.

1. **Select all parts** (or just needed ones)
2. **Export** panel
3. **Choose Format**: FBX (recommended for Roblox)
4. **Enable**: `Include Metadata`
5. **Click "Export Model"**

**Result**: FBX file(s) ready for Roblox Studio import.

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Segment Model                                       │
│ ─────────────────────────────────────────────────────────── │
│ Create vertex groups (mesh still whole)                     │
│ Options: Quick Segment / Auto Segmentation / Manual         │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Split Into Parts ⚡ CRITICAL                        │
│ ─────────────────────────────────────────────────────────── │
│ 1. Calculate pivot positions (from vertex group boundaries) │
│    → Store in metadata                                      │
│ 2. Split mesh into objects                                  │
│ 3. Create gaps (parts move apart)                           │
│ 4. Pivot positions NOT affected by gaps                     │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Clean Edges                                         │
│ ─────────────────────────────────────────────────────────── │
│ Smooth cut boundary edges                                   │
│ (Easier with gaps - can access cut surfaces)                │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: Fill Cuts                                           │
│ ─────────────────────────────────────────────────────────── │
│ Cap open boundaries with material-matched faces             │
│ (Gaps provide space to create geometry)                     │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 5: Create R6 Joints ⚡ CRITICAL                        │
│ ─────────────────────────────────────────────────────────── │
│ Use stored pivot positions (from Step 2)                    │
│ → Joints at actual boundaries (not gap centers)             │
│ → Motor6D with correct C0/C1 transforms                     │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 6: Export                                              │
│ ─────────────────────────────────────────────────────────── │
│ FBX + JSON metadata → Roblox Studio                         │
│ ✅ Joints connect correctly                                 │
│ ✅ Animation works properly                                 │
└─────────────────────────────────────────────────────────────┘
```

## Key Concepts

### Gap Distance

**Purpose**: Creates visible separation between parts for workflow convenience.

**Default**: 0.1 Blender units

**Effects**:
- ✅ Makes cut edges accessible for smoothing
- ✅ Provides space for filling cut faces
- ✅ Allows visual verification of separation
- ❌ Does NOT affect pivot positions

**Adjustment**: 
- Increase for larger models or better visibility
- Decrease for smaller models
- Set to 0 to skip gap creation (not recommended for workflow)

### Pivot Position Storage

**Where**: Object metadata (`pet_stored_attachment_points`)

**Format**: `{(group1_name, group2_name): Vector(position), ...}`

**Example**:
```python
{
    "('body', 'head')": [0.0, 1.5, 0.3],
    "('body', 'leg_front_l')": [0.4, 0.2, -0.1],
    ...
}
```

**Access**: R6 joints operator reads this automatically when `use_stored_pivots=True`

### Material Extraction Order

When filling cuts, color is extracted in this order:

1. **Principled BSDF Base Color** (material nodes)
2. **Material Diffuse Color** (legacy materials)
3. **Vertex Colors** (average of sampled vertices)
4. **Fallback Color** (configurable, default: dark brown)

## Troubleshooting

### Joints Appear in Gap Centers

**Problem**: R6 joints are placed in gap centers instead of boundaries.

**Solution**: 
- Ensure `Use Stored Pivot Positions` is enabled in R6 Joints panel
- Re-split the model (pivot positions stored during split)
- Check that `pet_stored_attachment_points` exists in object metadata

### Gaps Too Large/Small

**Problem**: Parts separated by inappropriate distance.

**Solution**:
- Adjust `Gap Distance` in Split operator (before splitting)
- For large models: Increase gap (0.15-0.2)
- For small models: Decrease gap (0.05-0.1)

### Cut Faces Not Filling

**Problem**: No faces created on cut surfaces.

**Possible Causes**:
- No open boundaries (parts already closed)
- Boundary loops too complex (non-planar)
- Material extraction failed

**Solution**:
- Verify parts have gaps (boundaries should be visible)
- Try adjusting material color settings
- Check Blender console for errors

### Animation Not Working in Roblox

**Problem**: Parts don't rotate correctly around joints.

**Possible Causes**:
- Pivot points in wrong locations (gap centers)
- C0/C1 transforms incorrect
- Joints not properly connected

**Solution**:
- Verify `Use Stored Pivot Positions` was enabled
- Check joint positions (should be at boundaries, not gaps)
- Re-export R6 metadata and verify C0/C1 values

### Segmentation Issues

**"0 vertices" in Results**:
- **Cause**: Vertex groups were created but no vertices assigned
- **Solution**: 
  - Check model orientation (might be rotated wrong)
  - Try different Pet Type
  - Adjust Sensitivity
  - Try Spatial-Only mode if Geometry-Based fails

**Preview shows wrong parts**:
- **Cause**: Model doesn't match template assumptions
- **Solution**:
  - Try different Pet Type
  - Adjust Sensitivity (lower = stricter boundaries)
  - Manually adjust vertex groups in Weight Paint mode

**Can't see vertex groups in Preview**:
- **Solution**: 
  - Make sure you're in Weight Paint mode
  - Check Properties panel → Object Data → Vertex Groups
  - Select a vertex group from the dropdown
  - The selected group will be highlighted in red

**Want to start over**:
- Click "Clear Existing Groups" checkbox
- Click Preview or Segment Model again

## Best Practices

1. **Always use stored pivot positions** for R6 joints
2. **Keep gaps small** (0.1 default is usually good)
3. **Clean edges before filling** (smoother results)
4. **Use material color extraction** (better visual matching)
5. **Verify pivot positions** visually before exporting
6. **Test in Roblox Studio** before final export
7. **Always preview first** before splitting
8. **Keep Auto Split OFF** until you're satisfied
9. **Use Weight Paint mode** to visualize and adjust
10. **Check vertex counts** - empty groups (0 vertices) won't split properly

## Quick Reference

| Step | Panel | Key Button | Critical Setting |
|------|-------|------------|------------------|
| 1. Segment | Quick Segment / Segmentation | Apply Cuts & Create Groups | Pet Type |
| 2. Split | Quick Segment / Segmentation | Split Into Parts | Gap Distance, Create Pivots |
| 3. Clean | Post-Split Cleanup | Smooth Cut Edges | Iterations |
| 4. Fill | Post-Split Cleanup | Fill Cut Faces | Use Material Color |
| 5. R6 Joints | Roblox R6 Joints | Create R6 Joints | **Use Stored Pivot Positions** ⚠️ |
| 6. Export | Export | Export Model | Format: FBX |

## Summary

The complete workflow ensures:
- ✅ Proper mesh segmentation and splitting
- ✅ Clean, filled cut surfaces
- ✅ **Correct pivot point placement for Roblox R6**
- ✅ Motor6D joints at attachment boundaries
- ✅ Animation-ready models for Roblox Studio

**Remember**: Where appendage separates from body = Where pivot point must be. This is calculated BEFORE gaps and stored for R6 joint creation.
