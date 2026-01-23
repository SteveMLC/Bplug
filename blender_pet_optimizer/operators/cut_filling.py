"""
Cut face filling operators
Fills open boundaries on split parts with material-matched faces
"""

import bpy
import bmesh
import time
from bpy.types import Operator
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, IntProperty, FloatProperty
from mathutils import Vector


# Safety constants
MAX_ITERATIONS_PER_LOOP = 1000  # Maximum iterations when building a single loop
MAX_LOOPS_PER_OBJECT = 1000     # Maximum loops to process per object
TIMEOUT_PER_OBJECT = 10.0       # Maximum seconds to spend on one object


def extract_primary_material_color(original_obj, split_obj):
    """
    Extract primary material color from original mesh or split part
    Returns RGB tuple (0.0-1.0) or None if no material found
    
    Improved detection with better error handling and logging
    """
    # Try split object first (may have materials)
    if split_obj.data.materials:
        for mat in split_obj.data.materials:
            if not mat:
                continue
            
            if mat.use_nodes:
                # Try to get base color from Principled BSDF
                if mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'BSDF_PRINCIPLED':
                            base_color_input = node.inputs.get('Base Color')
                            if base_color_input:
                                try:
                                    color = base_color_input.default_value
                                    if len(color) >= 3:
                                        # Validate color values are reasonable
                                        if all(0.0 <= c <= 1.0 for c in color[:3]):
                                            return (color[0], color[1], color[2])
                                except (AttributeError, TypeError, IndexError):
                                    pass
            
            # Fallback: use material's diffuse color
            if hasattr(mat, 'diffuse_color'):
                try:
                    color = mat.diffuse_color
                    if len(color) >= 3:
                        # Validate color values are reasonable
                        if all(0.0 <= c <= 1.0 for c in color[:3]):
                            return (color[0], color[1], color[2])
                except (AttributeError, TypeError, IndexError):
                    pass
    
    # Try original object
    if original_obj and original_obj.data.materials:
        for mat in original_obj.data.materials:
            if not mat:
                continue
            
            if mat.use_nodes:
                if mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'BSDF_PRINCIPLED':
                            base_color_input = node.inputs.get('Base Color')
                            if base_color_input:
                                try:
                                    color = base_color_input.default_value
                                    if len(color) >= 3:
                                        if all(0.0 <= c <= 1.0 for c in color[:3]):
                                            return (color[0], color[1], color[2])
                                except (AttributeError, TypeError, IndexError):
                                    pass
            
            if hasattr(mat, 'diffuse_color'):
                try:
                    color = mat.diffuse_color
                    if len(color) >= 3:
                        if all(0.0 <= c <= 1.0 for c in color[:3]):
                            return (color[0], color[1], color[2])
                except (AttributeError, TypeError, IndexError):
                    pass
    
    # Try vertex colors (color attributes)
    if hasattr(split_obj.data, 'color_attributes') and split_obj.data.color_attributes:
        # Try active color attribute
        try:
            color_attr = split_obj.data.color_attributes.active_color
            if color_attr:
                # Sample first few vertices to get average color
                total_color = Vector((0, 0, 0))
                count = 0
                sample_count = min(100, len(color_attr.data))
                for i in range(sample_count):
                    try:
                        color_data = color_attr.data[i]
                        if hasattr(color_data, 'color'):
                            color = color_data.color
                        else:
                            color = color_data
                        
                        if len(color) >= 3:
                            total_color += Vector((color[0], color[1], color[2]))
                            count += 1
                    except (AttributeError, TypeError, IndexError):
                        continue
                
                if count > 0:
                    avg_color = total_color / count
                    # Validate color values
                    if all(0.0 <= c <= 1.0 for c in avg_color[:3]):
                        return tuple(avg_color[:3])
        except (AttributeError, TypeError):
            pass
    
    # Legacy vertex colors support
    if hasattr(split_obj.data, 'vertex_colors') and split_obj.data.vertex_colors:
        try:
            color_layer = split_obj.data.vertex_colors.active
            if color_layer:
                total_color = Vector((0, 0, 0))
                count = 0
                sample_count = min(100, len(color_layer.data))
                for i in range(sample_count):
                    try:
                        loop = color_layer.data[i]
                        color = loop.color
                        if len(color) >= 3:
                            total_color += Vector((color[0], color[1], color[2]))
                            count += 1
                    except (AttributeError, TypeError, IndexError):
                        continue
                
                if count > 0:
                    avg_color = total_color / count
                    if all(0.0 <= c <= 1.0 for c in avg_color[:3]):
                        return tuple(avg_color[:3])
        except (AttributeError, TypeError):
            pass
    
    return None


