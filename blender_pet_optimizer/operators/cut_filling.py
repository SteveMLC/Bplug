"""
Cut face filling operators
Fills open boundaries on split parts with material-matched faces
"""

import bpy
import bmesh
from bpy.types import Operator
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty
from mathutils import Vector


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


def identify_separation_boundary_edges(bm, obj, tolerance=0.001):
    """
    Identify edges that are actual separation boundaries (created during split operation).
    Uses both edge connectivity (edges with only one face) and coordinate matching.
    
    Args:
        bm: bmesh object
        obj: Blender object (to check for stored boundary info)
        tolerance: Distance tolerance for matching vertex coordinates (increased to 0.001 for gaps)
    
    Returns:
        set: Set of bmesh edges that are separation boundaries
    """
    separation_edges = set()
    
    # Ensure lookup tables
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    
    # PRIMARY STRATEGY: Find edges with only ONE face that match stored boundaries
    # This is more robust than coordinate matching alone, especially after gaps are created
    
    # Check if object has stored separation boundary info
    if "pet_separation_boundary_edges" not in obj:
        # No stored info - return empty set (fallback will be used)
        return separation_edges
    
    stored_boundaries = obj.get("pet_separation_boundary_edges", [])
    if not stored_boundaries:
        return separation_edges
    
    # Convert stored boundary coordinates back to Vectors for comparison
    stored_edges = []
    for boundary_pair in stored_boundaries:
        if len(boundary_pair) == 2:
            v1_co = Vector(boundary_pair[0])
            v2_co = Vector(boundary_pair[1])
            stored_edges.append((v1_co, v2_co))
    
    if not stored_edges:
        return separation_edges
    
    # Match edges using BOTH connectivity AND coordinate matching
    # Priority: Edges with only one face (true boundaries) that match stored coordinates
    for edge in bm.edges:
        # CRITICAL: Only consider edges with exactly one face (true cut boundaries)
        # This ensures we don't match internal edges
        if len(edge.link_faces) != 1:
            continue
        
        v1_co = edge.verts[0].co
        v2_co = edge.verts[1].co
        
        # Check if this edge matches any stored boundary edge
        # Need to check both directions (v1-v2 and v2-v1)
        for stored_v1, stored_v2 in stored_edges:
            # Check forward direction
            dist1_forward = (v1_co - stored_v1).length
            dist2_forward = (v2_co - stored_v2).length
            
            # Check reverse direction
            dist1_reverse = (v1_co - stored_v2).length
            dist2_reverse = (v2_co - stored_v1).length
            
            # Match if both vertices are within tolerance (in either direction)
            # Increased tolerance (0.001) handles cases where gaps were created
            if (dist1_forward < tolerance and dist2_forward < tolerance) or \
               (dist1_reverse < tolerance and dist2_reverse < tolerance):
                separation_edges.add(edge)
                break
    
    return separation_edges


def identify_separation_boundary_edges_fallback(bm, obj):
    """
    Fallback method: Identify edges that are likely separation boundaries.
    Used when stored boundary info is not available (backwards compatibility).
    
    Strategy: Only select boundary edges (edges with only one face) that form closed loops.
    This filters out internal holes and ensures we only get actual cut surfaces.
    
    Args:
        bm: bmesh object
        obj: Blender object
    
    Returns:
        set: Set of bmesh edges that are likely separation boundaries (form closed loops)
    """
    boundary_edges = set()
    
    # Get all boundary edges (edges with only one face)
    candidate_edges = set()
    for edge in bm.edges:
        if len(edge.link_faces) == 1:
            candidate_edges.add(edge)
    
    if not candidate_edges:
        return boundary_edges
    
    # Filter to edges that form closed loops (actual cut surfaces)
    # Build loops from candidate edges and only keep edges that are part of closed loops
    processed_edges = set()
    
    for start_edge in candidate_edges:
        if start_edge in processed_edges:
            continue
        
        # Try to build a loop from this edge
        loop_edges = []
        current_edge = start_edge
        start_vert = start_edge.verts[0]
        current_vert = start_vert
        
        max_iterations = len(candidate_edges) * 2
        iteration_count = 0
        
        while current_edge and current_edge not in processed_edges and iteration_count < max_iterations:
            iteration_count += 1
            loop_edges.append(current_edge)
            
            # Get the other vertex
            other_vert = current_edge.other_vert(current_vert)
            current_vert = other_vert
            
            # If we've looped back to start, this is a closed loop
            if current_vert == start_vert:
                # This is a valid closed loop - add all edges to result
                for e in loop_edges:
                    boundary_edges.add(e)
                    processed_edges.add(e)
                break
            
            # Find next candidate edge connected to current vertex
            current_edge = None
            for e in current_vert.link_edges:
                if e not in processed_edges and e in candidate_edges:
                    current_edge = e
                    break
            
            if not current_edge:
                # Open end - not a closed loop, skip these edges
                break
    
    return boundary_edges


