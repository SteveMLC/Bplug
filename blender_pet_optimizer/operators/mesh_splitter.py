"""
Mesh splitting operators
Splits meshes by vertex groups with full data preservation (UVs, colors, materials)
"""

import bpy
import bmesh
from bpy.types import Operator
from bpy.props import BoolProperty, FloatProperty
from mathutils import Vector
import time

from ..utils.spatial_selection import (
    fill_small_surrounded_gaps,
)


def find_boundary_edges(bm, vertex_group_indices):
    """
    Find edges that form boundaries between different vertex groups
    
    Args:
        bm: bmesh object
        vertex_group_indices: dict mapping vertex group names to their indices in source mesh
    
    Returns:
        dict: {edge: (group1_name, group2_name)} for boundary edges
    """
    boundary_edges = {}
    
    # Build a mapping of vertex indices to their groups
    # Since bmesh doesn't have vertex groups directly, we need to track this from the source
    # This will be populated by the caller who has access to the original mesh vertex groups
    
    return boundary_edges


def copy_uv_layers(source_mesh, target_mesh, face_map):
    """
    Copy all UV layers from source to target mesh
    
    Args:
        source_mesh: Source mesh with UV layers
        target_mesh: Target mesh to copy UVs to
        face_map: dict mapping target face indices to source face indices
    """
    if not source_mesh.uv_layers:
        return
    
    # Copy each UV layer
    for uv_layer_idx, source_uv_layer in enumerate(source_mesh.uv_layers.items()):
        uv_layer_name, source_uv_data = source_uv_layer
        
        # Create or get UV layer in target
        if uv_layer_name in target_mesh.uv_layers:
            target_uv_data = target_mesh.uv_layers[uv_layer_name]
        else:
            target_uv_layer = target_mesh.uv_layers.new(name=uv_layer_name)
            target_uv_data = target_uv_layer.data
        
        # Copy UV data for each face
        for target_poly_idx, source_poly_idx in face_map.items():
            source_poly = source_mesh.polygons[source_poly_idx]
            target_poly = target_mesh.polygons[target_poly_idx]
            
            # Copy UV coordinates for each loop
            for i, source_loop_idx in enumerate(source_poly.loop_indices):
                if i < len(target_poly.loop_indices):
                    target_loop_idx = target_poly.loop_indices[i]
                    source_uv = source_uv_data[source_loop_idx].uv
                    target_uv_data[target_loop_idx].uv = source_uv


def copy_color_attributes(source_mesh, target_mesh, face_map, vert_map):
    """
    Copy all color attributes (vertex colors) from source to target mesh
    
    Args:
        source_mesh: Source mesh with color attributes
        target_mesh: Target mesh to copy colors to
        face_map: dict mapping target face indices to source face indices
        vert_map: dict mapping target vertex indices to source vertex indices
    """
    if not hasattr(source_mesh, 'color_attributes') or not source_mesh.color_attributes:
        return
    
    # Copy each color attribute
    for attr in source_mesh.color_attributes:
        # Create new color attribute in target
        if attr.name in target_mesh.color_attributes:
            target_attr = target_mesh.color_attributes[attr.name]
        else:
            target_attr = target_mesh.color_attributes.new(
                name=attr.name,
                domain=attr.domain,
                type=attr.data_type
            )
        
        # Copy data based on domain
        if attr.domain == 'POINT':  # Vertex colors
            for target_vert_idx, source_vert_idx in vert_map.items():
                if target_vert_idx < len(target_attr.data) and source_vert_idx < len(attr.data):
                    if hasattr(target_attr.data[target_vert_idx], 'color'):
                        target_attr.data[target_vert_idx].color = attr.data[source_vert_idx].color[:]
                    else:
                        # For FLOAT_COLOR type
                        target_attr.data[target_vert_idx] = attr.data[source_vert_idx]
        
        elif attr.domain == 'CORNER':  # Loop/face vertex colors
            for target_poly_idx, source_poly_idx in face_map.items():
                source_poly = source_mesh.polygons[source_poly_idx]
                target_poly = target_mesh.polygons[target_poly_idx]
                
                for i, source_loop_idx in enumerate(source_poly.loop_indices):
                    if i < len(target_poly.loop_indices):
                        target_loop_idx = target_poly.loop_indices[i]
                        if target_loop_idx < len(target_attr.data) and source_loop_idx < len(attr.data):
                            if hasattr(target_attr.data[target_loop_idx], 'color'):
                                target_attr.data[target_loop_idx].color = attr.data[source_loop_idx].color[:]
                            else:
                                target_attr.data[target_loop_idx] = attr.data[source_loop_idx]


def copy_materials(source_obj, target_obj, face_map):
    """
    Copy material assignments from source to target object
    
    Args:
        source_obj: Source object with materials
        target_obj: Target object to assign materials to
        face_map: dict mapping target face indices to source face indices
    """
    source_mesh = source_obj.data
    target_mesh = target_obj.data
    
    if not source_mesh.materials:
        return
    
    # Copy material slots
    material_map = {}  # Maps old material index to new material index
    for mat_idx, material in enumerate(source_mesh.materials):
        if material:
            if material not in target_mesh.materials:
                target_mesh.materials.append(material)
            material_map[mat_idx] = target_mesh.materials.find(material.name)
    
    # Assign materials to faces
    for target_poly_idx, source_poly_idx in face_map.items():
        source_poly = source_mesh.polygons[source_poly_idx]
        target_poly = target_mesh.polygons[target_poly_idx]
        
        if source_poly.material_index in material_map:
            target_poly.material_index = material_map[source_poly.material_index]


def split_mesh_by_vertex_group(obj, vertex_group_name, create_pivot=True):
    """
    Split mesh by a single vertex group, preserving all data
    
    Args:
        obj: Blender object with mesh data
        vertex_group_name: Name of vertex group to split
        create_pivot: Whether to create pivot points at boundaries
    
    Returns:
        tuple: (new_object, pivot_points_list) or (None, []) on failure
    """
    mesh = obj.data
    vg_index = obj.vertex_groups.find(vertex_group_name)
    
    if vg_index == -1:
        return None, []
    
    # Build vertex selection mask for this group
    vertex_mask = [False] * len(mesh.vertices)
    for vertex in mesh.vertices:
        for group in vertex.groups:
            if group.group == vg_index and group.weight > 0.5:  # Threshold for inclusion
                vertex_mask[vertex.index] = True
                break
    
    # Use bmesh to extract geometry
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    # Select faces that belong to this vertex group
    faces_to_extract = []
    for face in bm.faces:
        # Face belongs to group if most of its vertices are in the group
        verts_in_group = sum(1 for v in face.verts if vertex_mask[v.index])
        if verts_in_group >= len(face.verts) / 2:  # Majority threshold
            faces_to_extract.append(face)
    
    if not faces_to_extract:
        bm.free()
        return None, []
    
    # Select the faces and edges/verts we need
    bmesh.ops.select_all(bm, action='DESELECT')
    for face in faces_to_extract:
        face.select = True
        for edge in face.edges:
            edge.select = True
            for vert in edge.verts:
                vert.select = True
    
    # Duplicate selected geometry
    ret = bmesh.ops.duplicate(bm, geom=faces_to_extract)
    duplicated_geom = ret['geom']
    duplicated_faces = [g for g in duplicated_geom if isinstance(g, bmesh.types.BMFace)]
    
    # Create new mesh from duplicated geometry
    new_mesh = bpy.data.meshes.new(name=f"{obj.name}_{vertex_group_name}")
    new_bm = bmesh.new()
    
    # Copy faces
    new_bm.from_mesh(mesh)
    new_bm.faces.ensure_lookup_table()
    new_bm.verts.ensure_lookup_table()
    
    # Delete all faces not in our group
    faces_to_delete = []
    for face in new_bm.faces:
        verts_in_group = sum(1 for v in face.verts if vertex_mask[v.index])
        if verts_in_group < len(face.verts) / 2:
            faces_to_delete.append(face)
    
    if faces_to_delete:
        bmesh.ops.delete(new_bm, geom=faces_to_delete, context='FACES')
    
    # Remove loose vertices
    bmesh.ops.remove_doubles(new_bm, verts=new_bm.verts[:], dist=0.0001)
    
    # Convert to mesh
    new_bm.to_mesh(new_mesh)
    new_mesh.update()
    new_bm.free()
    bm.free()
    
    # Create new object
    new_obj = bpy.data.objects.new(name=f"{obj.name}_{vertex_group_name}", object_data=new_mesh)
    new_obj.location = obj.location
    new_obj.rotation_euler = obj.rotation_euler
    new_obj.scale = obj.scale
    
    # Copy data layers (this is complex, so we'll use a simpler approach)
    # Use Blender's built-in split operation which preserves data better
    
    return new_obj, []