def sample_color_from_adjacent_faces(bm, obj, boundary_edges, depth=2):
    """
    Sample material color from faces adjacent to boundary edges, traversing a few vertices deep.
    
    This avoids black border cuts by sampling from faces that are a few vertices away
    from the actual boundary, ensuring we get the true material color.
    
    Args:
        bm: bmesh object
        obj: Blender object (for material access)
        boundary_edges: set of boundary edges to sample from
        depth: number of vertices to traverse inward (default 2)
    
    Returns:
        tuple: RGB color (0.0-1.0) or None if no color found
    """
    if not boundary_edges or not obj.data.materials:
        return None
    
    collected_faces = set()
    boundary_verts = set()
    
    # Collect boundary vertices
    for edge in boundary_edges:
        boundary_verts.add(edge.verts[0])
        boundary_verts.add(edge.verts[1])
        # Get adjacent face (boundary edges have exactly one face)
        if len(edge.link_faces) == 1:
            collected_faces.add(edge.link_faces[0])
    
    # Traverse depth levels inward from boundary
    current_verts = boundary_verts.copy()
    for level in range(depth):
        next_verts = set()
        for vert in current_verts:
            # Get all faces connected to this vertex
            for face in vert.link_faces:
                collected_faces.add(face)
            # Get neighboring vertices (one step inward)
            for edge in vert.link_edges:
                if edge not in boundary_edges:
                    neighbor = edge.other_vert(vert)
                    if neighbor not in boundary_verts:
                        next_verts.add(neighbor)
        current_verts = next_verts
    
    # Extract colors from collected faces
    colors = []
    for face in collected_faces:
        mat_idx = face.material_index
        if 0 <= mat_idx < len(obj.data.materials):
            mat = obj.data.materials[mat_idx]
            if not mat:
                continue
            
            face_color = None
            
            # Try Principled BSDF base color
            if mat.use_nodes and mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        base_color_input = node.inputs.get('Base Color')
                        if base_color_input:
                            try:
                                color = base_color_input.default_value
                                if len(color) >= 3 and all(0.0 <= c <= 1.0 for c in color[:3]):
                                    face_color = (color[0], color[1], color[2])
                                    break
                            except (AttributeError, TypeError, IndexError):
                                pass
            
            # Fallback to diffuse color
            if face_color is None:
                if hasattr(mat, 'diffuse_color'):
                    try:
                        color = mat.diffuse_color
                        if len(color) >= 3 and all(0.0 <= c <= 1.0 for c in color[:3]):
                            face_color = (color[0], color[1], color[2])
                    except (AttributeError, TypeError, IndexError):
                        pass
            
            if face_color is not None:
                colors.append(face_color)
    
    if not colors:
        return None
    
    # Average all collected colors
    total = Vector((0, 0, 0))
    for color in colors:
        total += Vector(color[:3])
    avg_color = total / len(colors)
    return tuple(avg_color[:3])


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
    that were at vertex group boundaries during splitting. This prevents filling edges
    that weren't part of the original cut.
    
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
            print("[Fill Cut Faces] Warning: Stored boundary data is empty, falling back to one-face rule")
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
        
        print(f"[Fill Cut Faces] Found {matched_count} edges matching stored boundary data (from {len(stored_boundaries)} stored boundaries)")
        
        # If no edges matched, there might be a coordinate mismatch (e.g., gaps were created)
        # Fall back to one-face rule but warn the user
        if not separation_edges:
            print("[Fill Cut Faces] Warning: No edges matched stored boundaries, falling back to one-face rule")
            for edge in bm.edges:
                if len(edge.link_faces) == 1:
                    separation_edges.add(edge)
    else:
        # FALLBACK: No stored boundary data, use one-face rule
        # This is less accurate but works for backwards compatibility
        print("[Fill Cut Faces] No stored boundary data found, using one-face rule (may include non-cut edges)")
        for edge in bm.edges:
            if len(edge.link_faces) == 1:
                separation_edges.add(edge)
    
    return separation_edges


def get_boundary_edges(bm, obj=None):
    """
    Get separation boundary edges for filling.
    
    If the object has stored separation boundary data (pet_separation_boundary_edges),
    returns only edges that match those stored coordinates. Otherwise, falls back
    to returning all edges with only one face.
    
    Args:
        bm: bmesh object
        obj: Blender object (required for accurate boundary detection)
    
    Returns:
        set: Set of boundary edges that should be filled
    """
    # Ensure lookup tables
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    
    # Get separation boundary edges (uses stored data if available)
    boundary_edges = identify_separation_boundary_edges(bm, obj)
    
    return boundary_edges


