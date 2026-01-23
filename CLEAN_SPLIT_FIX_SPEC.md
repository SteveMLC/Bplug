# Clean Split Fix - Complete Code Changes Specification

## Problem Summary
The clean split operator works perfectly for the first vertex group (head) but fails for subsequent groups (body, legs, tail) because it uses original mesh vertex indices after Blender has re-indexed the mesh during `separate()` operations.

## Root Cause
- Phase 1 builds `vertex_mask` using original mesh vertex indices
- Phase 2 calls `bpy.ops.mesh.separate()` for each vertex group
- After each `separate()`, Blender re-indexes remaining vertices
- Code at line 1926 uses `v.index` (from modified mesh) to index into `vertex_mask` (using original indices)
- This works for first group (head) but fails for all subsequent groups

## Solution
Use coordinate-based mapping to match current mesh vertices back to original mesh indices, similar to the pattern in `calculate_attachment_points_from_vertex_groups()`.

---

## File: `blender_pet_optimizer/operators/mesh_splitter.py`

### Change 1: Store Original Vertex Coordinates (Phase 1)

**Location:** After line 1820, insert before line 1822

**Code to Add:**
```python
            # Store original vertex coordinates for coordinate-based mapping
            # CRITICAL: After each separate(), Blender re-indexes vertices
            # We need coordinates to map current vertices back to original indices
            original_vertex_coords = {}
            for vert_idx, vertex in enumerate(mesh.vertices):
                original_vertex_coords[vert_idx] = Vector(vertex.co)
            
            # Build coordinate-to-index lookup for fast matching
            # Use rounded coordinates as keys to handle floating-point precision
            coord_tolerance = 0.0001
            original_coord_to_index = {}
            for vert_idx, coord in original_vertex_coords.items():
                # Round coordinates to tolerance for matching
                coord_key = (
                    round(coord.x / coord_tolerance) * coord_tolerance,
                    round(coord.y / coord_tolerance) * coord_tolerance,
                    round(coord.z / coord_tolerance) * coord_tolerance
                )
                original_coord_to_index[coord_key] = vert_idx
```

**Context:**
```python
                vertex_group_masks[vg.name] = mask
            
            # [INSERT CODE HERE]
            
            # Assign each face to exactly ONE vertex group based on vertex membership
```

---

### Change 2: Build Current-to-Original Mapping (Phase 2)

**Location:** After line 1909, insert before line 1911

**Code to Add:**
```python
                # Build mapping from current mesh vertices to original mesh indices
                # CRITICAL: After each separate(), Blender re-indexes vertices
                # We must use coordinates to match current vertices back to original indices
                current_to_original_map = {}  # {current_bm_vert: original_mesh_index}
                coord_tolerance = 0.0001
                
                for bm_vert in bm.verts:
                    # Try direct index first (works for first iteration only)
                    original_idx = None
                    if bm_vert.index < len(original_vertex_coords):
                        orig_coord = original_vertex_coords[bm_vert.index]
                        if (bm_vert.co - orig_coord).length < coord_tolerance:
                            original_idx = bm_vert.index
                    
                    # Fallback: search by coordinate matching
                    if original_idx is None:
                        coord_key = (
                            round(bm_vert.co.x / coord_tolerance) * coord_tolerance,
                            round(bm_vert.co.y / coord_tolerance) * coord_tolerance,
                            round(bm_vert.co.z / coord_tolerance) * coord_tolerance
                        )
                        original_idx = original_coord_to_index.get(coord_key)
                        
                        # If still not found, do linear search (should be rare)
                        if original_idx is None:
                            for orig_idx, orig_coord in original_vertex_coords.items():
                                if (bm_vert.co - orig_coord).length < coord_tolerance:
                                    original_idx = orig_idx
                                    break
                    
                    if original_idx is not None:
                        current_to_original_map[bm_vert] = original_idx
                    else:
                        # This should never happen, but log a warning
                        print(f"[Clean Split] WARNING: Could not map vertex at {bm_vert.co} to original mesh")
```

**Context:**
```python
                bm = bmesh.from_edit_mesh(current_mesh)
                bm.faces.ensure_lookup_table()
                bm.verts.ensure_lookup_table()
                
                # [INSERT CODE HERE]
                
                # Select faces based on vertex group membership
```

---

### Change 3: Fix Vertex Mask Lookup in Face Selection

**Location:** Replace lines 1925-1926

**Old Code:**
```python
                        verts_in_group = sum(1 for v in face.verts 
                                           if v.index < len(vertex_mask) and vertex_mask[v.index])
```

**New Code:**
```python
                        # Use coordinate-based mapping to get original vertex index
                        # CRITICAL: v.index is from the modified mesh, but vertex_mask uses original indices
                        verts_in_group = 0
                        for v in face.verts:
                            original_idx = current_to_original_map.get(v)
                            if original_idx is not None and original_idx < len(vertex_mask) and vertex_mask[original_idx]:
                                verts_in_group += 1
```

**Context:**
```python
                    else:
                        # Appendages: Select faces where majority of vertices are in this group
                        # Use vertex membership to determine selection (robust after mesh changes)
                        # [REPLACE THESE 2 LINES]
                        total_verts = len(face.verts)
```

---

## Summary of Changes

### Lines Modified
- **Line ~1820**: Add original vertex coordinate storage (Phase 1)
- **Line ~1909**: Add current-to-original mapping (Phase 2)
- **Lines 1925-1926**: Fix vertex mask lookup

### Lines Added
- ~35 lines of new code
- ~5 lines of comments

### Lines Removed
- 2 lines (replaced with improved logic)

### No Changes Required
- UI panels (`panels.py`) - no changes needed
- Settings/preferences - no changes needed
- Other operators - no changes needed
- Imports - all required imports already present

---

## Testing Checklist

- [ ] Head vertex group still works correctly (first group, should be unchanged)
- [ ] Body vertex group now captures all vertices correctly
- [ ] Leg vertex groups (front_l, front_r, back_l, back_r) capture all vertices
- [ ] Tail vertex group captures all vertices
- [ ] No orphaned vertices remain after split
- [ ] Works with `strict_mode=True` (100% vertex match)
- [ ] Works with `strict_mode=False` (majority vertex match)
- [ ] Works with different vertex group processing orders
- [ ] Performance acceptable for large meshes (>10k vertices)
- [ ] Coordinate matching handles floating-point precision correctly
- [ ] Standard split operator (`PET_OT_split_by_vertex_groups`) unaffected
- [ ] UI panels and buttons still function correctly

---

## Implementation Order

1. **Change 1** (Phase 1): Store original vertex coordinates
2. **Change 2** (Phase 2): Build current-to-original mapping
3. **Change 3** (Phase 2): Fix vertex mask lookup

All changes must be made together - partial implementation will not work correctly.

---

## Notes

- Coordinate tolerance (0.0001) matches existing codebase patterns
- Uses same approach as `calculate_attachment_points_from_vertex_groups()` for consistency
- Performance impact is minimal: O(n) coordinate mapping built once per iteration
- Dictionary lookup is O(1) for coordinate matching
- Linear search fallback should rarely be needed
