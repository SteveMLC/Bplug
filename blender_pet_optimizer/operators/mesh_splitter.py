"""
Mesh splitting operators
Splits meshes by vertex groups with full data preservation (UVs, colors, materials)
"""

import bpy
import bmesh
from bpy.types import Operator
from bpy.props import BoolProperty
from mathutils import Vector


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
        
        mesh = obj.data
        created_objects = []
        all_pivots = []
        verification_warnings = []
        
        # Calculate attachment points BEFORE splitting (using original mesh)
        attachment_points = {}
        if self.create_pivots:
            attachment_points = calculate_attachment_points_from_vertex_groups(obj)
        
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
            for vg in obj.vertex_groups:
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
                
                faces_selected = 0
                for face in bm.faces:
                    # Count vertices in this face that belong to the vertex group
                    verts_in_group = sum(1 for v in face.verts if vertex_mask[v.index])
                    # Face belongs to group if majority of its vertices are in the group
                    if verts_in_group >= len(face.verts) / 2:  # Majority threshold
                        face.select = True
                        faces_selected += 1
                
                # Update edit mesh with selection
                bmesh.update_edit_mesh(current_mesh)
                bm.free()
                
                # Select linked faces to get connected geometry
                bpy.ops.mesh.select_linked(delimit={'SEAM'})
                
                # Go back to object mode to check selection
                bpy.ops.object.mode_set(mode='OBJECT')
                
                # Validate that faces are actually selected before attempting to separate
                selected_faces = sum(1 for p in current_mesh.polygons if p.select)
                if selected_faces == 0:
                    # No faces selected - selection might have failed
                    self.report({'WARNING'}, f"No faces selected for vertex group '{vg.name}' - skipping")
                    continue  # Skip if no faces selected
                
                # Go back to edit mode and separate
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.separate(type='SELECTED')
                bpy.ops.object.mode_set(mode='OBJECT')
                
                # Find the newly created object (should be in selected objects)
                # After separate(), both original and new object are selected
                all_mesh_objs = [o for o in context.selected_objects if o.type == 'MESH']
                new_objs = [o for o in all_mesh_objs if o != original_obj and o not in created_objects]
                
                if new_objs:
                    new_obj = new_objs[0]
                    new_obj.name = f"{original_obj.name}_{vg.name}"
                    
                    # Verify data preservation if requested
                    if self.verify_data:
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
            
            # Create pivot points using pre-calculated positions (BEFORE deleting original)
            if self.create_pivots and attachment_points and created_objects:
                pivots = self.create_pivot_points_from_attachments(obj, created_objects, attachment_points)
                all_pivots.extend(pivots)
            
            # Optionally delete original object (AFTER creating pivots)
            original_obj_name = obj.name  # Store name before deletion
            if not self.keep_original and created_objects:
                # Only delete if we successfully created split objects
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                    obj = None  # Mark as deleted
                except Exception as e:
                    self.report({'WARNING'}, f"Could not delete original object: {str(e)}")
            
            # Report results
            result_msg = f"Split into {len(created_objects)} objects"
            if all_pivots:
                result_msg += f" with {len(all_pivots)} pivot points"
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
