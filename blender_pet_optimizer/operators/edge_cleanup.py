"""
Edge cleanup operators for post-split workflow
Smooths cut edges and prepares boundaries for filling
"""

import bpy
import bmesh
from bpy.types import Operator
from bpy.props import IntProperty, BoolProperty, FloatProperty
from mathutils import Vector


def build_spatial_index(stored_boundaries, tolerance=0.001):
    """
    Build a spatial index from stored boundary coordinates for O(n) lookup.
    
    Args:
        stored_boundaries: List of [[v1_co, v2_co], ...] coordinate pairs
        tolerance: Distance tolerance for coordinate matching
    
    Returns:
        dict: Spatial index mapping rounded coordinate tuples to sets of exact coordinates
    """
    spatial_index = {}
    
    for boundary_pair in stored_boundaries:
        if len(boundary_pair) != 2:
            continue
        
        v1_co = boundary_pair[0]
        v2_co = boundary_pair[1]
        
        for co in [v1_co, v2_co]:
            if len(co) < 3:
                continue
            # Create a key based on rounded coordinates
            key = (
                round(co[0] / tolerance),
                round(co[1] / tolerance),
                round(co[2] / tolerance)
            )
            if key not in spatial_index:
                spatial_index[key] = set()
            spatial_index[key].add((co[0], co[1], co[2]))
    
    return spatial_index


def coord_in_spatial_index(co, spatial_index, tolerance=0.001):
    """
    Check if a coordinate is in the spatial index (within tolerance).
    
    Args:
        co: Coordinate to check (Vector or tuple)
        spatial_index: Spatial index from build_spatial_index()
        tolerance: Distance tolerance for matching
    
    Returns:
        bool: True if coordinate is in the index
    """
    # Check the main cell and neighboring cells (to handle boundary cases)
    key = (
        round(co[0] / tolerance),
        round(co[1] / tolerance),
        round(co[2] / tolerance)
    )
    
    # Check main cell and 26 neighbors (3x3x3 cube)
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            for dz in [-1, 0, 1]:
                neighbor_key = (key[0] + dx, key[1] + dy, key[2] + dz)
                if neighbor_key in spatial_index:
                    for stored_co in spatial_index[neighbor_key]:
                        # Check actual distance
                        dist = (
                            (co[0] - stored_co[0]) ** 2 +
                            (co[1] - stored_co[1]) ** 2 +
                            (co[2] - stored_co[2]) ** 2
                        ) ** 0.5
                        if dist < tolerance:
                            return True
    
    return False


def identify_separation_boundary_edges(bm, obj, tolerance=0.001):
    """
    Identify edges that are actual separation boundaries (created during split operation).
    
    Uses stored boundary data (pet_separation_boundary_edges) to identify only the edges
    that were at vertex group boundaries during splitting. This ensures we only smooth
    actual cut boundaries, not random edges.
    
    Args:
        bm: bmesh object
        obj: Blender object (must have pet_separation_boundary_edges for accurate detection)
        tolerance: Distance tolerance for coordinate matching
    
    Returns:
        set: Set of bmesh edges that are separation boundaries
    """
    separation_edges = set()
    
    # Ensure lookup tables
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    
    # Check if object has stored separation boundary info
    stored_boundaries = obj.get("pet_separation_boundary_edges", None) if obj else None
    
    if stored_boundaries and len(stored_boundaries) > 0:
        # PRIMARY METHOD: Use stored boundary data with spatial hashing
        # This is O(n) instead of O(n*m)
        
        # Build spatial index from stored boundaries
        spatial_index = build_spatial_index(stored_boundaries, tolerance)
        
        if not spatial_index:
            # No valid boundary data, fall back to one-face rule
            print("[Edge Cleanup] Warning: Stored boundary data is empty, falling back to one-face rule")
            for edge in bm.edges:
                if len(edge.link_faces) == 1:
                    separation_edges.add(edge)
            return separation_edges
        
        # Find edges that:
        # 1. Have exactly one face (are boundary edges)
        # 2. Both vertices match stored boundary coordinates
        matched_count = 0
        for edge in bm.edges:
            # Must be a boundary edge (one face)
            if len(edge.link_faces) != 1:
                continue
            
            v1_co = edge.verts[0].co
            v2_co = edge.verts[1].co
            
            # Check if BOTH vertices are in the stored boundary data
            v1_match = coord_in_spatial_index(v1_co, spatial_index, tolerance)
            v2_match = coord_in_spatial_index(v2_co, spatial_index, tolerance)
            
            if v1_match and v2_match:
                separation_edges.add(edge)
                matched_count += 1
        
        print(f"[Edge Cleanup] Found {matched_count} edges matching stored boundary data (from {len(stored_boundaries)} stored boundaries)")
        
        # If no edges matched, there might be a coordinate mismatch (e.g., gaps were created)
        # Fall back to one-face rule but warn the user
        if not separation_edges:
            print("[Edge Cleanup] Warning: No edges matched stored boundaries, falling back to one-face rule")
            for edge in bm.edges:
                if len(edge.link_faces) == 1:
                    separation_edges.add(edge)
    else:
        # FALLBACK: No stored boundary data, use one-face rule
        # This is less accurate but works for backwards compatibility
        print("[Edge Cleanup] No stored boundary data found, using one-face rule (may include non-cut edges)")
        for edge in bm.edges:
            if len(edge.link_faces) == 1:
                separation_edges.add(edge)
    
    return separation_edges