def build_edge_loop(start_edge, boundary_edges, processed_edges, start_time, timeout):
    """
    Build a single closed edge loop starting from the given edge.
    
    Args:
        start_edge: bmesh edge to start from
        boundary_edges: set of all boundary edges
        processed_edges: set of already processed edges (will be updated)
        start_time: time when operation started (for timeout checking)
        timeout: maximum seconds to spend
    
    Returns:
        list: List of edges forming a closed loop, or None if loop couldn't be built
    """
    if start_edge in processed_edges:
        return None
    
    loop_edges = [start_edge]
    processed_edges.add(start_edge)
    
    current_edge = start_edge
    current_vert = start_edge.verts[1]
    start_vert = start_edge.verts[0]
    
    iter_count = 0
    
    while iter_count < MAX_ITERATIONS_PER_LOOP:
        # Check timeout
        if time.time() - start_time > timeout:
            return None
        
        iter_count += 1
        next_edge = None
        
        # Find next boundary edge connected to current vertex
        for e in current_vert.link_edges:
            if e in boundary_edges and e not in processed_edges:
                # Verify it's still a boundary edge (safety check)
                if len(e.link_faces) == 1:
                    next_edge = e
                    break
        
        if not next_edge:
            # Open end - not a closed loop
            # Remove edges from processed set so they can be tried again
            for e in loop_edges:
                processed_edges.discard(e)
            return None
        
        loop_edges.append(next_edge)
        processed_edges.add(next_edge)
        current_vert = next_edge.other_vert(current_vert)
        
        # Check if we've looped back to start
        if current_vert == start_vert:
            # Closed loop found - validate it has enough edges
            if len(loop_edges) >= 3:
                return loop_edges
            else:
                # Too few edges - remove from processed
                for e in loop_edges:
                    processed_edges.discard(e)
                return None
    
    # Max iterations reached - remove from processed
    for e in loop_edges:
        processed_edges.discard(e)
    return None


def smooth_filled_faces(bm, filled_faces, iterations=2, factor=0.6):
    """
    Smooth vertices of filled faces to blend with surrounding mesh.
    
    Args:
        bm: bmesh object
        filled_faces: list/set of bmesh faces to smooth
        iterations: number of smoothing passes
        factor: smoothing strength (0.0-1.0)
    """
    if not filled_faces:
        return
    
    # Collect vertices from filled faces
    verts_to_smooth = set()
    for face in filled_faces:
        try:
            if face.is_valid:
                for vert in face.verts:
                    verts_to_smooth.add(vert)
        except (AttributeError, RuntimeError):
            # Face might have been invalidated, skip it
            continue
    
    if not verts_to_smooth:
        return
    
    # Apply smoothing iterations
    for _ in range(iterations):
        try:
            bmesh.ops.smooth_vert(
                bm,
                verts=list(verts_to_smooth),
                factor=factor,
                use_axis_x=True,
                use_axis_y=True,
                use_axis_z=True
            )
        except (ValueError, RuntimeError):
            # Smoothing failed, skip this iteration
            break


def find_and_fill_loops(bm, boundary_edges, material_index, start_time, timeout, progress_callback=None):
    """
    Find all closed loops from boundary edges and fill them one at a time.
    
    Args:
        bm: bmesh object
        boundary_edges: set of boundary edges to process
        material_index: material index to assign to created faces
        start_time: time when operation started
        timeout: maximum seconds to spend
        progress_callback: optional function to call for progress updates
    
    Returns:
        tuple: (number of faces created, list of created faces)
    """
    if not boundary_edges:
        return (0, [])
    
    faces_created = 0
    created_faces = []
    processed_edges = set()
    boundary_edges_list = list(boundary_edges)
    loops_processed = 0
    
    # Process loops one at a time
    for start_edge in boundary_edges_list:
        # Check timeout
        if time.time() - start_time > timeout:
            break
        
        # Check max loops limit
        if loops_processed >= MAX_LOOPS_PER_OBJECT:
            break
        
        # Try to build a loop from this edge
        loop_edges = build_edge_loop(start_edge, boundary_edges, processed_edges, start_time, timeout)
        
        if not loop_edges:
            continue
        
        # Fill the loop
        try:
            result = bmesh.ops.edgeloop_fill(bm, edges=loop_edges)
            
            if 'faces' in result:
                for face in result['faces']:
                    try:
                        face.material_index = material_index
                        faces_created += 1
                        created_faces.append(face)
                    except (AttributeError, RuntimeError):
                        # Face might have been invalidated, skip it
                        pass
            
            loops_processed += 1
            
            # Update progress if callback provided
            if progress_callback:
                progress_callback(loops_processed)
                
        except (ValueError, RuntimeError) as e:
            # Loop fill failed - remove edges from processed so they can be retried
            for e in loop_edges:
                processed_edges.discard(e)
            continue
    
    return (faces_created, created_faces)