def find_open_boundaries(bm, obj=None):
    """
    Find open boundary loops from actual separation boundaries (edges created during split).
    Only includes edges that match stored separation boundary info AND have only one face.
    Validates that loops are closed before returning them.
    
    Args:
        bm: bmesh object
        obj: Blender object (to check for stored boundary info)
    
    Returns:
        list: List of vertex loops (each loop is a list of bmesh vertices)
    """
    boundary_loops = []
    processed_edges = set()
    
    # Ensure lookup tables
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    
    # Get actual separation boundary edges (cuts from split operation)
    if obj:
        separation_edges = identify_separation_boundary_edges(bm, obj)
        
        # Fallback if no stored boundary info (backwards compatibility)
        if not separation_edges:
            separation_edges = identify_separation_boundary_edges_fallback(bm, obj)
    else:
        # No object provided - use fallback
        separation_edges = set()
        for edge in bm.edges:
            # CRITICAL: Only edges with exactly one face (true boundaries)
            if len(edge.link_faces) == 1:
                separation_edges.add(edge)
    
    if not separation_edges:
        return boundary_loops
    
    # Build loops from separation boundary edges only
    # CRITICAL: Only build loops from edges with exactly one face
    for edge in separation_edges:
        if edge in processed_edges:
            continue
        
        # CRITICAL: Only process edges with exactly one face (true cut boundaries)
        if len(edge.link_faces) != 1:
            continue
        
        # This edge is a separation boundary - find its connected loop
        loop_edges = []
        loop_verts = []
        
        # Start from this edge
        current_edge = edge
        start_vert = edge.verts[0]
        current_vert = start_vert
        loop_verts.append(start_vert)
        
        max_iterations = len(separation_edges) * 2  # Safety limit
        iteration_count = 0
        is_closed = False
        
        while current_edge and current_edge not in processed_edges and iteration_count < max_iterations:
            iteration_count += 1
            processed_edges.add(current_edge)
            loop_edges.append(current_edge)
            
            # Get the other vertex
            other_vert = current_edge.other_vert(current_vert)
            if other_vert not in loop_verts:
                loop_verts.append(other_vert)
            
            current_vert = other_vert
            
            # If we've looped back to start, this is a closed loop
            if current_vert == start_vert:
                is_closed = True
                break
            
            # Find next separation boundary edge connected to current vertex
            # CRITICAL: Only follow edges that are in separation_edges AND have only one face
            current_edge = None
            for e in current_vert.link_edges:
                if e not in processed_edges and e in separation_edges:
                    # Double-check: edge must have only one face
                    if len(e.link_faces) == 1:
                        current_edge = e
                        break
            
            if not current_edge:
                # Open end - not a closed loop
                break
        
        # VALIDATION: Only add loops that are closed and have enough edges
        # Closed loops need at least 3 edges to form a valid face
        if is_closed and len(loop_edges) >= 3:
            # Additional validation: check that loop vertices are distinct
            if len(loop_verts) >= 3 and len(set(loop_verts)) == len(loop_verts):
                boundary_loops.append(loop_verts)
            elif len(loop_verts) >= 3:
                # Loop has duplicate vertices but might still be valid (self-intersecting)
                # Check if it forms a valid boundary
                boundary_loops.append(loop_verts)
    
    return boundary_loops


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
    
    fallback_color: FloatVectorProperty(
        name="Fallback Color",
        description="Color to use if material color cannot be extracted (gray/dark brown)",
        default=(0.3, 0.3, 0.3),  # Medium gray - hidden inside model when reconnected
        min=0.0,
        max=1.0,
        subtype='COLOR'
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
        
        for obj in selected_objects:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            bpy.ops.object.mode_set(mode='EDIT')
            
            bm = bmesh.from_edit_mesh(obj.data)
            bm.faces.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.verts.ensure_lookup_table()
            
            # Find open boundary loops (only from actual separation boundaries)
            boundary_loops = find_open_boundaries(bm, obj)
            
            if not boundary_loops:
                bmesh.update_edit_mesh(obj.data)
                bm.free()
                bpy.ops.object.mode_set(mode='OBJECT')
                continue
            
            # Get material color
            fill_color = None
            if self.use_material_color:
                fill_color = extract_primary_material_color(original_obj, obj)
            
            # CRITICAL: Ensure fallback color is used if material detection fails
            # Default to gray (0.3, 0.3, 0.3) which is hidden inside model when reconnected
            if not fill_color:
                fill_color = tuple(self.fallback_color[:3]) if len(self.fallback_color) >= 3 else (0.3, 0.3, 0.3)
            
            # Validate color values
            if not all(0.0 <= c <= 1.0 for c in fill_color[:3]):
                fill_color = (0.3, 0.3, 0.3)  # Safe fallback to gray
            
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
            
            # Fill each boundary loop
            faces_created = 0
            for loop_verts in boundary_loops:
                if len(loop_verts) < 3:
                    continue
                
                # CRITICAL: Check if a face already exists for these vertices
                # This prevents creating overlapping faces on existing geometry
                face_already_exists = False
                loop_vert_indices = {v.index for v in loop_verts}
                
                # Check all faces to see if any face uses all vertices in this loop
                for face in bm.faces:
                    face_vert_indices = {v.index for v in face.verts}
                    # If the face contains all vertices from the loop, a face already exists
                    if loop_vert_indices.issubset(face_vert_indices):
                        face_already_exists = True
                        break
                
                if face_already_exists:
                    # Face already exists - skip this loop (don't create overlapping geometry)
                    continue
                
                # CRITICAL: Verify that all edges in the loop have only one face
                # This ensures we're only filling actual gaps, not internal edges
                all_edges_are_boundaries = True
                for i in range(len(loop_verts)):
                    v1 = loop_verts[i]
                    v2 = loop_verts[(i + 1) % len(loop_verts)]
                    
                    # Find edge connecting these vertices
                    edge = None
                    for e in v1.link_edges:
                        if e.other_vert(v1) == v2:
                            edge = e
                            break
                    
                    if edge and len(edge.link_faces) != 1:
                        # Edge has more than one face - not a true boundary
                        all_edges_are_boundaries = False
                        break
                
                if not all_edges_are_boundaries:
                    # Not all edges are boundaries - skip this loop
                    continue
                
                # Try creating face directly from vertex loop
                try:
                    face = bm.faces.new(loop_verts)
                    face.material_index = material_index
                    faces_created += 1
                except (ValueError, RuntimeError) as e:
                    # Face creation failed (might be degenerate, non-planar, or non-manifold)
                    # Try improved triangulation methods
                    try:
                        if len(loop_verts) >= 3:
                            # Method 1: Fan triangulation from first vertex
                            # This works well for convex loops
                            first_vert = loop_verts[0]
                            fan_success = False
                            
                            for i in range(1, len(loop_verts) - 1):
                                try:
                                    # Check if this triangle would create an overlapping face
                                    tri_verts = [first_vert, loop_verts[i], loop_verts[i + 1]]
                                    tri_vert_indices = {v.index for v in tri_verts}
                                    
                                    # Check if a face already exists for these three vertices
                                    tri_face_exists = False
                                    for face in bm.faces:
                                        face_vert_indices = {v.index for v in face.verts}
                                        if tri_vert_indices.issubset(face_vert_indices):
                                            tri_face_exists = True
                                            break
                                    
                                    if not tri_face_exists:
                                        tri_face = bm.faces.new(tri_verts)
                                        tri_face.material_index = material_index
                                        faces_created += 1
                                        fan_success = True
                                except (ValueError, RuntimeError):
                                    # Skip this triangle if it fails
                                    continue
                            
                            # Method 2: If fan triangulation failed, try ear clipping approach
                            # This works better for concave loops
                            if not fan_success and len(loop_verts) >= 4:
                                # Try creating triangles from different starting points
                                for start_idx in range(min(3, len(loop_verts))):  # Try first 3 vertices as starting points
                                    start_vert = loop_verts[start_idx]
                                    created_any = False
                                    
                                    for i in range(1, len(loop_verts) - 1):
                                        idx1 = (start_idx + i) % len(loop_verts)
                                        idx2 = (start_idx + i + 1) % len(loop_verts)
                                        
                                        if idx1 == idx2 or idx1 == start_idx or idx2 == start_idx:
                                            continue
                                        
                                        try:
                                            tri_verts = [start_vert, loop_verts[idx1], loop_verts[idx2]]
                                            
                                            # Validate triangle (check for degenerate cases)
                                            v0 = tri_verts[0].co
                                            v1 = tri_verts[1].co
                                            v2 = tri_verts[2].co
                                            
                                            # Check if triangle is degenerate (zero area)
                                            edge1 = v1 - v0
                                            edge2 = v2 - v0
                                            cross = edge1.cross(edge2)
                                            if cross.length < 0.0001:
                                                continue  # Degenerate triangle, skip
                                            
                                            tri_vert_indices = {v.index for v in tri_verts}
                                            
                                            # Check if a face already exists
                                            tri_face_exists = False
                                            for face in bm.faces:
                                                face_vert_indices = {v.index for v in face.verts}
                                                if tri_vert_indices.issubset(face_vert_indices):
                                                    tri_face_exists = True
                                                    break
                                            
                                            if not tri_face_exists:
                                                tri_face = bm.faces.new(tri_verts)
                                                tri_face.material_index = material_index
                                                faces_created += 1
                                                created_any = True
                                        except (ValueError, RuntimeError):
                                            continue
                                    
                                    if created_any:
                                        break  # Success with this starting point
                    except Exception:
                        # Skip this loop entirely if all triangulation methods fail
                        pass
            
            total_faces_created += faces_created
            
            # Update mesh
            bmesh.update_edit_mesh(obj.data)
            bm.free()
            
            # Recalculate normals
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.normals_make_consistent(inside=False)
            bpy.ops.object.mode_set(mode='OBJECT')
            
            processed_objects += 1
        
        # Restore selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_objects:
            obj.select_set(True)
        if selected_objects:
            context.view_layer.objects.active = selected_objects[0]
        
        if processed_objects > 0:
            self.report({'INFO'}, f"Created {total_faces_created} fill faces on {processed_objects} object(s)")
        else:
            self.report({'WARNING'}, "No open boundaries found to fill")
        
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