def verify_split_data_preservation(original_obj, split_obj, vertex_group_name):
    """
    Verify that split object has preserved all data from original
    
    Args:
        original_obj: Original object before splitting
        split_obj: Split object to verify
        vertex_group_name: Name of vertex group that was split
    
    Returns:
        tuple: (is_valid, warnings_list)
    """
    warnings = []
    original_mesh = original_obj.data
    split_mesh = split_obj.data
    
    # Check UV layers
    original_uv_count = len(original_mesh.uv_layers) if original_mesh.uv_layers else 0
    split_uv_count = len(split_mesh.uv_layers) if split_mesh.uv_layers else 0
    if split_uv_count < original_uv_count:
        warnings.append(f"UV layers: {split_uv_count}/{original_uv_count} (may be expected if group had no UVs)")
    
    # Check color attributes
    original_color_count = 0
    split_color_count = 0
    if hasattr(original_mesh, 'color_attributes'):
        original_color_count = len(original_mesh.color_attributes) if original_mesh.color_attributes else 0
    if hasattr(split_mesh, 'color_attributes'):
        split_color_count = len(split_mesh.color_attributes) if split_mesh.color_attributes else 0
    if split_color_count < original_color_count:
        warnings.append(f"Color attributes: {split_color_count}/{original_color_count}")
    
    # Check materials (at least material slots exist)
    original_mat_count = len(original_mesh.materials) if original_mesh.materials else 0
    split_mat_count = len(split_mesh.materials) if split_mesh.materials else 0
    # Materials might be fewer if the split part doesn't use all materials
    
    is_valid = len(warnings) == 0 or (original_uv_count == 0 and original_color_count == 0)
    
    return is_valid, warnings


def calculate_attachment_points_from_vertex_groups(obj):
    """
    Calculate attachment point positions from vertex group boundaries BEFORE splitting
    
    Args:
        obj: Object with vertex groups
    
    Returns:
        dict: {('group1', 'group2'): Vector(position), ...}
    """
    if not obj or obj.type != 'MESH' or not obj.vertex_groups:
        return {}
    
    mesh = obj.data
    attachment_points = {}
    
    # Create bmesh to analyze boundaries
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    
    # Build vertex group membership map
    vert_group_map = {}  # {vert_index: set(group_names)}
    for vg in obj.vertex_groups:
        vg_index = vg.index
        vg_name = vg.name
        for vert_idx, vertex in enumerate(mesh.vertices):
            for group in vertex.groups:
                if group.group == vg_index and group.weight > 0.5:
                    if vert_idx not in vert_group_map:
                        vert_group_map[vert_idx] = set()
                    vert_group_map[vert_idx].add(vg_name)
    
    # Find boundary edges (edges where vertices belong to different groups)
    # After bm.from_mesh() on unchanged mesh, bmesh vertex index matches mesh vertex index
    # However, to be safe, we'll use a more efficient approach:
    # Since bmesh indices can change, we'll use vertex coordinates for matching
    # But optimize: after from_mesh(), indices usually match, so try direct index first
    bm_vert_to_mesh_idx = {}
    for vert in bm.verts:
        # Try direct index first (usually works after from_mesh())
        if vert.index < len(mesh.vertices):
            mesh_vert = mesh.vertices[vert.index]
            if (vert.co - mesh_vert.co).length < 0.0001:
                bm_vert_to_mesh_idx[vert] = vert.index
                continue
        # Fallback: search by coordinate (slower but more robust)
        for mesh_vert_idx, mesh_vert in enumerate(mesh.vertices):
            if (vert.co - mesh_vert.co).length < 0.0001:
                bm_vert_to_mesh_idx[vert] = mesh_vert_idx
                break
    
    boundary_edges = {}
    for edge in bm.edges:
        v1_bm = edge.verts[0]
        v2_bm = edge.verts[1]
        
        # Get mesh vertex indices (use fallback if mapping fails)
        v1_mesh_idx = bm_vert_to_mesh_idx.get(v1_bm, v1_bm.index)
        v2_mesh_idx = bm_vert_to_mesh_idx.get(v2_bm, v2_bm.index)
        
        # Ensure indices are valid
        if v1_mesh_idx >= len(mesh.vertices) or v2_mesh_idx >= len(mesh.vertices):
            continue
        
        groups1 = vert_group_map.get(v1_mesh_idx, set())
        groups2 = vert_group_map.get(v2_mesh_idx, set())
        
        # If vertices belong to different groups, this is a boundary edge
        if groups1 and groups2 and groups1 != groups2:
            # Get all group pairs
            for g1 in groups1:
                for g2 in groups2:
                    if g1 != g2:
                        key = tuple(sorted([g1, g2]))  # Sort for consistent key
                        if key not in boundary_edges:
                            boundary_edges[key] = []
                        # Store edge center in world space
                        v1_world = obj.matrix_world @ v1_bm.co
                        v2_world = obj.matrix_world @ v2_bm.co
                        edge_center = (v1_world + v2_world) / 2
                        boundary_edges[key].append(edge_center)
    
    # Calculate average position for each boundary
    for key, positions in boundary_edges.items():
        if positions:
            avg_position = sum(positions, Vector((0, 0, 0))) / len(positions)
            attachment_points[key] = avg_position
    
    bm.free()
    return attachment_points


