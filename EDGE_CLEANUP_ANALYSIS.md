# Edge Cleanup UI Fix - Analysis & Recommendations

## Problem Summary
1. **UI Sliders Don't Work**: Iterations and Smooth Factor sliders reset on every UI redraw
2. **Too Aggressive Smoothing**: Default settings (factor=1.0, iterations=2) cause gaps in mesh
3. **No Control Over Smoothing Strength**: No way to reduce aggressiveness before filling

## Root Cause Analysis

### Issue 1: Non-Functional Sliders
**Root Cause**: Properties accessed on operator instance created inline:
```python
smooth_op = edge_box.operator("pet.smooth_cut_edges", ...)
edge_box.prop(smooth_op, "iterations")  # Resets to default on redraw!
```

**Solution**: Use Scene PropertyGroup (matches existing codebase pattern)
- ✅ Pattern already used: `PET_SegmentationSettings`, `PET_SplitSettings`, etc.
- ✅ Provides persistence across UI redraws
- ✅ Follows established codebase conventions

### Issue 2: Aggressive Smoothing
**Current Defaults**:
- `smooth_factor = 1.0` (full smoothing - maximum movement)
- `iterations = 2`
- No constraints on vertex movement

**Impact**: Vertices move too far, creating gaps between split parts

## Plan Review - Issues Found

### ✅ Good Aspects
1. **PropertyGroup Pattern**: Correct approach, matches codebase
2. **Backwards Compatibility**: Fallback to operator properties is good
3. **Lower Default Factor**: Changing to 0.5 is sensible

### ⚠️ Issues & Improvements Needed

#### Issue 1: Over-Engineering Custom Smoothing
**Problem**: Plan proposes full custom smoothing implementation
- Complex to implement and maintain
- Slower than Blender's optimized C code
- Requires keeping bmesh alive (current code frees it before smoothing)

**Better Approach**: Hybrid method
1. Store original vertex positions
2. Use Blender's `bpy.ops.mesh.vertices_smooth` (fast, optimized)
3. Apply constraints post-smoothing via bmesh:
   - Clamp displacement if `max_vertex_displacement > 0`
   - Restore positions for sharp vertices if `preserve_sharp_angles` enabled

**Benefits**:
- Simpler implementation
- Faster (uses Blender's optimized code)
- Easier to maintain
- Less code to test

#### Issue 2: Sharp Angle Preservation Implementation
**Current Plan**: Implement in custom smoothing algorithm

**Better Approach**: Pre-filter selection
1. Before smoothing: detect vertices at sharp angles
2. Deselect those vertices (or mark for reduced smoothing)
3. Apply Blender's smoothing
4. Optionally: restore original positions for sharp vertices

**Code Reuse**: `algorithms.detect_sharp_edges()` already exists and can be adapted

#### Issue 3: Max Displacement Constraint
**Current Plan**: Implement in custom smoothing

**Better Approach**: Post-processing
1. Store original positions before smoothing
2. Apply Blender's smoothing
3. Re-acquire bmesh
4. For each vertex: clamp movement to `max_displacement`
5. Update mesh

**Simpler and more reliable**

#### Issue 4: Bmesh Lifecycle
**Current Code**:
```python
bmesh.update_edit_mesh(obj.data)
bm.free()  # Freed before smoothing
# Then uses bpy.ops.mesh.vertices_smooth
```

**For Constraints**: Need to re-acquire bmesh after smoothing to apply constraints
- This is fine and doesn't require major refactoring
- Can use `bmesh.from_edit_mesh()` again after smoothing

#### Issue 5: Missing Error Handling
**Need**: Try/except for AttributeError when scene properties don't exist (addon reload)
- Pattern already exists in `mesh_splitter.py` lines 508-519
- Should be included

## Revised Implementation Strategy

### Phase 1: Fix UI (Essential)
1. Create `PET_EdgeCleanupSettings` PropertyGroup
2. Register on Scene
3. Update UI to use scene properties
4. Update operator to read from scene with fallback
5. **Lower default smooth_factor to 0.5**

### Phase 2: Add Constraints (Recommended)
1. **Max Displacement**: Post-smoothing clamp
   - Store original positions
   - Apply smoothing
   - Re-acquire bmesh, clamp movement
   
2. **Sharp Angle Preservation**: Pre-filter + post-restore
   - Detect sharp vertices before smoothing
   - Option A: Deselect them (simpler)
   - Option B: Restore positions after smoothing (more precise)

3. **Keep it Simple**: Use Blender's operator, add constraints around it

### Phase 3: Advanced Options (Optional)
- Constrained smoothing mode (if Phase 2 isn't sufficient)
- Per-vertex smoothing factor based on angle
- Progressive smoothing (multiple passes with increasing factor)

## Recommended Changes to Plan

### 1. Simplify Constrained Smoothing
**Instead of**: Full custom smoothing algorithm
**Use**: Blender's operator + post-processing constraints

### 2. Implementation Order
1. **First**: Fix UI sliders (Phase 1) - solves immediate problem
2. **Second**: Add max displacement constraint - prevents gaps
3. **Third**: Add sharp angle preservation - improves quality

### 3. Code Structure
```python
def apply_constrained_smoothing(bm, selected_verts, settings):
    # Store original positions
    original_positions = {v.index: v.co.copy() for v in selected_verts}
    
    # Update edit mesh, free bmesh
    bmesh.update_edit_mesh(obj.data)
    bm.free()
    
    # Use Blender's fast smoothing
    for i in range(settings.iterations):
        bpy.ops.mesh.vertices_smooth(factor=settings.smooth_factor, repeat=1)
    
    # Re-acquire bmesh for constraints
    bm = bmesh.from_edit_mesh(obj.data)
    
    # Apply constraints
    if settings.max_vertex_displacement > 0:
        clamp_vertex_displacement(bm, selected_verts, original_positions, 
                                   settings.max_vertex_displacement)
    
    if settings.preserve_sharp_angles:
        restore_sharp_vertices(bm, selected_verts, original_positions,
                               settings.sharp_angle_threshold)
    
    bmesh.update_edit_mesh(obj.data)
    bm.free()
```

### 4. Remove Unnecessary Complexity
- Don't implement full Laplacian smoothing from scratch
- Don't keep bmesh alive during smoothing
- Use Blender's optimized operators where possible

## Risk Assessment

### Low Risk ✅
- PropertyGroup creation and registration
- UI updates
- Reading from scene properties
- Lowering default smooth_factor

### Medium Risk ⚠️
- Post-smoothing constraint application (needs testing)
- Sharp angle detection on boundary vertices (may need adaptation)

### High Risk ❌
- Full custom smoothing (unnecessary complexity)
- Keeping bmesh alive during operator calls (potential conflicts)

## Testing Considerations

1. **Backwards Compatibility**: Ensure operator still works when called programmatically
2. **Performance**: Verify constraints don't significantly slow down smoothing
3. **Edge Cases**: 
   - Meshes with no sharp angles
   - Very small meshes
   - Very large meshes
   - Meshes with existing gaps

## Conclusion

**The plan is sound but over-engineered**. The core fix (PropertyGroup) is correct, but the constrained smoothing implementation should be simplified to use Blender's operators with post-processing constraints rather than a full custom implementation.

**Recommended Approach**:
1. ✅ Fix UI sliders (PropertyGroup)
2. ✅ Lower default smooth_factor to 0.5
3. ✅ Add max displacement constraint (post-processing)
4. ✅ Add sharp angle preservation (pre-filter + post-restore)
5. ❌ Skip full custom smoothing implementation (unnecessary)

This provides all the benefits with much less complexity and better performance.