def identify_separation_boundary_edges_fallback(bm, obj):
    """
    Fallback method: Identify edges that are likely separation boundaries.
    Used when stored boundary info is not available (backwards compatibility).
    
    WARNING: This method is less accurate than using stored boundary data.
    It may include false positives (edges that weren't part of the original cut).
    For best results, ensure objects have pet_separation_boundary_edges data from
    the split operation.
    
    Strategy:
    - Select boundary edges (edges with only one face)
    - This includes all open edges, not just cut boundaries
    - May include edges that existed before splitting or were created by other operations
    
    Args:
        bm: bmesh object
        obj: Blender object
    
    Returns:
        set: Set of bmesh edges that are likely separation boundaries
        (may include false positives)
    """
    boundary_edges = set()
    
    # Ensure lookup tables
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    
    # Get all boundary edges (edges with only one face)
    for edge in bm.edges:
        if len(edge.link_faces) == 1:
            boundary_edges.add(edge)
    
    # Note: This is a simple fallback that may include edges that weren't
    # part of the original vertex group split. For accurate results, use
    # objects with stored pet_separation_boundary_edges data.
    
    return boundary_edges


class PET_OT_smooth_cut_edges(Operator):
    """
    Smooth cut edges on selected split parts for cleaner boundaries.
    
    This operator smooths the jagged edges created when vertex groups are separated
    during the split operation. Smoothing creates cleaner, more uniform cut surfaces
    that are better suited for subsequent filling operations.
    
    HOW SMOOTHING WORKS:
    
    The smoothing process uses Blender's vertices_smooth operator, which applies
    a Laplacian smoothing algorithm:
    
    1. Edge Selection Process:
       - Identifies separation boundary edges using stored pet_separation_boundary_edges data
       - Validates edges have exactly one face (open boundary requirement)
       - Matches edge vertices to stored boundary coordinates using spatial hashing (O(n))
       - Only selects edges that are actual vertex cut boundaries
       - Falls back to one-face rule if no stored data exists
    
    2. Smooth Factor (0.0 - 1.0):
       - Controls the strength of smoothing per iteration
       - 0.0 = No movement (no smoothing applied)
       - 1.0 = Full smoothing (vertex moves completely to average of neighbors)
       - Values between = Partial smoothing (blends original position with smoothed position)
       - Formula: new_position = original_position * (1 - factor) + smoothed_position * factor
       - Default: 1.0 (full smoothing for maximum effect)
    
    3. Iterations (1 - 10):
       - Number of times the smoothing algorithm is applied
       - Each iteration applies one smoothing pass to selected vertices
       - More iterations = smoother result but may over-smooth fine details
       - Recommended: 2-4 iterations for cut boundaries
       - Default: 2 iterations (good balance between smoothness and detail preservation)
    
    4. Smoothing Algorithm (Blender's vertices_smooth):
       - For each selected vertex, calculates the average position of all connected vertices
       - Moves the vertex toward this average by the smooth_factor amount
       - Repeats this process for the specified number of iterations
       - Only affects selected vertices/edges (boundary edges in this case)
    
    WHY IT WORKS FOR CUT BOUNDARIES:
    
    - Cut boundaries are often jagged from the split operation
    - Smoothing averages the positions along the boundary loop
    - Creates cleaner, more uniform cut surfaces
    - Makes subsequent fill operations produce better results with fewer artifacts
    - Reduces visual noise and improves mesh quality
    
    PERFORMANCE:
    
    - Uses optimized O(n) spatial hashing for boundary edge identification
    - Only processes actual cut boundaries (not all edges)
    - Efficient for large meshes with many boundary edges
    """
    bl_idname = "pet.smooth_cut_edges"
    bl_label = "Smooth Cut Edges"
    bl_options = {'REGISTER', 'UNDO'}
    
    iterations: IntProperty(
        name="Iterations",
        description="Number of smoothing iterations. Each iteration applies one smoothing pass. More iterations = smoother result but may over-smooth details. Recommended: 2-4 for cut boundaries",
        default=2,
        min=1,
        max=10
    )
    
    smooth_factor: bpy.props.FloatProperty(
        name="Smooth Factor",
        description="Strength of smoothing per iteration (0.0 = no smoothing, 1.0 = full smoothing). Values between blend original position with smoothed position. Formula: new_pos = original * (1 - factor) + smoothed * factor",
        default=1.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )
    
    only_boundary: BoolProperty(
        name="Only Boundary Edges",
        description="Only smooth edges that are on boundaries (edges with only one face). When enabled, only actual cut boundaries are smoothed. When disabled, all edges are smoothed (not recommended)",
        default=True
    )
    
    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'ERROR'}, "Please select mesh objects with cut edges to smooth")
            return {'CANCELLED'}
        
        total_edges_smoothed = 0
        processed_objects = 0
        
        for obj in selected_objects:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            # Select this object
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            # Enter edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Identify actual separation boundary edges (created during split)
            bm = bmesh.from_edit_mesh(obj.data)
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            
            # Deselect all first
            for edge in bm.edges:
                edge.select = False
            
            # Get separation boundary edges (actual cuts from split operation)
            separation_edges = identify_separation_boundary_edges(bm, obj)
            
            # Fallback if no stored boundary info (backwards compatibility)
            if not separation_edges:
                separation_edges = identify_separation_boundary_edges_fallback(bm, obj)
            
            # Select separation edges
            boundary_edges = list(separation_edges)
            for edge in boundary_edges:
                edge.select = True
            
            # If not only_boundary, also select all other edges
            if not self.only_boundary:
                for edge in bm.edges:
                    if edge not in separation_edges:
                        edge.select = True
                        if edge not in boundary_edges:
                            boundary_edges.append(edge)
            
            if not boundary_edges:
                bmesh.update_edit_mesh(obj.data)
                bm.free()
                bpy.ops.object.mode_set(mode='OBJECT')
                continue
            
            total_edges_smoothed += len(boundary_edges)
            
            # Update edit mesh with selection
            bmesh.update_edit_mesh(obj.data)
            bm.free()
            
            # Apply smoothing iterations
            for i in range(self.iterations):
                # Use Blender's smooth operator
                # This smooths selected edges/vertices
                try:
                    bpy.ops.mesh.vertices_smooth(
                        factor=self.smooth_factor,
                        repeat=1
                    )
                except RuntimeError:
                    # If vertices_smooth fails, try alternative method
                    bpy.ops.mesh.select_mode(type='VERT')
                    bpy.ops.mesh.vertices_smooth(
                        factor=self.smooth_factor,
                        repeat=1
                    )
                    bpy.ops.mesh.select_mode(type='EDGE')
            
            # Return to object mode
            bpy.ops.object.mode_set(mode='OBJECT')
            processed_objects += 1
        
        # Restore selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_objects:
            obj.select_set(True)
        if selected_objects:
            context.view_layer.objects.active = selected_objects[0]
        
        if processed_objects > 0:
            self.report({'INFO'}, f"Smoothed {total_edges_smoothed} boundary edges on {processed_objects} object(s)")
        else:
            self.report({'WARNING'}, "No boundary edges found to smooth")
        
        return {'FINISHED'}


