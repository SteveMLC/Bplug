# Mesh Splitting & Fidelity Improvement Plan

## Goals
- Preserve 100% mesh fidelity (geometry, UVs, colors, materials) when splitting
- Ensure split parts work correctly in Roblox
- Provide non-destructive workflow options
- Optimize attachment/pivot point placement

---

## Key Decisions

### 1. Original Mesh Handling
**Decision**: Keep original by default, allow deletion via option
- **Rationale**: Non-destructive workflow, easier debugging, supports undo
- **Implementation**: Add `keep_original` BoolProperty (default=True)
- **Location**: `PET_OT_split_by_vertex_groups` operator

### 2. Data Preservation Strategy
**Decision**: Trust `bpy.ops.mesh.separate()` with verification
- **Rationale**: Blender's operator is well-tested and preserves most data
- **Implementation**: 
  - Use `separate()` as primary method
  - Add optional verification step using manual copy functions
  - Only use manual copying if verification fails
- **Location**: `mesh_splitter.py` - modify `execute()` method

### 3. Pivot/Attachment Point Timing
**Decision**: Calculate attachment points BEFORE splitting, refine AFTER
- **Rationale**: 
  - Before: Use vertex group boundaries for precise placement
  - After: Link pivots to actual split objects and refine positions
- **Implementation**: 
  - Pre-split: Calculate attachment positions from vertex group boundaries
  - Post-split: Create Empty objects, parent to split objects, adjust if needed
- **Location**: New method `calculate_attachments_before_split()`

### 4. Priority: Accuracy vs Performance
**Decision**: Accuracy first, with performance optimizations
- **Rationale**: Fidelity is critical for Roblox import
- **Implementation**: 
  - Use efficient Blender operators where possible
  - Add progress reporting for large meshes
  - Batch operations where safe
- **Location**: All operators

---

## Implementation Changes

### Change 1: Enhanced Split Operator with Options

**File**: `blender_pet_optimizer/operators/mesh_splitter.py`

**Changes**:
1. Add `keep_original` property (default=True)
2. Add `verify_data_preservation` property (default=True)
3. Improve `split_mesh_by_vertex_group()` to use `bpy.ops.mesh.separate()` correctly
4. Add verification function to check UV/material/color preservation
5. Add option to delete original after successful split

### Change 2: Pre-Split Attachment Calculation

**File**: `blender_pet_optimizer/operators/mesh_splitter.py`

**New Method**: `calculate_attachment_points_from_vertex_groups()`
- Calculate attachment positions from vertex group boundaries
- Store as metadata in original object
- Use these positions when creating pivots after splitting

### Change 3: Improved Split Workflow

**Current Flow** (problematic):
```
1. Select vertices by group
2. Duplicate selection
3. Separate
4. Repeat for each group (issues with mode switching)
```

**New Flow** (recommended):
```
1. For each vertex group:
   a. Select vertices (weight > 0.5)
   b. Select connected faces
   c. Duplicate and separate in one operation
2. Verify all split objects have required data
3. Create attachment points using pre-calculated positions
4. Optionally delete original
```

### Change 4: Data Verification Function

**New Function**: `verify_split_data_preservation(original_obj, split_obj, vertex_group_name)`
- Check UV layer count matches
- Verify material assignments preserved
- Validate color attributes exist
- Report any missing data

---

## Code Improvements Needed

### Issue 1: Current split logic has mode switching problems
**Problem**: Switching between EDIT/OBJECT mode for each vertex group causes issues
**Solution**: Process all groups at once or use bmesh directly

### Issue 2: Manual copy functions are incomplete
**Problem**: `copy_uv_layers()`, `copy_color_attributes()`, `copy_materials()` exist but aren't used
**Solution**: 
- Use as verification/fallback
- Complete implementation for edge cases

### Issue 3: Pivot points calculated after splitting only
**Problem**: Using bounding box centers (imprecise)
**Solution**: Calculate from vertex group boundaries before splitting

### Issue 4: Original object handling unclear
**Problem**: Comment says "Remove original object if all parts were split" but not implemented
**Solution**: Add explicit option with proper deletion logic

---

## Recommended Workflow for Roblox Export

```
1. Import 3D model into Blender
2. Segment model (creates vertex groups) [NON-DESTRUCTIVE]
3. OPTIONAL: Optimize mesh (applies to original)
4. Calculate attachment points from vertex groups
5. Split by vertex groups (creates separate objects) [DESTRUCTIVE]
   - Verify data preservation
   - Create attachment points linked to split objects
   - Optionally delete original
6. Standardize parts (normalize scale/orientation)
7. Create rigging (armature from vertex groups)
8. Export parts to Roblox (FBX/OBJ)
```

---

## Testing Checklist

- [ ] Split preserves all UV layers
- [ ] Split preserves material assignments
- [ ] Split preserves vertex colors/color attributes
- [ ] Original mesh can be kept or deleted
- [ ] Attachment points positioned correctly
- [ ] Split objects export correctly to FBX
- [ ] Imported into Roblox with correct geometry
- [ ] Materials/textures visible in Roblox
- [ ] Pivot points work for attachment in Roblox

---

## Questions for Further Clarification

1. **Export format preference**: FBX or OBJ? (FBX recommended for Roblox)
2. **Scale normalization**: Should parts be normalized before or after splitting?
3. **Vertex group overlap**: How to handle vertices in multiple groups?
4. **Boundary geometry**: Should boundary vertices be duplicated or shared?
5. **Rigging timing**: Create armature before or after splitting?

---

## Next Steps

1. ✅ Document decisions (this file)
2. ⏳ Implement `keep_original` option
3. ⏳ Implement pre-split attachment calculation
4. ⏳ Add data verification function
5. ⏳ Fix split workflow to avoid mode switching issues
6. ⏳ Test with actual Roblox model
7. ⏳ Update UI panel with new options