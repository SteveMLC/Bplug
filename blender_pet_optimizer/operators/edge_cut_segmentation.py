"""
Edge-loop based segment marking for efficient batch workflow
Select edge loops as cut boundaries, mark segments, remaining becomes body
Optimized for AI-generated 3D models (Huanyuan, etc.)
"""

import bpy
import bmesh
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty, StringProperty, IntProperty
from mathutils import Vector
import time

from ..utils.spatial_selection import (
    intelligent_select_head,
    intelligent_select_head_from_seeds,
    intelligent_select_leg,
    intelligent_select_tail,
    intelligent_select_wing,
    compute_selection_boundary_edges,
    compute_selection_boundary_rings,
)


class PET_OT_mark_segment_cut(Operator):
    """Mark selected edges as a segment cut boundary"""
    bl_idname = "pet.mark_segment_cut"
    bl_label = "Mark Segment Cut"
    bl_options = {'REGISTER', 'UNDO'}
    
    segment_name: EnumProperty(
        name="Segment Name",
        description="Name of the segment being cut off",
        items=[
            ('head', "Head", "Mark as head segment"),
            ('leg_front_l', "Front Left Leg", "Mark as front left leg"),
            ('leg_front_r', "Front Right Leg", "Mark as front right leg"),
            ('leg_back_l', "Back Left Leg", "Mark as back left leg"),
            ('leg_back_r', "Back Right Leg", "Mark as back right leg"),
            ('tail', "Tail", "Mark as tail segment"),
            ('wing_l', "Left Wing", "Mark as left wing"),
            ('wing_r', "Right Wing", "Mark as right wing"),
        ],
        default='head'
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Please switch to Edit mode and select edges")
            return {'CANCELLED'}
        
        # Ensure mesh is updated before accessing BMesh
        mesh = obj.data
        mesh.update()
        
        # Get fresh BMesh from edit mesh
        # Important: Always get a fresh BMesh reference to avoid stale data
        bm = bmesh.from_edit_mesh(mesh)
        
        # Ensure lookup tables are built before accessing elements
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        # Validate BMesh is still valid by accessing a property
        try:
            _ = len(bm.edges)
        except ReferenceError:
            # BMesh was invalidated - get a fresh one
            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
        
        # Collect selected edges immediately while BMesh is valid
        selected_edges = [e for e in bm.edges if e.select]
        
        if not selected_edges:
            self.report({'ERROR'}, "Please select edges to mark as cut boundary")
            bmesh.update_edit_mesh(mesh)
            return {'CANCELLED'}
        
        # Get or create layers - do this before iterating edges
        # Wrap in try-except to handle potential ReferenceError
        try:
            cut_layer = bm.edges.layers.int.get("pet_segment_cut")
            if not cut_layer:
                cut_layer = bm.edges.layers.int.new("pet_segment_cut")
            
            name_layer = bm.edges.layers.string.get("pet_segment_name")
            if not name_layer:
                name_layer = bm.edges.layers.string.new("pet_segment_name")
        except ReferenceError:
            # BMesh became invalid - refresh and retry
            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            
            # Re-collect selected edges
            selected_edges = [e for e in bm.edges if e.select]
            if not selected_edges:
                self.report({'ERROR'}, "Please select edges to mark as cut boundary")
                bmesh.update_edit_mesh(mesh)
                return {'CANCELLED'}
            
            # Get or create layers again
            cut_layer = bm.edges.layers.int.get("pet_segment_cut")
            if not cut_layer:
                cut_layer = bm.edges.layers.int.new("pet_segment_cut")
            
            name_layer = bm.edges.layers.string.get("pet_segment_name")
            if not name_layer:
                name_layer = bm.edges.layers.string.new("pet_segment_name")
        
        segment_id = self._get_segment_id(self.segment_name)
        
        # Mark selected edges
        for edge in selected_edges:
            edge[cut_layer] = segment_id
            edge[name_layer] = self.segment_name.encode('utf-8')
        
        # Update edit mesh to apply changes
        bmesh.update_edit_mesh(mesh)
        
        if "pet_marked_segments" not in obj:
            obj["pet_marked_segments"] = []
        
        marked = list(obj.get("pet_marked_segments", []))
        if self.segment_name not in marked:
            marked.append(self.segment_name)
            obj["pet_marked_segments"] = marked
        
        self.report({'INFO'}, f"Marked {len(selected_edges)} edges as '{self.segment_name}' cut boundary")
        return {'FINISHED'}
    
    def _get_segment_id(self, name):
        segment_ids = {
            'head': 1,
            'leg_front_l': 2,
            'leg_front_r': 3,
            'leg_back_l': 4,
            'leg_back_r': 5,
            'tail': 6,
            'wing_l': 7,
            'wing_r': 8,
        }
        return segment_ids.get(name, 0)


class PET_OT_clear_segment_cuts(Operator):
    """Clear all segment cut markings"""
    bl_idname = "pet.clear_segment_cuts"
    bl_label = "Clear Segment Cuts"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        was_in_edit = context.mode == 'EDIT_MESH'
        if was_in_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        cut_layer = bm.edges.layers.int.get("pet_segment_cut")
        if cut_layer:
            bm.edges.layers.int.remove(cut_layer)
        
        name_layer = bm.edges.layers.string.get("pet_segment_name")
        if name_layer:
            bm.edges.layers.string.remove(name_layer)
        
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        
        if "pet_marked_segments" in obj:
            del obj["pet_marked_segments"]
        
        if was_in_edit:
            bpy.ops.object.mode_set(mode='EDIT')
        
        self.report({'INFO'}, "Cleared all segment cut markings")
        return {'FINISHED'}


class PET_OT_apply_segment_cuts(Operator):
    """Apply marked cuts to create vertex groups (remaining mesh becomes body)"""
    bl_idname = "pet.apply_segment_cuts"
    bl_label = "Apply Segment Cuts"
    bl_options = {'REGISTER', 'UNDO'}
    
    keep_markings: BoolProperty(
        name="Keep Markings",
        description="Keep edge markings after applying",
        default=False
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode == 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        mesh = obj.data
        
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        cut_layer = bm.edges.layers.int.get("pet_segment_cut")
        name_layer = bm.edges.layers.string.get("pet_segment_name")
        
        if not cut_layer:
            self.report({'ERROR'}, "No segment cuts marked. Please mark cuts first.")
            bm.free()
            return {'CANCELLED'}
        
        cut_edges = {}
        for edge in bm.edges:
            segment_id = edge[cut_layer]
            if segment_id > 0:
                segment_name = edge[name_layer].decode('utf-8') if name_layer else f"segment_{segment_id}"
                if segment_name not in cut_edges:
                    cut_edges[segment_name] = []
                cut_edges[segment_name].append(edge)
        
        if not cut_edges:
            self.report({'ERROR'}, "No segment cuts found")
            bm.free()
            return {'CANCELLED'}
        
        obj.vertex_groups.clear()
        
        all_verts = set(range(len(bm.verts)))
        segment_verts = {}
        
        for segment_name, edges in cut_edges.items():
            boundary_verts = set()
            for edge in edges:
                for vert in edge.verts:
                    boundary_verts.add(vert.index)
            
            segment_verts[segment_name] = self._flood_fill_segment(
                bm, boundary_verts, all_verts, segment_name
            )
        
        body_verts = all_verts.copy()
        for verts in segment_verts.values():
            body_verts -= verts
        
        for segment_name, verts in segment_verts.items():
            if verts:
                vg = obj.vertex_groups.new(name=segment_name)
                vg.add(list(verts), 1.0, 'REPLACE')
        
        if body_verts:
            body_vg = obj.vertex_groups.new(name="body")
            body_vg.add(list(body_verts), 1.0, 'REPLACE')
        
        if not self.keep_markings:
            if cut_layer:
                bm.edges.layers.int.remove(cut_layer)
            if name_layer:
                bm.edges.layers.string.remove(name_layer)
            if "pet_marked_segments" in obj:
                del obj["pet_marked_segments"]
        
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        
        total_segments = len(segment_verts) + (1 if body_verts else 0)
        self.report({'INFO'}, f"Created {total_segments} vertex groups from segment cuts")
        return {'FINISHED'}
    
    def _flood_fill_segment(self, bm, boundary_verts, all_verts, segment_name):
        """Flood fill from boundary to find segment vertices (away from body center)"""
        segment_name_lower = segment_name.lower()
        
        mesh_center = Vector((0, 0, 0))
        for vert in bm.verts:
            mesh_center += vert.co
        mesh_center /= len(bm.verts)
        
        min_z = min(v.co.z for v in bm.verts)
        max_z = max(v.co.z for v in bm.verts)
        min_y = min(v.co.y for v in bm.verts)
        max_y = max(v.co.y for v in bm.verts)
        
        seed_verts = set()
        for boundary_idx in boundary_verts:
            vert = bm.verts[boundary_idx]
            for edge in vert.link_edges:
                other_vert = edge.other_vert(vert)
                if other_vert.index not in boundary_verts:
                    is_appendage_side = False
                    
                    if 'head' in segment_name_lower:
                        is_appendage_side = other_vert.co.y > vert.co.y or other_vert.co.z > vert.co.z
                    elif 'leg' in segment_name_lower:
                        is_appendage_side = other_vert.co.z < vert.co.z
                    elif 'tail' in segment_name_lower:
                        is_appendage_side = other_vert.co.y < vert.co.y
                    elif 'wing' in segment_name_lower:
                        if '_l' in segment_name_lower:
                            is_appendage_side = other_vert.co.x > vert.co.x
                        else:
                            is_appendage_side = other_vert.co.x < vert.co.x
                    
                    if is_appendage_side:
                        seed_verts.add(other_vert.index)
        
        if not seed_verts:
            for boundary_idx in boundary_verts:
                vert = bm.verts[boundary_idx]
                for edge in vert.link_edges:
                    other_vert = edge.other_vert(vert)
                    if other_vert.index not in boundary_verts:
                        to_center = (mesh_center - other_vert.co).length
                        from_center = (mesh_center - vert.co).length
                        if to_center > from_center:
                            seed_verts.add(other_vert.index)
        
        if not seed_verts:
            return boundary_verts
        
        segment = boundary_verts.copy()
        to_visit = list(seed_verts)
        visited = set()
        
        while to_visit:
            vert_idx = to_visit.pop()
            if vert_idx in visited or vert_idx in boundary_verts:
                continue
            
            visited.add(vert_idx)
            segment.add(vert_idx)
            
            vert = bm.verts[vert_idx]
            for edge in vert.link_edges:
                other_vert = edge.other_vert(vert)
                if other_vert.index not in visited and other_vert.index not in boundary_verts:
                    to_visit.append(other_vert.index)
        
        return segment


class PET_OT_select_segment_edges(Operator):
    """Select edges marked for a specific segment"""
    bl_idname = "pet.select_segment_edges"
    bl_label = "Select Segment Edges"
    bl_options = {'REGISTER', 'UNDO'}
    
    segment_name: StringProperty(
        name="Segment Name",
        description="Name of segment to select edges for",
        default=""
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')
        
        bm = bmesh.from_edit_mesh(obj.data)
        
        cut_layer = bm.edges.layers.int.get("pet_segment_cut")
        name_layer = bm.edges.layers.string.get("pet_segment_name")
        
        if not cut_layer or not name_layer:
            self.report({'WARNING'}, "No segment cuts marked")
            return {'CANCELLED'}
        
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type='EDGE')
        
        count = 0
        for edge in bm.edges:
            if edge[cut_layer] > 0:
                stored_name = edge[name_layer].decode('utf-8')
                if not self.segment_name or stored_name == self.segment_name:
                    edge.select = True
                    count += 1
        
        bmesh.update_edit_mesh(obj.data)
        
        self.report({'INFO'}, f"Selected {count} edges")
        return {'FINISHED'}


class PET_OT_preview_segment_cuts(Operator):
    """Preview how segments will be split based on current edge markings"""
    bl_idname = "pet.preview_segment_cuts"
    bl_label = "Preview Segment Cuts"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode == 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        
        cut_layer = bm.edges.layers.int.get("pet_segment_cut")
        
        if not cut_layer:
            self.report({'WARNING'}, "No segment cuts marked. Mark edge loops first.")
            bm.free()
            return {'CANCELLED'}
        
        marked_segments = obj.get("pet_marked_segments", [])
        cut_count = sum(1 for e in bm.edges if e[cut_layer] > 0)
        
        bm.free()
        
        info = f"Marked segments: {', '.join(marked_segments) if marked_segments else 'None'}. "
        info += f"Cut edges: {cut_count}. Remaining mesh will become 'body'."
        
        self.report({'INFO'}, info)
        return {'FINISHED'}


class PET_OT_find_edge_loop_for_part(Operator):
    """Automatically find edge loop for a part using grow/auto-grow boundary logic"""
    bl_idname = "pet.find_edge_loop_for_part"
    bl_label = "Find Edge Loop for Part"
    bl_options = {'REGISTER', 'UNDO'}
    
    part_type: EnumProperty(
        name="Part Type",
        description="Type of part to find edge loop for",
        items=[
            ('head', "Head", "Find edge loop for head"),
            ('leg_front_l', "Front Left Leg", "Find edge loop for front left leg"),
            ('leg_front_r', "Front Right Leg", "Find edge loop for front right leg"),
            ('leg_back_l', "Back Left Leg", "Find edge loop for back left leg"),
            ('leg_back_r', "Back Right Leg", "Find edge loop for back right leg"),
            ('tail', "Tail", "Find edge loop for tail"),
            ('wing_l', "Left Wing", "Find edge loop for left wing"),
            ('wing_r', "Right Wing", "Find edge loop for right wing"),
        ],
        default='head'
    )
    
    use_selected_as_seed: BoolProperty(
        name="Use Selected as Seed",
        description="Use current vertex selection as seed for part detection",
        default=True
    )
    
    close_loop_tolerance: IntProperty(
        name="Close Loop Tolerance",
        description="Maximum number of edges to bridge when closing a loop",
        default=5,
        min=0,
        max=20
    )
    
    def execute(self, context):
        start_time = time.time()
        TIMEOUT_SECONDS = 30.0
        MAX_VERTS_DIRECT = 100000
        
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Check mesh size for performance
        total_verts = len(obj.data.vertices)
        if total_verts > MAX_VERTS_DIRECT:
            use_progress = True
            context.window_manager.progress_begin(0, 100)
        else:
            use_progress = False
        
        try:
            # Get pet type from settings
            settings = context.scene.pet_segmentation_settings
            pet_type = settings.pet_type if hasattr(settings, 'pet_type') else 'quadruped'
            invert_forward_axis = settings.invert_forward_axis if hasattr(settings, 'invert_forward_axis') else False
            
            # Ensure we're in Edit mode
            was_in_edit = context.mode == 'EDIT_MESH'
            if not was_in_edit:
                bpy.ops.object.mode_set(mode='EDIT')
            
            mesh = obj.data
            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            
            # Check timeout
            if time.time() - start_time > TIMEOUT_SECONDS:
                self.report({'WARNING'}, "Operation timed out. Try with a smaller selection or decimated mesh.")
                bmesh.update_edit_mesh(mesh)
                return {'CANCELLED'}
            
            # Get part selection using intelligent selection
            if use_progress:
                context.window_manager.progress_update(10)
            
            selected_indices = self._get_part_selection(
                context, obj, bm, self.part_type, self.use_selected_as_seed,
                pet_type, invert_forward_axis
            )
            
            if not selected_indices:
                self.report({'ERROR'}, f"Could not find part selection for {self.part_type}. Try selecting vertices first, then use 'Use Selected as Seed'.")
                bmesh.update_edit_mesh(mesh)
                return {'CANCELLED'}
            
            if len(selected_indices) > total_verts * 0.6:
                self.report({'WARNING'}, f"Selection is very large ({len(selected_indices)} vertices). The boundary may not be accurate. Consider refining your selection.")
            
            # Check timeout
            if time.time() - start_time > TIMEOUT_SECONDS:
                self.report({'WARNING'}, "Operation timed out during part selection.")
                bmesh.update_edit_mesh(mesh)
                return {'CANCELLED'}
            
            # Extract boundary edges
            if use_progress:
                context.window_manager.progress_update(30)
            
            # Check for existing vertex groups to avoid crossing into other parts
            excluded_indices = set()
            if obj.vertex_groups:
                # Get vertices already assigned to other parts
                for vg in obj.vertex_groups:
                    if vg.name != self.part_type and vg.name != 'body':
                        vg_index = vg.index
                        for vert in obj.data.vertices:
                            for group in vert.groups:
                                if group.group == vg_index and group.weight > 0.5:
                                    excluded_indices.add(vert.index)
                                    break
            
            boundary_edges = compute_selection_boundary_edges(bm, selected_indices, excluded_indices)
            
            if not boundary_edges:
                self.report({'WARNING'}, f"No boundary edges found for {self.part_type}. The selection may be too large or the mesh topology may be unusual.")
                bmesh.update_edit_mesh(mesh)
                return {'CANCELLED'}
            
            # Check timeout
            if time.time() - start_time > TIMEOUT_SECONDS:
                self.report({'WARNING'}, "Operation timed out during boundary extraction.")
                bmesh.update_edit_mesh(mesh)
                return {'CANCELLED'}
            
            # Form edge loops
            if use_progress:
                context.window_manager.progress_update(50)
            
            vertex_loops = compute_selection_boundary_rings(
                bm, boundary_edges, self.close_loop_tolerance
            )
            
            if not vertex_loops:
                # Fallback: select all boundary edges even if they don't form perfect loops
                self.report({'WARNING'}, f"Could not form complete edge loops for {self.part_type}. Selecting best boundary path instead.")
                selected_edges = self._boundary_edges_to_edge_objects(bm, boundary_edges)
            else:
                # Check if loops are fragmented (multiple small loops might indicate issues)
                if len(vertex_loops) > 1:
                    total_loop_length = sum(len(loop) for loop in vertex_loops)
                    if total_loop_length < 10:
                        self.report({'WARNING'}, f"Found {len(vertex_loops)} small loops. The boundary may be fragmented. Results may need manual refinement.")
                
                # Convert vertex loops to edge selection
                if use_progress:
                    context.window_manager.progress_update(70)
                
                selected_edges = self._vertex_loops_to_edges(bm, vertex_loops, boundary_edges)
                
                if not selected_edges:
                    # Fallback to all boundary edges
                    self.report({'WARNING'}, f"Could not convert loops to edges. Selecting all boundary edges instead.")
                    selected_edges = self._boundary_edges_to_edge_objects(bm, boundary_edges)
            
            if not selected_edges:
                self.report({'ERROR'}, f"Could not find any edges to select for {self.part_type}. Please check your selection.")
                bmesh.update_edit_mesh(mesh)
                return {'CANCELLED'}
            
            # Check timeout
            if time.time() - start_time > TIMEOUT_SECONDS:
                self.report({'WARNING'}, "Operation timed out. Partial selection applied.")
            
            # Select edges in Edit mode
            if use_progress:
                context.window_manager.progress_update(90)
            
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.mesh.select_mode(type='EDGE')
            
            for edge in selected_edges:
                edge.select = True
            
            bmesh.update_edit_mesh(mesh)
            
            elapsed = time.time() - start_time
            self.report({'INFO'}, f"Found and selected {len(selected_edges)} edges for {self.part_type} ({elapsed:.1f}s)")
            return {'FINISHED'}
        
        except Exception as e:
            import traceback
            self.report({'ERROR'}, f"Error finding edge loop: {str(e)}")
            print(f"Error traceback:\n{traceback.format_exc()}")
            return {'CANCELLED'}
        
        finally:
            if use_progress:
                context.window_manager.progress_end()
    
    def _get_part_selection(self, context, obj, bm, part_type, use_selected_as_seed, pet_type, invert_forward_axis):
        """Get vertex selection for the part using intelligent selection functions"""
        selected_indices = set()
        
        if use_selected_as_seed:
            # Use current vertex selection as seeds
            seed_indices = {v.index for v in bm.verts if v.select}
            
            if seed_indices:
                # Use seed-based selection
                if part_type == 'head':
                    selected_indices = intelligent_select_head_from_seeds(
                        seed_indices, obj, bm, invert_forward_axis=invert_forward_axis
                    )
                elif part_type.startswith('leg_') or part_type in ('leg_l', 'leg_r'):
                    # For legs, use first seed
                    seed = next(iter(seed_indices))
                    leg_side = 'left' if part_type.endswith('_l') else 'right'
                    leg_position = 'front' if 'front' in part_type else 'back'
                    selected_indices = intelligent_select_leg(seed, obj, bm, leg_side, leg_position)
                elif part_type == 'tail':
                    seed = next(iter(seed_indices))
                    selected_indices = intelligent_select_tail(seed, obj, bm)
                elif part_type.startswith('wing_'):
                    seed = next(iter(seed_indices))
                    wing_side = 'left' if part_type.endswith('_l') else 'right'
                    selected_indices = intelligent_select_wing(seed, obj, bm, wing_side)
        else:
            # Auto-detect part location - try to find part using intelligent selection
            # For now, we'll try to find a representative vertex based on part type
            # In practice, this could be enhanced with a click-to-select modal
            # For now, return empty set and let the user know they need to select vertices
            # The UI should guide users to select vertices first
            return set()
        
        return selected_indices
    
    def _vertex_loops_to_edges(self, bm, vertex_loops, boundary_edges):
        """Convert vertex loops to actual edge objects for selection"""
        selected_edges = []
        boundary_edge_set = boundary_edges
        
        # Create a mapping from (v1, v2) tuples to edge objects
        # boundary_edges contains tuples in canonical order (v1 < v2)
        edge_map = {}
        for edge in bm.edges:
            v1_idx = edge.verts[0].index
            v2_idx = edge.verts[1].index
            # Store in canonical order
            if v1_idx < v2_idx:
                edge_map[(v1_idx, v2_idx)] = edge
            else:
                edge_map[(v2_idx, v1_idx)] = edge
        
        # For each vertex loop, find the edges connecting consecutive vertices
        for loop in vertex_loops:
            if len(loop) < 2:
                continue
            
            # Connect consecutive vertices in the loop
            for i in range(len(loop)):
                v1_idx = loop[i]
                v2_idx = loop[(i + 1) % len(loop)]  # Wrap around for closed loops
                
                # Create canonical edge key
                edge_key = (v1_idx, v2_idx) if v1_idx < v2_idx else (v2_idx, v1_idx)
                
                # Check if this edge is in the boundary
                if edge_key in boundary_edge_set:
                    edge = edge_map.get(edge_key)
                    if edge and edge not in selected_edges:
                        selected_edges.append(edge)
        
        return selected_edges
    
    def _boundary_edges_to_edge_objects(self, bm, boundary_edges):
        """Fallback: convert boundary edge tuples directly to edge objects"""
        selected_edges = []
        edge_map = {}
        
        # Create mapping from (v1, v2) tuples to edge objects
        for edge in bm.edges:
            v1_idx = edge.verts[0].index
            v2_idx = edge.verts[1].index
            # Store in canonical order
            if v1_idx < v2_idx:
                edge_map[(v1_idx, v2_idx)] = edge
            else:
                edge_map[(v2_idx, v1_idx)] = edge
        
        # Select all boundary edges
        for edge_key in boundary_edges:
            edge = edge_map.get(edge_key)
            if edge and edge not in selected_edges:
                selected_edges.append(edge)
        
        return selected_edges


classes = [
    PET_OT_mark_segment_cut,
    PET_OT_clear_segment_cuts,
    PET_OT_apply_segment_cuts,
    PET_OT_select_segment_edges,
    PET_OT_preview_segment_cuts,
    PET_OT_find_edge_loop_for_part,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