class PET_OT_select_cut_boundaries(Operator):
    """Select all boundary edges (cut surfaces) on selected objects"""
    bl_idname = "pet.select_cut_boundaries"
    bl_label = "Select Cut Boundaries"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'ERROR'}, "Please select mesh objects")
            return {'CANCELLED'}
        
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        total_edges = 0
        
        for obj in selected_objects:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            bpy.ops.object.mode_set(mode='EDIT')
            
            bm = bmesh.from_edit_mesh(obj.data)
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            
            # Deselect all first
            for edge in bm.edges:
                edge.select = False
            
            # Get actual separation boundary edges (cuts from split operation)
            separation_edges = identify_separation_boundary_edges(bm, obj)
            
            # Fallback if no stored boundary info (backwards compatibility)
            if not separation_edges:
                separation_edges = identify_separation_boundary_edges_fallback(bm, obj)
            
            # Select separation edges
            boundary_count = len(separation_edges)
            for edge in separation_edges:
                edge.select = True
            
            total_edges += boundary_count
            
            bmesh.update_edit_mesh(obj.data)
            bm.free()
            
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Restore selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_objects:
            obj.select_set(True)
        if selected_objects:
            context.view_layer.objects.active = selected_objects[0]
            bpy.ops.object.mode_set(mode='EDIT')
        
        self.report({'INFO'}, f"Selected {total_edges} boundary edges on {len(selected_objects)} object(s)")
        return {'FINISHED'}