class PET_OT_fill_cut_faces(Operator):
    """Fill open cut boundaries on selected split parts with material-matched faces"""
    bl_idname = "pet.fill_cut_faces"
    bl_label = "Fill Cut Faces"
    bl_options = {'REGISTER', 'UNDO'}
    
    use_material_color: BoolProperty(
        name="Use Material Color",
        description="Extract color from existing materials. If disabled, uses fallback color.",
        default=True
    )
    
    color_darkening_factor: FloatProperty(
        name="Color Darkening",
        description="Darken extracted material color to make fills less obvious (0.0-1.0). Lower values = darker fills",
        default=0.65,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )
    
    sample_depth: IntProperty(
        name="Color Sample Depth",
        description="Number of vertices to traverse inward from boundary when sampling color (avoids black borders)",
        default=2,
        min=1,
        max=5
    )
    
    fallback_color: FloatVectorProperty(
        name="Fallback Color",
        description="Color to use if material color cannot be extracted (dark brown/gray)",
        default=(0.15, 0.1, 0.08),  # Dark brown - much less visible
        min=0.0,
        max=1.0,
        subtype='COLOR'
    )
    
    auto_smooth_filled: BoolProperty(
        name="Auto-Smooth Filled Faces",
        description="Automatically smooth filled faces after creation for better integration",
        default=True
    )
    
    smooth_iterations: IntProperty(
        name="Smooth Iterations",
        description="Number of smoothing passes to apply to filled faces",
        default=2,
        min=1,
        max=5
    )
    
    smooth_factor: FloatProperty(
        name="Smooth Factor",
        description="Strength of smoothing per iteration (0.0-1.0)",
        default=0.6,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )
    
    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'ERROR'}, "Please select mesh objects with open boundaries to fill")
            return {'CANCELLED'}
        
        # Try to find original object (for material extraction)
        original_obj = None
        for obj in context.scene.objects:
            if obj.type == 'MESH' and "pet_original_mesh" in obj:
                # This might be marked as original, but we want the one that was split
                pass
        
        total_faces_created = 0
        processed_objects = 0
        failed_objects = []
        
        # Initialize progress reporting
        wm = context.window_manager
        total_work = len(selected_objects)
        wm.progress_begin(0, total_work)
        
        try:
            for obj_idx, obj in enumerate(selected_objects):
                # Update progress
                wm.progress_update(obj_idx)
                
                obj_start_time = time.time()
                
                try:
                    # Ensure we're in object mode
                    if context.mode != 'OBJECT':
                        bpy.ops.object.mode_set(mode='OBJECT')
                    
                    # Select this object
                    bpy.ops.object.select_all(action='DESELECT')
                    obj.select_set(True)
                    context.view_layer.objects.active = obj
                    
                    # Enter edit mode
                    bpy.ops.object.mode_set(mode='EDIT')
                    
                    # Get bmesh
                    bm = bmesh.from_edit_mesh(obj.data)
                    
                    # Ensure lookup tables
                    bm.faces.ensure_lookup_table()
                    bm.edges.ensure_lookup_table()
                    bm.verts.ensure_lookup_table()
                    
                    # Get boundary edges (edges with only one face)
                    boundary_edges = get_boundary_edges(bm, obj)
                    
                    if not boundary_edges:
                        bmesh.update_edit_mesh(obj.data)
                        bm.free()
                        bpy.ops.object.mode_set(mode='OBJECT')
                        continue
                    
                    # Get material color - try adjacent face sampling first
                    fill_color = None
                    if self.use_material_color:
                        # First try sampling from adjacent faces (avoids black borders)
                        fill_color = sample_color_from_adjacent_faces(bm, obj, boundary_edges, depth=self.sample_depth)
                        
                        # Fallback to general material extraction if adjacent sampling fails
                        if not fill_color:
                            fill_color = extract_primary_material_color(original_obj, obj)
                        
                        # Apply darkening factor to make fills less obvious
                        if fill_color:
                            fill_color = tuple(c * self.color_darkening_factor for c in fill_color[:3])
                    
                    # CRITICAL: Ensure fallback color is used if material detection fails
                    # Default to dark brown (0.15, 0.1, 0.08) which is much less visible
                    if not fill_color:
                        fill_color = tuple(self.fallback_color[:3]) if len(self.fallback_color) >= 3 else (0.15, 0.1, 0.08)
                    
                    # Validate color values
                    if not all(0.0 <= c <= 1.0 for c in fill_color[:3]):
                        fill_color = (0.15, 0.1, 0.08)  # Safe fallback to dark brown
                    
                    # Create material for filled faces if needed
                    material = None
                    material_name = f"{obj.name}_FillMaterial"
                    
                    # Check if material already exists
                    if material_name in bpy.data.materials:
                        material = bpy.data.materials[material_name]
                    else:
                        # Create new material
                        material = bpy.data.materials.new(name=material_name)
                        material.use_nodes = True
                        
                        # Set up Principled BSDF with extracted color
                        if material.node_tree:
                            principled = material.node_tree.nodes.get('Principled BSDF')
                            if principled:
                                principled.inputs['Base Color'].default_value = (*fill_color, 1.0)
                                principled.inputs['Metallic'].default_value = 0.0
                                principled.inputs['Roughness'].default_value = 0.8
                    
                    # Add material to object if not present
                    if material.name not in obj.data.materials:
                        obj.data.materials.append(material)
                    material_index = obj.data.materials.find(material.name)
                    
                    # Find and fill loops one at a time (prevents freezing)
                    def progress_callback(loops_done):
                        """Update progress during loop processing"""
                        # Progress is already updated per object, but we could add per-loop updates here
                        pass
                    
                    faces_created, created_faces = find_and_fill_loops(
                        bm,
                        boundary_edges,
                        material_index,
                        obj_start_time,
                        TIMEOUT_PER_OBJECT,
                        progress_callback
                    )
                    
                    total_faces_created += faces_created
                    
                    # Auto-smooth filled faces if enabled
                    if self.auto_smooth_filled and created_faces:
                        try:
                            smooth_filled_faces(
                                bm,
                                created_faces,
                                iterations=self.smooth_iterations,
                                factor=self.smooth_factor
                            )
                        except (ValueError, RuntimeError) as e:
                            # Smoothing failed, but continue with normal processing
                            print(f"[Fill Cut Faces] Warning: Smoothing failed: {e}")
                    
                    # Recalculate normals using bmesh ops (non-blocking)
                    # Do this after smoothing to ensure proper normals
                    try:
                        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                    except (ValueError, RuntimeError):
                        # If recalc fails, try updating mesh and using bpy.ops as fallback
                        bmesh.update_edit_mesh(obj.data)
                        bm.free()
                        bpy.ops.object.mode_set(mode='OBJECT')
                        bpy.ops.object.mode_set(mode='EDIT')
                        try:
                            bpy.ops.mesh.normals_make_consistent(inside=False)
                        except RuntimeError:
                            pass
                        bpy.ops.object.mode_set(mode='OBJECT')
                    else:
                        # Update mesh and free bmesh
                        bmesh.update_edit_mesh(obj.data)
                        bm.free()
                        bpy.ops.object.mode_set(mode='OBJECT')
                    
                    processed_objects += 1
                    
                except Exception as e:
                    # Log error but continue with other objects
                    failed_objects.append((obj.name, str(e)))
                    try:
                        bm.free()
                    except:
                        pass
                    try:
                        if context.mode != 'OBJECT':
                            bpy.ops.object.mode_set(mode='OBJECT')
                    except:
                        pass
                    continue
                    
        finally:
            # End progress reporting
            wm.progress_end()
        
        # Restore selection
        try:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in selected_objects:
                obj.select_set(True)
            if selected_objects:
                context.view_layer.objects.active = selected_objects[0]
        except RuntimeError:
            # Selection restore failed, but that's okay
            pass
        
        # Report results
        if processed_objects > 0:
            msg = f"Created {total_faces_created} fill faces on {processed_objects} object(s)"
            if failed_objects:
                msg += f" ({len(failed_objects)} object(s) failed)"
            self.report({'INFO'}, msg)
            
            if failed_objects:
                for obj_name, error in failed_objects[:3]:  # Show first 3 errors
                    self.report({'WARNING'}, f"{obj_name}: {error}")
        else:
            self.report({'WARNING'}, "No open boundaries found to fill or all objects failed")
        
        return {'FINISHED'}


classes = [
    PET_OT_fill_cut_faces,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