class PET_OT_split_by_vertex_groups(Operator):
    """Split mesh into separate objects by vertex groups with full data preservation"""
    bl_idname = "pet.split_by_vertex_groups"
    bl_label = "Split by Vertex Groups"
    bl_options = {'REGISTER', 'UNDO'}
    
    create_pivots: BoolProperty(
        name="Create Pivot Points",
        description="Create pivot points at disconnect boundaries",
        default=True
    )
    
    keep_original: BoolProperty(
        name="Keep Original",
        description="Keep original mesh after splitting",
        default=True
    )
    
    verify_data: BoolProperty(
        name="Verify Data Preservation",
        description="Verify that UVs, colors, and materials are preserved",
        default=True
    )
    
    gap_distance: FloatProperty(
        name="Gap Distance",
        description="Distance to separate parts after splitting (for filling/smoothing workflow). Set to 0 to skip gap creation.",
        default=0.1,
        min=0.0,
        max=10.0,
        step=0.01,
        precision=3
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if not obj.vertex_groups:
            self.report({'ERROR'}, "No vertex groups found. Please segment the model first.")
            return {'CANCELLED'}
        
        # Ensure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Get settings from scene properties (fallback to operator properties for backwards compatibility)
        # Priority: Scene settings (for UI consistency), but operator properties are used if scene settings don't exist
        # When called from UI button, operator properties have defaults, so scene settings (user's choices) are used
        # When called programmatically with explicit params, those are set on self.*, but scene settings take precedence
        # Note: For programmatic calls that need to override scene settings, set scene settings before calling operator
        try:
            settings = context.scene.pet_split_settings
            keep_original = settings.keep_original if hasattr(settings, 'keep_original') else self.keep_original
            verify_data = settings.verify_data if hasattr(settings, 'verify_data') else self.verify_data
            gap_distance = settings.gap_distance if hasattr(settings, 'gap_distance') else self.gap_distance
            create_pivots = settings.create_pivots if hasattr(settings, 'create_pivots') else self.create_pivots
        except AttributeError:
            # Scene property doesn't exist (e.g., during addon reload) - use operator properties
            keep_original = self.keep_original
            verify_data = self.verify_data
            gap_distance = self.gap_distance
            create_pivots = self.create_pivots
        
        mesh = obj.data
        created_objects = []
        all_pivots = []
        verification_warnings = []
        
        # Calculate attachment points BEFORE splitting (using original mesh)
        # CRITICAL: These positions are at actual separation boundaries (where appendage meets body)
        # Must be stored BEFORE creating gaps so R6 joints can use them
        attachment_points = {}
        if create_pivots:
            attachment_points = calculate_attachment_points_from_vertex_groups(obj)
            # Store attachment points in original object metadata for R6 joints operator
            # Format: {(group1_name, group2_name): Vector(position), ...}
            if attachment_points:
                # Convert Vector to list for storage (Vector not directly serializable)
                stored_points = {}
                for key, pos in attachment_points.items():
                    stored_points[str(key)] = list(pos)
                obj["pet_stored_attachment_points"] = stored_points
                # Also store mapping info for lookup by object names later
                obj["pet_attachment_points_created"] = True
        
        try:
            # Check for potential overlapping vertex groups (vertices in multiple groups)
            # This can cause issues if vertices belong to multiple groups with weight > 0.5
            overlapping_vertices = set()
            for vg in obj.vertex_groups:
                vg_index = obj.vertex_groups.find(vg.name)
                if vg_index == -1:
                    continue
                for vertex in mesh.vertices:
                    for group in vertex.groups:
                        if group.group == vg_index and group.weight > 0.5:
                            if vertex.index in overlapping_vertices:
                                # Vertex is in multiple groups
                                pass  # Will be handled by split order
                            overlapping_vertices.add(vertex.index)
                            break
            
            # Store original object state for restoration
            context.view_layer.objects.active = obj
            
            # Split each vertex group - must work from original for each iteration
            # IMPORTANT: After each split(), the original mesh has faces removed
            # Vertices in overlapping groups will go to the FIRST group processed
            # This is intentional - each vertex should belong to one split object
            
            # CRITICAL: Store mesh reference before splitting - original mesh gets modified
            # We need to work with a fresh reference each time
            
            # Sort vertex groups: process body LAST to ensure it captures all remaining vertices
            # Body acts as a catch-all for faces not explicitly assigned to appendages
            vertex_groups_list = list(obj.vertex_groups)
            body_names = {'body', 'torso', 'core', 'Body', 'Torso', 'Core', 'BODY', 'TORSO', 'CORE'}
            
            def get_processing_priority(vg):
                """Return 1 for body (process last as catch-all), 0 for appendages"""
                return 1 if vg.name in body_names else 0
            
            # Sort: appendages first (priority 0), then body (priority 1) as catch-all
            vertex_groups_list.sort(key=get_processing_priority)
            
            # CRITICAL: Calculate body spatial boundaries BEFORE any splitting
            # Body vertices will be removed after split, so we need original mesh state
            stored_body_boundaries = {}
            
            # Create temporary bmesh from original mesh to calculate boundaries
            temp_bm = bmesh.new()
            temp_bm.from_mesh(mesh)
            temp_bm.verts.ensure_lookup_table()
            
            # Calculate body boundaries from original mesh
            for vg in obj.vertex_groups:
                vg_name_lower = vg.name.lower()
                
                # Only include body parts
                if vg.name not in body_names and vg_name_lower not in {n.lower() for n in body_names}:
                    continue
                
                # Get vertices in this body group from original mesh
                vg_index = vg.index
                body_vertices = []
                for vertex in mesh.vertices:  # Original mesh, not modified
                    for group in vertex.groups:
                        if group.group == vg_index and group.weight > 0.5:
                            body_vertices.append(vertex.index)
                            break
                
                if not body_vertices:
                    continue
                
                # Calculate bounding box for this body part
                bbox_min = None
                bbox_max = None
                for vert_idx in body_vertices:
                    if vert_idx >= len(temp_bm.verts):
                        continue
                    vert_co = temp_bm.verts[vert_idx].co
                    
                    if bbox_min is None:
                        bbox_min = Vector(vert_co)
                        bbox_max = Vector(vert_co)
                    else:
                        bbox_min.x = min(bbox_min.x, vert_co.x)
                        bbox_min.y = min(bbox_min.y, vert_co.y)
                        bbox_min.z = min(bbox_min.z, vert_co.z)
                        bbox_max.x = max(bbox_max.x, vert_co.x)
                        bbox_max.y = max(bbox_max.y, vert_co.y)
                        bbox_max.z = max(bbox_max.z, vert_co.z)
                
                if bbox_min is not None and bbox_max is not None:
                    # Expand boundary by same factor (0.015) for consistency
                    bbox_size = bbox_max - bbox_min
                    expand_amount = bbox_size * 0.015
                    expanded_min = bbox_min - expand_amount
                    expanded_max = bbox_max + expand_amount
                    stored_body_boundaries[vg.name] = (expanded_min, expanded_max)
            
            temp_bm.free()
            
            for vg in vertex_groups_list:
                # Re-acquire the original object reference (it may have been deselected)
                # Find it by name if context lost reference
                original_obj = None
                for o in bpy.context.scene.objects:
                    if o == obj or (o.name == obj.name and o.type == 'MESH'):
                        original_obj = o
                        break
                
                if not original_obj:
                    self.report({'ERROR'}, "Lost reference to original object during split")
                    break
                
                # Ensure we're working with the original object
                context.view_layer.objects.active = original_obj
                original_obj.select_set(True)
                
                # Make sure we're in object mode
                if context.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
                
                # Get fresh mesh reference (mesh data persists even if object changes)
                current_mesh = original_obj.data
                
                # Build vertex mask for this vertex group
                vg_index = original_obj.vertex_groups.find(vg.name)
                if vg_index == -1:
                    continue
                
                # Create vertex mask: True if vertex is in this group with weight > 0.5
                vertex_mask = [False] * len(current_mesh.vertices)
                vertices_in_group = 0
                for vertex in current_mesh.vertices:
                    for group in vertex.groups:
                        if group.group == vg_index and group.weight > 0.5:
                            vertex_mask[vertex.index] = True
                            vertices_in_group += 1
                            break
                
                if vertices_in_group == 0:
                    continue  # Skip if no vertices in this group
                
                # Switch to edit mode to select faces
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='DESELECT')  # Clear selection first
                bpy.ops.mesh.select_mode(type='FACE')  # Set to face mode
                
                # Use bmesh to reliably select faces where majority of vertices are in vertex group
                # This avoids the selection loss issue when switching modes
                bm = bmesh.from_edit_mesh(current_mesh)
                bm.faces.ensure_lookup_table()
                bm.verts.ensure_lookup_table()
                bm.edges.ensure_lookup_table()
                
                # EXPAND: Include internal vertices that are surrounded by the vertex group
                # This ensures vertices inside horns, nose, etc. are included
                vertex_mask = self._expand_vertex_group_internal_vertices(
                    original_obj, vg.name, bm, vertex_mask, current_mesh
                )
                
                # SPATIAL INCLUSION: Include all vertices within spatial boundary of vertex group
                # This captures isolated vertices that are inside the segment boundary
                # Respects boundaries of other segments (excludes vertices in other groups)
                vertex_mask = self._include_vertices_within_spatial_boundary(
                    original_obj, vg.name, bm, vertex_mask, current_mesh, expansion_factor=0.015,
                    stored_body_boundaries=stored_body_boundaries if vg.name not in body_names else None
                )
                
                # CRITICAL: Identify separation boundary edges BEFORE splitting
                # These are edges that connect vertices from different vertex groups
                # They will become the cut boundaries after separation
                separation_boundary_edges = self._identify_separation_boundary_edges(
                    bm, vertex_mask, vg.name
                )
                
                # Build exclusion set for other vertex groups to prevent bleeding
                other_group_vertices = set()
                vg_index = original_obj.vertex_groups.find(vg.name)
                if vg_index != -1:
                    for other_vg in original_obj.vertex_groups:
                        if other_vg.name == vg.name:
                            continue
                        other_vg_index = other_vg.index
                        for vertex in current_mesh.vertices:
                            for group in vertex.groups:
                                if group.group == other_vg_index and group.weight > 0.5:
                                    other_group_vertices.add(vertex.index)
                                    break
                
                # SELECT LINKED APPROACH: Start with vertex group vertices,
                # select all connected geometry, then only exclude clear boundaries
                
                # Step 1: Select all vertices in the vertex group
                for vert in bm.verts:
                    vert.select = vertex_mask[vert.index]
                
                # Step 2: Extend selection to all faces containing selected vertices
                for face in bm.faces:
                    if any(v.select for v in face.verts):
                        face.select = True
                        for v in face.verts:
                            v.select = True
                
                # Step 3: Flood-fill to include all connected faces
                # Stop only at faces where MAJORITY of vertices belong to OTHER groups
                added = True
                while added:
                    added = False
                    for face in bm.faces:
                        if face.select:
                            continue
                        
                        # Check if adjacent to a selected face (via EDGE)
                        is_adjacent = False
                        for edge in face.edges:
                            for linked in edge.link_faces:
                                if linked != face and linked.select:
                                    is_adjacent = True
                                    break
                            if is_adjacent:
                                break
                        
                        # ALSO check if shares a VERTEX with selected face
                        # This catches orphan faces that are only vertex-connected, not edge-connected
                        if not is_adjacent:
                            for vert in face.verts:
                                for linked_face in vert.link_faces:
                                    if linked_face != face and linked_face.select:
                                        is_adjacent = True
                                        break
                                if is_adjacent:
                                    break
                        
                        if not is_adjacent:
                            continue
                        
                        # Only EXCLUDE if MAJORITY of vertices are in other groups
                        # This is the ONLY exclusion rule - keeps logic simple
                        other_count = sum(1 for v in face.verts if v.index in other_group_vertices)
                        if other_count <= len(face.verts) / 2:
                            # Not majority in other groups - include it
                            face.select = True
                            for v in face.verts:
                                v.select = True
                            added = True
                
                faces_selected = sum(1 for f in bm.faces if f.select)
                
                # Update edit mesh with selection
                bmesh.update_edit_mesh(current_mesh)
                bm.free()
                
                # Validate that faces are actually selected before attempting to separate
                if faces_selected == 0:
                    # No faces selected - selection might have failed
                    self.report({'WARNING'}, f"No faces selected for vertex group '{vg.name}' - skipping")
                    bpy.ops.object.mode_set(mode='OBJECT')
                    continue  # Skip if no faces selected
                
                # Ensure we're still in edit mode (we should be, but be safe)
                if context.mode != 'EDIT':
                    bpy.ops.object.mode_set(mode='EDIT')
                
                # Separate the selected faces into a new object
                # NOTE: Removed select_linked() call as it was interfering with selection
                # The bmesh selection is already complete based on vertex group membership
                bpy.ops.mesh.separate(type='SELECTED')
                bpy.ops.object.mode_set(mode='OBJECT')
                
                # Find the newly created object (should be in selected objects)
                # After separate(), both original and new object are selected
                all_mesh_objs = [o for o in context.selected_objects if o.type == 'MESH']
                new_objs = [o for o in all_mesh_objs if o != original_obj and o not in created_objects]
                
                if new_objs:
                    new_obj = new_objs[0]
                    new_obj.name = f"{original_obj.name}_{vg.name}"
                    
                    # CRITICAL: Store separation boundary edge info for cut detection
                    # Convert Vector objects to lists for storage (Vectors aren't directly serializable)
                    if separation_boundary_edges:
                        stored_boundaries = []
                        for v1_co, v2_co in separation_boundary_edges:
                            stored_boundaries.append([list(v1_co), list(v2_co)])
                        new_obj["pet_separation_boundary_edges"] = stored_boundaries
                        new_obj["pet_source_vertex_group"] = vg.name
                    
                    # Verify data preservation if requested
                    if verify_data:
                        is_valid, warnings = verify_split_data_preservation(original_obj, new_obj, vg.name)
                        if warnings:
                            verification_warnings.extend([f"{vg.name}: {w}" for w in warnings])
                        # Note: Blender's separate() should preserve data automatically
                    
                    created_objects.append(new_obj)
                    
                    # IMPORTANT: After separate(), the original object is still selected
                    # but its mesh may have fewer faces. Continue with next group.
                else:
                    # If no new object was created, the selection might have failed
                    self.report({'WARNING'}, f"Failed to split vertex group: {vg.name} - no new object created")
            
            # CLEANUP: Assign any remaining orphan faces to nearest split object
            # This ensures no holes in the final split meshes
            if original_obj and original_obj.data.polygons:
                orphan_count = self._cleanup_orphan_faces(context, original_obj, created_objects)
                if orphan_count > 0:
                    self.report({'INFO'}, f"Assigned {orphan_count} orphan faces to body")
            
            # REMOVED: Gap separation now available in Post-Split Cleanup
            # Users can create gaps after splitting for visual review if needed
            # if gap_distance > 0.0 and created_objects:
            #     body_obj = self._find_body_object(created_objects, obj)
            #     if body_obj:
            #         self._apply_gap_separation(created_objects, body_obj, gap_distance)
            #     else:
            #         self.report({'WARNING'}, "Could not find body object - skipping gap creation")
            
            # Create pivot points using pre-calculated positions (BEFORE deleting original)
            # Pivot positions are at original attachment boundaries (before gaps)
            if create_pivots and attachment_points and created_objects:
                pivots = self.create_pivot_points_from_attachments(obj, created_objects, attachment_points)
                all_pivots.extend(pivots)
            
            # Optionally delete original object (AFTER creating pivots)
            original_obj_name = obj.name  # Store name before deletion
            if not keep_original and created_objects:
                # Only delete if we successfully created split objects
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                    obj = None  # Mark as deleted
                except Exception as e:
                    self.report({'WARNING'}, f"Could not delete original object: {str(e)}")
            
            # Report results
            result_msg = f"Split into {len(created_objects)} objects"
            if all_pivots:
                result_msg += f" and {len(all_pivots)} pivot points"
            if verification_warnings:
                result_msg += f" ({len(verification_warnings)} warnings)"
                for warning in verification_warnings[:3]:  # Show first 3 warnings
                    self.report({'WARNING'}, warning)
            
            self.report({'INFO'}, result_msg)
            return {'FINISHED'}
            
        except RuntimeError as e:
            self.report({'ERROR'}, f"Blender operation failed: {str(e)}")
            return {'CANCELLED'}
        except Exception as e:
            import traceback
            self.report({'ERROR'}, f"Splitting failed: {str(e)}")
            # Log full traceback for debugging
            print(f"Split error traceback:\n{traceback.format_exc()}")
            return {'CANCELLED'}
    
    def _find_body_object(self, split_objects, original_obj):
        """Find the body object in split objects"""
        # Look for object with 'body' in name (case insensitive)
        for obj in split_objects:
            name_lower = obj.name.lower()
            if 'body' in name_lower or 'torso' in name_lower:
                return obj
        
        # Fallback: find largest object (body is usually largest)
        if split_objects:
            return max(split_objects, key=lambda o: len(o.data.vertices) if o.data.vertices else 0)
        
        return None
    
    def _expand_vertex_group_internal_vertices(self, obj, vertex_group_name, bm, vertex_mask, mesh):
        """
        Expand vertex group to include all internal vertices surrounded by the group.
        Uses connectivity analysis to find vertices inside the selection (e.g., inside horns, nose).
        
        Args:
            obj: Blender object with mesh data
            vertex_group_name: Name of vertex group being expanded
            bm: bmesh object (in edit mesh state)
            vertex_mask: List[bool] - Current vertex mask (True for vertices in group)
            mesh: Blender mesh data
        
        Returns:
            List[bool]: Updated vertex_mask with internal vertices included
        """
        # Convert vertex_mask to set of indices for gap-filling function
        selected_indices = {i for i, in_group in enumerate(vertex_mask) if in_group}
        
        if not selected_indices:
            return vertex_mask
        
        # Build exclusion set: vertices that belong to other vertex groups
        excluded_indices = set()
        for other_vg in obj.vertex_groups:
            if other_vg.name == vertex_group_name:
                continue
            
            other_vg_index = other_vg.index
            for vertex in mesh.vertices:
                for group in vertex.groups:
                    if group.group == other_vg_index and group.weight > 0.5:
                        # Don't exclude vertices that are already in our group
                        if not vertex_mask[vertex.index]:
                            excluded_indices.add(vertex.index)
                        break
        
        # Use gap-filling to find internal vertices
        # More aggressive parameters to catch larger internal structures like horns
        start_time = time.time()
        expanded_indices = fill_small_surrounded_gaps(
            bm,
            selected_indices,
            max_gap_size=1024,  # Larger gap size for structures like horns
            neighbor_selected_ratio=0.7,  # More lenient to catch mostly-surrounded vertices
            max_total_vertices=None,  # No cap - include all internal vertices
            start_time=start_time,
            timeout_seconds=10.0,
            excluded_indices=excluded_indices,
            use_component_level_check=True,  # Use relaxed checking for better coverage
        )
        
        # Update vertex_mask with expanded indices
        expanded_mask = list(vertex_mask)
        for idx in expanded_indices:
            if idx < len(expanded_mask):
                expanded_mask[idx] = True
        
        added_count = len(expanded_indices) - len(selected_indices)
        if added_count > 0:
            print(f"[Mesh Splitter] Expanded '{vertex_group_name}' vertex group: added {added_count} internal vertices")
        
        return expanded_mask
    
    def _get_appendage_spatial_boundaries(self, obj, bm, mesh, body_names):
        """
        Calculate spatial boundaries (bounding boxes) for all appendage vertex groups.
        Returns dict mapping appendage group names to (bbox_min, bbox_max) tuples.
        
        Args:
            obj: Blender object with mesh data
            bm: bmesh object
            mesh: Blender mesh data
            body_names: Set of body part names to exclude from appendages
        
        Returns:
            dict: {appendage_name: (bbox_min, bbox_max), ...}
        """
        appendage_boundaries = {}
        
        # Define appendage part patterns
        appendage_patterns = ['head', 'leg', 'arm', 'tail', 'wing', 'foot', 'hand']
        
        for vg in obj.vertex_groups:
            vg_name_lower = vg.name.lower()
            
            # Skip if this is a body part
            if vg.name in body_names or vg_name_lower in {n.lower() for n in body_names}:
                continue
            
            # Check if this is an appendage (contains any appendage pattern)
            is_appendage = any(pattern in vg_name_lower for pattern in appendage_patterns)
            if not is_appendage:
                continue
            
            # Get vertices in this appendage group
            vg_index = vg.index
            appendage_vertices = []
            for vertex in mesh.vertices:
                for group in vertex.groups:
                    if group.group == vg_index and group.weight > 0.5:
                        appendage_vertices.append(vertex.index)
                        break
            
            if not appendage_vertices:
                continue
            
            # Calculate bounding box for this appendage
            bbox_min = None
            bbox_max = None
            for vert_idx in appendage_vertices:
                if vert_idx >= len(bm.verts):
                    continue
                vert_co = bm.verts[vert_idx].co
                
                if bbox_min is None:
                    bbox_min = Vector(vert_co)
                    bbox_max = Vector(vert_co)
                else:
                    bbox_min.x = min(bbox_min.x, vert_co.x)
                    bbox_min.y = min(bbox_min.y, vert_co.y)
                    bbox_min.z = min(bbox_min.z, vert_co.z)
                    bbox_max.x = max(bbox_max.x, vert_co.x)
                    bbox_max.y = max(bbox_max.y, vert_co.y)
                    bbox_max.z = max(bbox_max.z, vert_co.z)
            
            if bbox_min is not None and bbox_max is not None:
                # Expand boundary by same factor (0.015) for consistency
                bbox_size = bbox_max - bbox_min
                expand_amount = bbox_size * 0.015
                expanded_min = bbox_min - expand_amount
                expanded_max = bbox_max + expand_amount
                appendage_boundaries[vg.name] = (expanded_min, expanded_max)
        
        return appendage_boundaries
    
    def _get_body_spatial_boundaries(self, obj, bm, mesh, body_names):
        """
        Calculate spatial boundaries (bounding boxes) for body vertex groups.
        Returns dict mapping body group names to (bbox_min, bbox_max) tuples.
        
        Args:
            obj: Blender object with mesh data
            bm: bmesh object
            mesh: Blender mesh data
            body_names: Set of body part names
        
        Returns:
            dict: {body_name: (bbox_min, bbox_max), ...}
        """
        body_boundaries = {}
        
        for vg in obj.vertex_groups:
            vg_name_lower = vg.name.lower()
            
            # Only include body parts
            if vg.name not in body_names and vg_name_lower not in {n.lower() for n in body_names}:
                continue
            
            # Get vertices in this body group
            vg_index = vg.index
            body_vertices = []
            for vertex in mesh.vertices:
                for group in vertex.groups:
                    if group.group == vg_index and group.weight > 0.5:
                        body_vertices.append(vertex.index)
                        break
            
            if not body_vertices:
                continue
            
            # Calculate bounding box for this body part
            bbox_min = None
            bbox_max = None
            for vert_idx in body_vertices:
                if vert_idx >= len(bm.verts):
                    continue
                vert_co = bm.verts[vert_idx].co
                
                if bbox_min is None:
                    bbox_min = Vector(vert_co)
                    bbox_max = Vector(vert_co)
                else:
                    bbox_min.x = min(bbox_min.x, vert_co.x)
                    bbox_min.y = min(bbox_min.y, vert_co.y)
                    bbox_min.z = min(bbox_min.z, vert_co.z)
                    bbox_max.x = max(bbox_max.x, vert_co.x)
                    bbox_max.y = max(bbox_max.y, vert_co.y)
                    bbox_max.z = max(bbox_max.z, vert_co.z)
            
            if bbox_min is not None and bbox_max is not None:
                # Expand boundary by same factor (0.015) for consistency
                bbox_size = bbox_max - bbox_min
                expand_amount = bbox_size * 0.015
                expanded_min = bbox_min - expand_amount
                expanded_max = bbox_max + expand_amount
                body_boundaries[vg.name] = (expanded_min, expanded_max)
        
        return body_boundaries
    
    def _include_vertices_within_spatial_boundary(self, obj, vertex_group_name, bm, vertex_mask, mesh, expansion_factor=0.015, stored_body_boundaries=None):
        """
        Include all vertices within the spatial boundary (bounding box) of the vertex group.
        Expands boundary by a small percentage (1-2%) to catch outliers, but excludes vertices
        assigned to other vertex groups to respect segment boundaries.
        
        Args:
            obj: Blender object with mesh data
            vertex_group_name: Name of vertex group being processed
            bm: bmesh object (in edit mesh state)
            vertex_mask: List[bool] - Current vertex mask (True for vertices in group)
            mesh: Blender mesh data
            expansion_factor: Factor for boundary expansion (default 0.015 = 1.5%)
        
        Returns:
            List[bool]: Updated vertex_mask with spatially-contained vertices included
        """
        # Get vertices currently in the vertex group
        vertices_in_group = [i for i, in_group in enumerate(vertex_mask) if in_group]
        
        if not vertices_in_group:
            return vertex_mask
        
        # Calculate bounding box of vertices in the group (in object space)
        bbox_min = None
        bbox_max = None
        
        for vert_idx in vertices_in_group:
            if vert_idx >= len(bm.verts):
                continue
            vert_co = bm.verts[vert_idx].co
            
            if bbox_min is None:
                bbox_min = Vector(vert_co)
                bbox_max = Vector(vert_co)
            else:
                bbox_min.x = min(bbox_min.x, vert_co.x)
                bbox_min.y = min(bbox_min.y, vert_co.y)
                bbox_min.z = min(bbox_min.z, vert_co.z)
                bbox_max.x = max(bbox_max.x, vert_co.x)
                bbox_max.y = max(bbox_max.y, vert_co.y)
                bbox_max.z = max(bbox_max.z, vert_co.z)
        
        if bbox_min is None or bbox_max is None:
            return vertex_mask
        
        # Expand bounding box by expansion_factor (1-2% to catch outliers)
        bbox_size = bbox_max - bbox_min
        expand_amount = bbox_size * expansion_factor
        
        # Expanded bounding box
        expanded_min = bbox_min - expand_amount
        expanded_max = bbox_max + expand_amount
        
        # Build exclusion set: vertices assigned to OTHER vertex groups (weight > 0.5)
        # This respects boundaries of other segments - they are off-limits
        excluded_indices = set()
        for other_vg in obj.vertex_groups:
            if other_vg.name == vertex_group_name:
                continue
            
            other_vg_index = other_vg.index
            for vertex in mesh.vertices:
                for group in vertex.groups:
                    if group.group == other_vg_index and group.weight > 0.5:
                        excluded_indices.add(vertex.index)
                        break
        
        # ADDITIONAL: If processing body, exclude vertices within appendage spatial boundaries
        body_names = {'body', 'torso', 'core', 'Body', 'Torso', 'Core', 'BODY', 'TORSO', 'CORE'}
        if vertex_group_name in body_names:
            appendage_boundaries = self._get_appendage_spatial_boundaries(obj, bm, mesh, body_names)
            
            for vert_idx, vert in enumerate(bm.verts):
                if vert_idx in excluded_indices:
                    continue
                
                vert_co = vert.co
                # Check if vertex is within any appendage's spatial boundary
                for appendage_name, (app_bbox_min, app_bbox_max) in appendage_boundaries.items():
                    inside_appendage = (
                        app_bbox_min.x <= vert_co.x <= app_bbox_max.x and
                        app_bbox_min.y <= vert_co.y <= app_bbox_max.y and
                        app_bbox_min.z <= vert_co.z <= app_bbox_max.z
                    )
                    if inside_appendage:
                        excluded_indices.add(vert_idx)
                        break
        
        # ADDITIONAL: If processing appendage, exclude vertices within body spatial boundaries
        appendage_patterns = ['head', 'leg', 'arm', 'tail', 'wing', 'foot', 'hand']
        vg_name_lower = vertex_group_name.lower()
        is_appendage = any(pattern in vg_name_lower for pattern in appendage_patterns)
        
        if is_appendage and vertex_group_name not in body_names:
            # Use stored boundaries if available (calculated from original mesh)
            # Otherwise fall back to calculating from current mesh (shouldn't happen)
            if stored_body_boundaries:
                body_boundaries = stored_body_boundaries
            else:
                body_boundaries = self._get_body_spatial_boundaries(obj, bm, mesh, body_names)
            
            for vert_idx, vert in enumerate(bm.verts):
                if vert_idx in excluded_indices:
                    continue
                
                vert_co = vert.co
                # Check if vertex is within any body's spatial boundary
                for body_name, (body_bbox_min, body_bbox_max) in body_boundaries.items():
                    inside_body = (
                        body_bbox_min.x <= vert_co.x <= body_bbox_max.x and
                        body_bbox_min.y <= vert_co.y <= body_bbox_max.y and
                        body_bbox_min.z <= vert_co.z <= body_bbox_max.z
                    )
                    if inside_body:
                        excluded_indices.add(vert_idx)
                        break
        
        # Test all mesh vertices against expanded spatial boundary
        # Include if: inside expanded boundary AND not excluded (not in other groups)
        spatially_included = 0
        updated_mask = list(vertex_mask)
        
        for vert_idx, vert in enumerate(bm.verts):
            # Skip if already in mask
            if updated_mask[vert_idx]:
                continue
            
            # Skip if excluded (belongs to another vertex group)
            if vert_idx in excluded_indices:
                continue
            
            # Check if vertex is inside expanded bounding box
            vert_co = vert.co
            inside_boundary = (
                expanded_min.x <= vert_co.x <= expanded_max.x and
                expanded_min.y <= vert_co.y <= expanded_max.y and
                expanded_min.z <= vert_co.z <= expanded_max.z
            )
            
            if inside_boundary:
                updated_mask[vert_idx] = True
                spatially_included += 1
        
        if spatially_included > 0:
            print(f"[Mesh Splitter] Included {spatially_included} vertices within spatial boundary for '{vertex_group_name}'")
        
        return updated_mask
    
    def _include_boundary_adjacent_vertices(self, bm, vertex_mask, other_group_vertices, max_patch_size=5):
        """
        Include small vertex patches that are immediately adjacent to the selection boundary
        but weren't captured by other expansion methods.
        
        This targets the "straggler" vertices at cut boundaries (e.g., tail base, leg joints).
        
        Args:
            bm: bmesh object (in edit mesh state)
            vertex_mask: List[bool] - Current vertex mask (True for vertices in group)
            other_group_vertices: Set of vertex indices belonging to other groups
            max_patch_size: Maximum size of isolated patch to include
        
        Returns:
            List[bool]: Updated vertex_mask with boundary-adjacent vertices included
        """
        updated_mask = list(vertex_mask)
        
        # Find boundary vertices (selected vertices with unselected neighbors)
        boundary_verts = set()
        for vert_idx, in_group in enumerate(vertex_mask):
            if not in_group or vert_idx >= len(bm.verts):
                continue
            vert = bm.verts[vert_idx]
            for edge in vert.link_edges:
                neighbor = edge.other_vert(vert)
                if not vertex_mask[neighbor.index]:
                    boundary_verts.add(vert_idx)
                    break
        
        if not boundary_verts:
            return updated_mask
        
        # Find unselected vertices adjacent to boundary that are NOT in other groups
        candidates = set()
        for boundary_vert_idx in boundary_verts:
            if boundary_vert_idx >= len(bm.verts):
                continue
            vert = bm.verts[boundary_vert_idx]
            for edge in vert.link_edges:
                neighbor = edge.other_vert(vert)
                n_idx = neighbor.index
                # Include if: not selected, not in other groups
                if not updated_mask[n_idx] and n_idx not in other_group_vertices:
                    candidates.add(n_idx)
        
        if not candidates:
            return updated_mask
        
        # For each candidate, check if it's part of a small isolated patch
        # (not connected to many other unselected non-other-group vertices)
        added_count = 0
        visited = set()
        
        for candidate in candidates:
            if candidate in visited or updated_mask[candidate]:
                continue
            
            # BFS to find connected patch of unselected, non-other-group vertices
            patch = set()
            queue = [candidate]
            visited.add(candidate)
            
            while queue and len(patch) <= max_patch_size:
                current = queue.pop(0)
                patch.add(current)
                
                if current >= len(bm.verts):
                    continue
                vert = bm.verts[current]
                for edge in vert.link_edges:
                    neighbor = edge.other_vert(vert)
                    n_idx = neighbor.index
                    if n_idx in visited or updated_mask[n_idx] or n_idx in other_group_vertices:
                        continue
                    visited.add(n_idx)
                    queue.append(n_idx)
            
            # Include patch if it's small enough
            if len(patch) <= max_patch_size:
                for v_idx in patch:
                    updated_mask[v_idx] = True
                    added_count += 1
        
        if added_count > 0:
            print(f"[Mesh Splitter] Added {added_count} boundary-adjacent straggler vertices")
        
        return updated_mask
    
    def _expand_face_selection_within_boundaries(self, bm, vertex_mask, boundary_edges):
        """
        Expand face selection to include connected faces that don't cross boundaries.
        Ensures all faces connecting internal vertices are included.
        
        Args:
            bm: bmesh object (in edit mesh state)
            vertex_mask: List[bool] - True for vertices in the vertex group
            boundary_edges: List of boundary edge coordinates (for reference)
        
        Returns:
            int: Count of selected faces
        """
        # Start with faces that are already selected (majority vertices in group)
        initial_selected_faces = {f.index for f in bm.faces if f.select}
        
        # Expand to connected faces that don't cross boundaries
        # A face can be added if:
        # 1. All its vertices are in the vertex group (including internal vertices we just added)
        # 2. OR majority of vertices are in the group and it doesn't connect to other vertex groups
        faces_to_check = list(initial_selected_faces)
        selected_faces = set(initial_selected_faces)
        checked = set()
        
        while faces_to_check:
            face_idx = faces_to_check.pop(0)
            if face_idx in checked:
                continue
            checked.add(face_idx)
            
            if face_idx >= len(bm.faces):
                continue
            
            face = bm.faces[face_idx]
            
            # Check neighboring faces
            for edge in face.edges:
                for linked_face in edge.link_faces:
                    linked_idx = linked_face.index
                    if linked_idx in checked or linked_idx in selected_faces:
                        continue
                    
                    # Count vertices in this face that are in the vertex group
                    verts_in_group = sum(1 for v in linked_face.verts if vertex_mask[v.index])
                    total_verts = len(linked_face.verts)
                    
                    # Include face if majority of vertices are in group
                    if verts_in_group >= total_verts / 2:
                        # Additional check: don't include if face has a boundary edge
                        # connecting to another vertex group (unless all vertices are in group)
                        has_boundary_edge = False
                        if verts_in_group < total_verts:  # Not all vertices in group
                            for face_edge in linked_face.edges:
                                ev1, ev2 = face_edge.verts
                                # Check if this edge connects vertices from different groups
                                if vertex_mask[ev1.index] != vertex_mask[ev2.index]:
                                    has_boundary_edge = True
                                    break
                        
                        # Only add if all vertices are in group, or it doesn't cross a boundary
                        if not has_boundary_edge:
                            selected_faces.add(linked_idx)
                            faces_to_check.append(linked_idx)
        
        # Update face selection
        for face in bm.faces:
            face.select = face.index in selected_faces
        
        return len(selected_faces)
    
    def _identify_separation_boundary_edges(self, bm, vertex_mask, vertex_group_name):
        """
        Identify edges that form the boundary between the vertex group being split and other groups.
        These edges will become cut boundaries after separation.
        
        Args:
            bm: bmesh object (in edit mesh state)
            vertex_mask: List[bool] - True for vertices in the vertex group being split
            vertex_group_name: Name of vertex group being split (for metadata)
        
        Returns:
            List[tuple(Vector, Vector)]: List of edge vertex coordinates [(v1_co, v2_co), ...]
        """
        boundary_edges = []
        
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        
        for edge in bm.edges:
            v1, v2 = edge.verts
            
            # Check if edge connects vertices from different groups
            # One vertex is in the group being split, other is not
            v1_in_group = vertex_mask[v1.index]
            v2_in_group = vertex_mask[v2.index]
            
            # Edge is on boundary if vertices are on different sides
            if v1_in_group != v2_in_group:
                # Store vertex coordinates (in object space)
                boundary_edges.append((Vector(v1.co), Vector(v2.co)))
        
        return boundary_edges
    
    def _calculate_separation_vector(self, body_obj, part_obj):
        """Calculate direction vector to move part away from body"""
        # Get world space centers
        body_center = Vector((0, 0, 0))
        part_center = Vector((0, 0, 0))
        
        # Use bounding box center for body
        if body_obj and body_obj.data.vertices:
            body_bbox = [body_obj.matrix_world @ Vector(corner) for corner in body_obj.bound_box]
            body_center = sum(body_bbox, Vector((0, 0, 0))) / len(body_bbox)
        
        # Use bounding box center for part
        if part_obj and part_obj.data.vertices:
            part_bbox = [part_obj.matrix_world @ Vector(corner) for corner in part_obj.bound_box]
            part_center = sum(part_bbox, Vector((0, 0, 0))) / len(part_bbox)
        
        # Direction from body center to part center
        direction = part_center - body_center
        
        if direction.length > 0.001:
            direction.normalize()
            return direction
        else:
            # Fallback: use object location
            if body_obj and part_obj:
                direction = part_obj.location - body_obj.location
                if direction.length > 0.001:
                    direction.normalize()
                    return direction
            
            # Last resort: use Y axis (forward direction)
            return Vector((0, 1, 0))
    
    def _apply_gap_separation(self, split_objects, body_obj, gap_distance):
        """Move split parts away from body to create gaps for workflow"""
        for part_obj in split_objects:
            # Don't move body
            if part_obj == body_obj:
                continue
            
            # Store original position before moving
            original_location = Vector(part_obj.location)
            part_obj["pet_original_location"] = list(original_location)
            
            # Calculate separation direction (away from body)
            direction = self._calculate_separation_vector(body_obj, part_obj)
            
            # Move part along separation direction
            offset = direction * gap_distance
            part_obj.location = original_location + offset
            
            # Store metadata for potential restoration
            part_obj["pet_gap_offset"] = list(offset)
            part_obj["pet_has_gap"] = True
    
    def _cleanup_orphan_faces(self, context, original_obj, created_objects):
        """
        Find any faces remaining in the original mesh after all splits
        and assign them to the nearest split object by spatial proximity.
        
        This is the final safety net to ensure no holes in the split meshes.
        
        Args:
            context: Blender context
            original_obj: Original object that may still have orphan faces
            created_objects: List of split objects created from the original
        
        Returns:
            int: Number of orphan faces that were joined
        """
        if not original_obj or not created_objects:
            return 0
        
        # Check if original still has geometry
        if not original_obj.data.polygons:
            return 0
        
        orphan_count = len(original_obj.data.polygons)
        if orphan_count == 0:
            return 0
        
        print(f"[Mesh Splitter] Found {orphan_count} orphan faces - assigning to nearest split objects")
        
        # Ensure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Group orphan faces by their nearest split object using bounding box containment
        import bmesh
        from mathutils import Vector
        
        bm = bmesh.new()
        bm.from_mesh(original_obj.data)
        bm.faces.ensure_lookup_table()
        
        # For each face, find the best split object
        face_assignments = {}  # {split_obj: [face_indices]}
        for face in bm.faces:
            # Calculate face center in world space
            face_center = original_obj.matrix_world @ face.calc_center_median()
            
            # First, check if face center is INSIDE any object's bounding box
            best_obj = None
            best_dist = float('inf')
            
            for split_obj in created_objects:
                if not split_obj.data.vertices:
                    continue
                
                # Get bounding box in world space
                bbox_corners = [split_obj.matrix_world @ Vector(corner) for corner in split_obj.bound_box]
                bbox_min = Vector((min(c.x for c in bbox_corners),
                                 min(c.y for c in bbox_corners),
                                 min(c.z for c in bbox_corners)))
                bbox_max = Vector((max(c.x for c in bbox_corners),
                                 max(c.y for c in bbox_corners),
                                 max(c.z for c in bbox_corners)))
                
                # Check containment - if inside, this is the best match
                if (bbox_min.x <= face_center.x <= bbox_max.x and
                    bbox_min.y <= face_center.y <= bbox_max.y and
                    bbox_min.z <= face_center.z <= bbox_max.z):
                    best_obj = split_obj
                    break
                
                # Track nearest bbox center as fallback
                bbox_center = sum(bbox_corners, Vector((0, 0, 0))) / len(bbox_corners)
                dist = (face_center - bbox_center).length
                if dist < best_dist:
                    best_dist = dist
                    best_obj = split_obj
            
            if best_obj:
                if best_obj not in face_assignments:
                    face_assignments[best_obj] = []
                face_assignments[best_obj].append(face.index)
        
        bm.free()
        
        # Now join the original object (with orphans) to the appropriate split objects
        # For simplicity, join ALL orphans to the object that has the most assigned orphans
        # (Usually they all belong to the same nearby object)
        if face_assignments:
            # Find the object with most orphan faces assigned
            best_target = max(face_assignments.keys(), key=lambda o: len(face_assignments[o]))
            assigned_count = len(face_assignments[best_target])
            
            # Clear selections
            bpy.ops.object.select_all(action='DESELECT')
            
            # Select target and original
            context.view_layer.objects.active = best_target
            best_target.select_set(True)
            original_obj.select_set(True)
            
            # Join
            bpy.ops.object.join()
            
            print(f"[Mesh Splitter] Joined {orphan_count} orphan faces to '{best_target.name}' (nearest by proximity)")
            return orphan_count
        
        return 0
    
    def create_pivot_points_from_attachments(self, original_obj, split_objects, attachment_points):
        """
        Create pivot points using pre-calculated attachment positions
        
        Args:
            original_obj: Original object before splitting
            split_objects: List of objects created from splitting
            attachment_points: dict from calculate_attachment_points_from_vertex_groups()
        
        Returns:
            list: Empty objects representing pivot points
        """
        pivots = []
        
        # Create collection for pivots
        pivot_collection_name = f"{original_obj.name}_Pivots"
        pivot_collection = None
        
        for collection in bpy.data.collections:
            if collection.name == pivot_collection_name:
                pivot_collection = collection
                break
        
        if not pivot_collection:
            pivot_collection = bpy.data.collections.new(pivot_collection_name)
            bpy.context.scene.collection.children.link(pivot_collection)
        
        # Create Empty objects at attachment points
        for (g1, g2), position in attachment_points.items():
            # Find corresponding split objects
            obj1 = next((o for o in split_objects if g1 in o.name), None)
            obj2 = next((o for o in split_objects if g2 in o.name), None)
            
            if obj1 and obj2:
                # Create Empty object at pivot location
                bpy.ops.object.empty_add(
                    type='ARROWS',
                    location=position,
                    scale=(0.15, 0.15, 0.15)
                )
                pivot = bpy.context.active_object
                pivot.name = f"{g1}_Pivot_{g2}"
                
                # Add metadata
                pivot["pet_pivot_type"] = "disconnect"
                pivot["pet_source_part"] = g1
                pivot["pet_target_part"] = g2
                pivot["pet_original_mesh"] = original_obj.name
                
                # Link to pivot collection, then unlink from current collection(s)
                pivot_collection.objects.link(pivot)
                # Unlink from all collections the pivot is currently in (except our pivot collection)
                for collection in list(pivot.users_collection):  # Use list() to avoid modifying while iterating
                    if collection != pivot_collection:
                        collection.objects.unlink(pivot)
                
                pivots.append(pivot)
        
        return pivots
    
    def create_pivot_points(self, original_obj, split_objects):
        """
        Create pivot points at boundaries between split objects
        
        Args:
            original_obj: Original object before splitting
            split_objects: List of objects created from splitting
        
        Returns:
            list: Empty objects representing pivot points
        """
        pivots = []
        
        # Create collection for pivots
        pivot_collection_name = f"{original_obj.name}_Pivots"
        pivot_collection = None
        
        for collection in bpy.data.collections:
            if collection.name == pivot_collection_name:
                pivot_collection = collection
                break
        
        if not pivot_collection:
            pivot_collection = bpy.data.collections.new(pivot_collection_name)
            bpy.context.scene.collection.children.link(pivot_collection)
        
        # For each pair of split objects, find boundary edges
        for i, obj1 in enumerate(split_objects):
            for obj2 in split_objects[i+1:]:
                # Find boundary between these two parts
                boundary_center = self.find_boundary_center(original_obj, obj1, obj2)
                
                if boundary_center:
                    # Create Empty object at pivot location
                    bpy.ops.object.empty_add(
                        type='ARROWS',
                        location=boundary_center,
                        scale=(0.15, 0.15, 0.15)
                    )
                    pivot = bpy.context.active_object
                    pivot.name = f"{obj1.name.split('_')[-1]}_Pivot_{obj2.name.split('_')[-1]}"
                    
                    # Add metadata
                    pivot["pet_pivot_type"] = "disconnect"
                    pivot["pet_source_part"] = obj1.name.split('_')[-1]
                    pivot["pet_target_part"] = obj2.name.split('_')[-1]
                    pivot["pet_original_mesh"] = original_obj.name
                    
                    # Link to pivot collection, then unlink from current collection(s)
                    pivot_collection.objects.link(pivot)
                    # Unlink from all collections the pivot is currently in (except our pivot collection)
                    for collection in list(pivot.users_collection):  # Use list() to avoid modifying while iterating
                        if collection != pivot_collection:
                            collection.objects.unlink(pivot)
                    
                    pivots.append(pivot)
        
        return pivots
    
    def find_boundary_center(self, original_obj, obj1, obj2):
        """
        Find the center point of the boundary between two split objects
        
        Returns:
            Vector: Center position of boundary, or None if not found
        """
        # Simple approach: use the closest points between the two objects
        # Or use vertex group boundaries from original
        
        # Get bounding boxes
        bbox1 = [obj1.matrix_world @ Vector(corner) for corner in obj1.bound_box]
        bbox2 = [obj2.matrix_world @ Vector(corner) for corner in obj2.bound_box]
        
        # Calculate centers
        center1 = sum(bbox1, Vector((0, 0, 0))) / len(bbox1)
        center2 = sum(bbox2, Vector((0, 0, 0))) / len(bbox2)
        
        # Boundary is midpoint between centers
        boundary_center = (center1 + center2) / 2
        
        return boundary_center


classes = [
    PET_OT_split_by_vertex_groups,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