class PET_OT_create_gaps(Operator):
    """Create gaps between split parts for visual review"""
    bl_idname = "pet.create_gaps"
    bl_label = "Create Gaps"
    bl_options = {'REGISTER', 'UNDO'}
    
    gap_distance: FloatProperty(
        name="Gap Distance",
        description="Distance to separate parts",
        default=0.1,
        min=0.0,
        max=10.0,
        step=0.01,
        precision=3
    )
    
    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if len(selected_objects) < 2:
            self.report({'ERROR'}, "Select at least 2 split parts")
            return {'CANCELLED'}
        
        # Find body object (largest, or one with 'body' in name)
        body_obj = None
        for obj in selected_objects:
            name_lower = obj.name.lower()
            if 'body' in name_lower or 'torso' in name_lower:
                body_obj = obj
                break
        
        # Fallback: use largest object
        if not body_obj:
            body_obj = max(selected_objects, key=lambda o: len(o.data.vertices) if o.data.vertices else 0)
        
        # Calculate body center using bounding box
        body_center = Vector(body_obj.location)
        if body_obj.data.vertices:
            body_bbox = [body_obj.matrix_world @ Vector(corner) for corner in body_obj.bound_box]
            body_center = sum(body_bbox, Vector((0, 0, 0))) / len(body_bbox)
        
        # Move non-body parts away from body
        moved_count = 0
        for part_obj in selected_objects:
            if part_obj == body_obj:
                continue
            
            # Calculate part center
            part_center = Vector(part_obj.location)
            if part_obj.data.vertices:
                part_bbox = [part_obj.matrix_world @ Vector(corner) for corner in part_obj.bound_box]
                part_center = sum(part_bbox, Vector((0, 0, 0))) / len(part_bbox)
            
            # Direction from body to part
            direction = part_center - body_center
            if direction.length > 0.001:
                direction.normalize()
            else:
                # Fallback: use object location difference
                direction = Vector(part_obj.location) - Vector(body_obj.location)
                if direction.length > 0.001:
                    direction.normalize()
                else:
                    direction = Vector((0, 1, 0))
            
            # Store original position
            original_location = Vector(part_obj.location)
            part_obj["pet_original_location"] = list(original_location)
            
            # Move part
            offset = direction * self.gap_distance
            part_obj.location = original_location + offset
            
            # Store metadata
            part_obj["pet_gap_offset"] = list(offset)
            part_obj["pet_has_gap"] = True
            moved_count += 1
        
        self.report({'INFO'}, f"Created {self.gap_distance:.3f} gaps for {moved_count} part(s)")
        return {'FINISHED'}


classes = [
    PET_OT_smooth_cut_edges,
    PET_OT_select_cut_boundaries,
    PET_OT_create_gaps,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
