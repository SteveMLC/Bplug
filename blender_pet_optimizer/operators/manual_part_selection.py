"""
Manual Part Selection Operators

Provides operators for manual part-by-part segmentation with intelligent
auto-selection based on spatial awareness. Users click on the model to
auto-select vertices for each body part, then manually adjust and save.
"""

import bpy
import bmesh
import time
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, EnumProperty
from mathutils import Vector
import bpy_extras.view3d_utils

from ..utils.spatial_selection import (
    intelligent_select_head,
    intelligent_select_leg,
    intelligent_select_tail,
    intelligent_select_wing,
    intelligent_select_body,
    generic_bfs_expand
)
from ..utils import segmentation_templates


# Part definitions for each pet type
PART_DEFINITIONS = {
    'quadruped': ['head', 'leg_front_l', 'leg_front_r', 'leg_back_l', 'leg_back_r', 'tail', 'body'],
    'biped': ['head', 'arm_l', 'arm_r', 'leg_l', 'leg_r', 'tail', 'body'],
    'flying': ['head', 'wing_l', 'wing_r', 'leg_front_l', 'leg_front_r', 'leg_back_l', 'leg_back_r', 'tail', 'body'],
}


def get_part_display_name(part_name):
    """Get user-friendly display name for a part."""
    display_names = {
        'head': 'HEAD',
        'leg_front_l': 'Front Left Leg',
        'leg_front_r': 'Front Right Leg',
        'leg_back_l': 'Back Left Leg',
        'leg_back_r': 'Back Right Leg',
        'leg_l': 'Left Leg',
        'leg_r': 'Right Leg',
        'arm_l': 'Left Arm',
        'arm_r': 'Right Arm',
        'wing_l': 'Left Wing',
        'wing_r': 'Right Wing',
        'tail': 'TAIL',
        'body': 'BODY',
    }
    return display_names.get(part_name, part_name.upper())


class PET_OT_start_manual_part_selection(Operator):
    """Start manual part selection mode - select parts one by one with intelligent auto-selection"""
    bl_idname = "pet.start_manual_part_selection"
    bl_label = "Start Manual Part Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Get pet type from segmentation settings
        settings = context.scene.pet_segmentation_settings
        pet_type = settings.pet_type if hasattr(settings, 'pet_type') else 'quadruped'
        
        # Get part list for this pet type
        part_list = PART_DEFINITIONS.get(pet_type, PART_DEFINITIONS['quadruped']).copy()
        
        # Initialize manual part selection state
        state = context.scene.pet_manual_part_selection_state
        state.is_active = True
        state.current_part = part_list[0] if part_list else 'head'
        state.current_part_index = 0
        state.total_parts = len(part_list)
        state.current_selection_vertex_count = 0
        
        # Store part list on object
        obj["pet_manual_part_list"] = part_list
        obj["pet_manual_completed_parts"] = []
        obj["pet_manual_pet_type"] = pet_type
        
        # Clear existing vertex groups if requested
        if settings.clear_existing:
            obj.vertex_groups.clear()
        
        # Create empty vertex groups for all parts
        for part_name in part_list:
            if part_name not in obj.vertex_groups:
                obj.vertex_groups.new(name=part_name)
        
        # Switch to Edit mode
        if context.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        # Deselect all vertices
        bpy.ops.mesh.select_all(action='DESELECT')
        
        self.report({'INFO'}, f"Manual part selection started. First part: {get_part_display_name(state.current_part)}")
        return {'FINISHED'}


class PET_OT_select_part_to_assign(Operator):
    """Select which part to assign next"""
    bl_idname = "pet.select_part_to_assign"
    bl_label = "Select Part"
    bl_options = {'REGISTER', 'UNDO'}
    
    part_name: StringProperty(
        name="Part Name",
        description="Name of the part to assign"
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        state = context.scene.pet_manual_part_selection_state
        if not state.is_active:
            self.report({'ERROR'}, "Manual part selection is not active")
            return {'CANCELLED'}
        
        part_list = obj.get("pet_manual_part_list", [])
        if self.part_name not in part_list:
            self.report({'ERROR'}, f"Part '{self.part_name}' not in part list")
            return {'CANCELLED'}
        
        # Update current part
        state.current_part = self.part_name
        state.current_part_index = part_list.index(self.part_name)
        
        # Switch to Edit mode and deselect all
        if context.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        
        self.report({'INFO'}, f"Now assigning: {get_part_display_name(self.part_name)}")
        return {'FINISHED'}


class PET_OT_click_to_assign_part(Operator):
    """Click on model to auto-select vertices for the current part"""
    bl_idname = "pet.click_to_assign_part"
    bl_label = "Click to Assign Part"
    bl_options = {'REGISTER', 'UNDO'}
    
    part_type: StringProperty(
        name="Part Type",
        description="Type of part to select (head, leg_front_l, etc.)"
    )
    
    def invoke(self, context, event):
        """Called when operator is activated"""
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        state = context.scene.pet_manual_part_selection_state
        if not state.is_active:
            self.report({'ERROR'}, "Manual part selection is not active. Click 'Start Manual Part Selection' first.")
            return {'CANCELLED'}
        
        # Ensure we're in Edit mode
        if context.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        # Store initial state
        self.obj = obj
        self.part_type = self.part_type or state.current_part
        
        # Set up modal handler
        context.window_manager.modal_handler_add(self)
        
        # Update UI status
        self.report({'INFO'}, f"Click on model to auto-select {get_part_display_name(self.part_type)}")
        
        # Change cursor to crosshair
        context.window.cursor_set('CROSSHAIR')
        
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        """Handle modal events"""
        # ESCAPE or RIGHT CLICK: Cancel and exit
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            context.window.cursor_set('DEFAULT')
            self.report({'INFO'}, "Selection cancelled")
            return {'CANCELLED'}
        
        # LEFTMOUSE CLICK: Perform auto-selection
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Only handle clicks in 3D viewport
            if context.area and context.area.type == 'VIEW_3D':
                # Perform ray casting to find clicked vertex
                start_vertex_idx = self._ray_cast_to_vertex(context, event)
                
                if start_vertex_idx is not None:
                    # Call intelligent spatial selection function
                    selected_verts = self._intelligent_select(context, start_vertex_idx, self.part_type)
                    
                    if selected_verts:
                        # Update viewport selection with auto-selected vertices
                        self._update_selection(context, selected_verts)
                        
                        # Update state
                        state = context.scene.pet_manual_part_selection_state
                        state.current_selection_vertex_count = len(selected_verts)
                        
                        # Exit modal mode (selection done, user can now adjust)
                        context.window.cursor_set('DEFAULT')
                        self.report({'INFO'}, f"Auto-selected {len(selected_verts)} vertices for {get_part_display_name(self.part_type)}")
                        return {'FINISHED'}
                    else:
                        self.report({'WARNING'}, "No vertices selected. Try clicking on a different area.")
                else:
                    self.report({'WARNING'}, "Could not find vertex at click position. Click directly on the model.")
        
        return {'RUNNING_MODAL'}
    
    def _ray_cast_to_vertex(self, context, event):
        """Cast ray from click position to find nearest vertex"""
        region = context.region
        rv3d = context.region_data
        
        if not region or not rv3d:
            return None
        
        # Get mouse position in viewport coordinates
        mouse_pos = (event.mouse_region_x, event.mouse_region_y)
        
        # Cast ray into 3D space
        origin = bpy_extras.view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse_pos)
        direction = bpy_extras.view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse_pos)
        
        if origin is None or direction is None:
            return None
        
        # Use scene ray cast for accurate hit detection
        depsgraph = context.evaluated_depsgraph_get()
        
        # First try scene ray cast
        result, location, normal, index, hit_obj, matrix = context.scene.ray_cast(
            depsgraph, origin, direction
        )
        
        if result and hit_obj == self.obj:
            # Find nearest vertex to hit location
            mesh = self.obj.data
            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()
            
            min_dist = float('inf')
            closest_vert_idx = None
            
            for vert in bm.verts:
                vert_world = self.obj.matrix_world @ vert.co
                dist = (vert_world - location).length
                if dist < min_dist:
                    min_dist = dist
                    closest_vert_idx = vert.index
            
            return closest_vert_idx
        
        # Fallback: Find closest vertex along ray direction
        mesh = self.obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        
        min_dist = float('inf')
        closest_vert_idx = None
        
        for vert in bm.verts:
            vert_world = self.obj.matrix_world @ vert.co
            
            # Calculate distance from ray
            to_vert = vert_world - origin
            proj_length = to_vert.dot(direction.normalized())
            
            if proj_length > 0:  # Vertex is in front of camera
                proj_point = origin + direction.normalized() * proj_length
                dist_to_ray = (vert_world - proj_point).length
                
                # Weight by distance along ray (prefer closer vertices)
                weighted_dist = dist_to_ray + proj_length * 0.01
                
                if weighted_dist < min_dist:
                    min_dist = weighted_dist
                    closest_vert_idx = vert.index
        
        return closest_vert_idx
    
    def _intelligent_select(self, context, start_vertex_idx, part_type):
        """Call appropriate spatial selection function based on part type"""
        mesh = self.obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        selected_verts = set()
        
        try:
            if part_type == 'head':
                selected_verts = intelligent_select_head(start_vertex_idx, self.obj, bm)
            elif part_type.startswith('leg_') or part_type in ('leg_l', 'leg_r'):
                # Extract side from part_type
                leg_side = 'left' if part_type.endswith('_l') else 'right'
                leg_position = 'front' if 'front' in part_type else 'back'
                selected_verts = intelligent_select_leg(start_vertex_idx, self.obj, bm, leg_side, leg_position)
            elif part_type.startswith('arm_'):
                # Arms are similar to legs
                arm_side = 'left' if part_type.endswith('_l') else 'right'
                selected_verts = intelligent_select_leg(start_vertex_idx, self.obj, bm, arm_side, 'front')
            elif part_type == 'tail':
                selected_verts = intelligent_select_tail(start_vertex_idx, self.obj, bm)
            elif part_type.startswith('wing_'):
                wing_side = 'left' if part_type.endswith('_l') else 'right'
                selected_verts = intelligent_select_wing(start_vertex_idx, self.obj, bm, wing_side)
            elif part_type == 'body':
                # For body, get all assigned parts and select remaining
                assigned_parts = self._get_assigned_parts()
                selected_verts = intelligent_select_body(self.obj, bm, assigned_parts)
            else:
                # Fallback: use generic BFS expansion
                selected_verts = generic_bfs_expand(start_vertex_idx, self.obj, bm)
        except Exception as e:
            print(f"Error in intelligent selection: {e}")
            # Fallback to generic expansion
            selected_verts = generic_bfs_expand(start_vertex_idx, self.obj, bm)
        
        return selected_verts
    
    def _get_assigned_parts(self):
        """Get dict of already assigned parts (vertex groups with vertices)"""
        assigned = {}
        mesh = self.obj.data
        
        for vg in self.obj.vertex_groups:
            if vg.name == 'body':
                continue
            
            verts = set()
            for vert in mesh.vertices:
                for group in vert.groups:
                    if group.group == vg.index and group.weight > 0.5:
                        verts.add(vert.index)
                        break
            
            if verts:
                assigned[vg.name] = verts
        
        return assigned
    
    def _update_selection(self, context, vertex_indices):
        """Update Edit mode selection with auto-selected vertices"""
        # Ensure Edit mode
        if context.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        # Deselect all first
        bpy.ops.mesh.select_all(action='DESELECT')
        
        # Select the auto-selected vertices
        mesh = self.obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        
        for vert_idx in vertex_indices:
            if vert_idx < len(bm.verts):
                bm.verts[vert_idx].select = True
        
        # Update edit mesh
        bmesh.update_edit_mesh(mesh)
        
        # Refresh viewport
        context.view_layer.update()


class PET_OT_save_part_selection(Operator):
    """Save current selection to vertex group for the current part"""
    bl_idname = "pet.save_part_selection"
    bl_label = "Save Part Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        state = context.scene.pet_manual_part_selection_state
        if not state.is_active:
            self.report({'ERROR'}, "Manual part selection is not active")
            return {'CANCELLED'}
        
        current_part = state.current_part
        
        # Get selected vertices
        if context.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        
        selected_verts = [v.index for v in bm.verts if v.select]
        
        if not selected_verts:
            self.report({'WARNING'}, "No vertices selected. Select vertices before saving.")
            return {'CANCELLED'}
        
        # Switch to Object mode to modify vertex groups
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Get or create vertex group
        if current_part in obj.vertex_groups:
            vg = obj.vertex_groups[current_part]
        else:
            vg = obj.vertex_groups.new(name=current_part)
        
        # Remove these vertices from other vertex groups (prevent overlaps)
        for other_vg in obj.vertex_groups:
            if other_vg.name != current_part:
                try:
                    other_vg.remove(selected_verts)
                except:
                    pass  # Vertex might not be in this group
        
        # Assign vertices to current part
        vg.add(selected_verts, 1.0, 'REPLACE')
        
        # Update completed parts list
        completed = obj.get("pet_manual_completed_parts", [])
        if current_part not in completed:
            completed = list(completed)  # Convert from IDPropertyArray
            completed.append(current_part)
            obj["pet_manual_completed_parts"] = completed
        
        # Move to next part
        part_list = obj.get("pet_manual_part_list", [])
        current_idx = part_list.index(current_part) if current_part in part_list else 0
        
        # Find next uncompleted part
        next_part = None
        for i in range(current_idx + 1, len(part_list)):
            if part_list[i] not in completed:
                next_part = part_list[i]
                break
        
        # If no next part found, check from beginning
        if next_part is None:
            for i in range(0, current_idx):
                if part_list[i] not in completed:
                    next_part = part_list[i]
                    break
        
        if next_part:
            state.current_part = next_part
            state.current_part_index = part_list.index(next_part)
        
        # Update state
        state.current_selection_vertex_count = 0
        
        # Switch back to Edit mode
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        
        self.report({'INFO'}, f"Saved {len(selected_verts)} vertices to '{get_part_display_name(current_part)}'. Next: {get_part_display_name(next_part) if next_part else 'All parts complete!'}")
        return {'FINISHED'}


class PET_OT_edit_saved_part(Operator):
    """Load a previously saved part for re-editing"""
    bl_idname = "pet.edit_saved_part"
    bl_label = "Edit Saved Part"
    bl_options = {'REGISTER', 'UNDO'}
    
    part_name: StringProperty(
        name="Part Name",
        description="Name of the part to edit"
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        state = context.scene.pet_manual_part_selection_state
        if not state.is_active:
            self.report({'ERROR'}, "Manual part selection is not active")
            return {'CANCELLED'}
        
        if self.part_name not in obj.vertex_groups:
            self.report({'ERROR'}, f"Vertex group '{self.part_name}' not found")
            return {'CANCELLED'}
        
        # Set current part
        state.current_part = self.part_name
        part_list = obj.get("pet_manual_part_list", [])
        if self.part_name in part_list:
            state.current_part_index = part_list.index(self.part_name)
        
        # Switch to Edit mode
        if context.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        # Deselect all
        bpy.ops.mesh.select_all(action='DESELECT')
        
        # Select vertices in this vertex group
        bpy.ops.object.mode_set(mode='OBJECT')
        
        vg = obj.vertex_groups[self.part_name]
        vg_index = vg.index
        
        for vert in obj.data.vertices:
            for group in vert.groups:
                if group.group == vg_index and group.weight > 0.5:
                    vert.select = True
                    break
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Update selection count
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        selected_count = sum(1 for v in bm.verts if v.select)
        state.current_selection_vertex_count = selected_count
        
        self.report({'INFO'}, f"Editing '{get_part_display_name(self.part_name)}' - {selected_count} vertices selected")
        return {'FINISHED'}


class PET_OT_preview_current_selection(Operator):
    """Preview current selection before saving"""
    bl_idname = "pet.preview_current_selection"
    bl_label = "Preview Current Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Ensure Edit mode
        if context.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        # Count selected vertices
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        
        selected_count = sum(1 for v in bm.verts if v.select)
        
        # Update state
        state = context.scene.pet_manual_part_selection_state
        state.current_selection_vertex_count = selected_count
        
        if selected_count > 0:
            self.report({'INFO'}, f"Current selection: {selected_count} vertices")
        else:
            self.report({'WARNING'}, "No vertices selected")
        
        return {'FINISHED'}


class PET_OT_preview_all_parts(Operator):
    """Preview all saved parts in Weight Paint mode"""
    bl_idname = "pet.preview_all_parts"
    bl_label = "Preview All Parts"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Switch to Weight Paint mode
        if context.mode != 'WEIGHT_PAINT':
            bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        
        # Select first vertex group to visualize
        if obj.vertex_groups:
            obj.vertex_groups.active_index = 0
        
        self.report({'INFO'}, "Previewing all parts in Weight Paint mode. Use Properties panel to switch between parts.")
        return {'FINISHED'}


class PET_OT_add_custom_part(Operator):
    """Add a custom part to the part list"""
    bl_idname = "pet.add_custom_part"
    bl_label = "Add Custom Part"
    bl_options = {'REGISTER', 'UNDO'}
    
    part_name: StringProperty(
        name="Part Name",
        description="Name for the custom part",
        default="custom_part"
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        state = context.scene.pet_manual_part_selection_state
        if not state.is_active:
            self.report({'ERROR'}, "Manual part selection is not active")
            return {'CANCELLED'}
        
        # Sanitize part name
        part_name = self.part_name.lower().replace(' ', '_')
        
        # Add to part list
        part_list = list(obj.get("pet_manual_part_list", []))
        
        if part_name in part_list:
            self.report({'WARNING'}, f"Part '{part_name}' already exists")
            return {'CANCELLED'}
        
        # Insert before 'body' (body should always be last)
        if 'body' in part_list:
            body_idx = part_list.index('body')
            part_list.insert(body_idx, part_name)
        else:
            part_list.append(part_name)
        
        obj["pet_manual_part_list"] = part_list
        
        # Create vertex group
        if part_name not in obj.vertex_groups:
            obj.vertex_groups.new(name=part_name)
        
        # Update state
        state.total_parts = len(part_list)
        
        self.report({'INFO'}, f"Added custom part: {part_name}")
        return {'FINISHED'}


class PET_OT_assign_body_remaining(Operator):
    """Assign all remaining unassigned vertices to BODY"""
    bl_idname = "pet.assign_body_remaining"
    bl_label = "Assign Remaining to Body"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Switch to Object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        mesh = obj.data
        
        # Find all assigned vertices
        assigned_verts = set()
        for vg in obj.vertex_groups:
            if vg.name == 'body':
                continue
            
            vg_index = vg.index
            for vert in mesh.vertices:
                for group in vert.groups:
                    if group.group == vg_index and group.weight > 0.5:
                        assigned_verts.add(vert.index)
                        break
        
        # Find unassigned vertices
        all_verts = set(range(len(mesh.vertices)))
        unassigned_verts = list(all_verts - assigned_verts)
        
        if not unassigned_verts:
            self.report({'INFO'}, "All vertices are already assigned")
            return {'FINISHED'}
        
        # Get or create body vertex group
        if 'body' in obj.vertex_groups:
            body_vg = obj.vertex_groups['body']
        else:
            body_vg = obj.vertex_groups.new(name='body')
        
        # Assign unassigned vertices to body
        body_vg.add(unassigned_verts, 1.0, 'REPLACE')
        
        # Update completed parts
        completed = list(obj.get("pet_manual_completed_parts", []))
        if 'body' not in completed:
            completed.append('body')
            obj["pet_manual_completed_parts"] = completed
        
        self.report({'INFO'}, f"Assigned {len(unassigned_verts)} remaining vertices to BODY")
        return {'FINISHED'}


class PET_OT_finish_part_selection(Operator):
    """Finish manual part selection and show completion summary"""
    bl_idname = "pet.finish_part_selection"
    bl_label = "Finish Part Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        state = context.scene.pet_manual_part_selection_state
        if not state.is_active:
            self.report({'ERROR'}, "Manual part selection is not active")
            return {'CANCELLED'}
        
        # Auto-assign remaining to body
        bpy.ops.pet.assign_body_remaining()
        
        # Switch to Object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Calculate summary
        mesh = obj.data
        total_vertices = len(mesh.vertices)
        
        part_summary = []
        total_assigned = 0
        
        for vg in obj.vertex_groups:
            vg_index = vg.index
            vert_count = 0
            for vert in mesh.vertices:
                for group in vert.groups:
                    if group.group == vg_index and group.weight > 0.5:
                        vert_count += 1
                        break
            
            if vert_count > 0:
                part_summary.append(f"{vg.name}: {vert_count:,}")
                total_assigned += vert_count
        
        # Store metrics on object
        obj["pet_segmentation_parts"] = len(obj.vertex_groups)
        obj["pet_segmentation_vertices"] = total_assigned
        obj["pet_segmentation_time"] = 0.0
        obj["pet_segmentation_timestamp"] = time.time()
        
        # Deactivate manual part selection
        state.is_active = False
        state.current_part = ""
        state.current_part_index = 0
        state.current_selection_vertex_count = 0
        
        # Clean up object properties
        if "pet_manual_part_list" in obj:
            del obj["pet_manual_part_list"]
        if "pet_manual_completed_parts" in obj:
            del obj["pet_manual_completed_parts"]
        if "pet_manual_pet_type" in obj:
            del obj["pet_manual_pet_type"]
        
        # Switch to Weight Paint mode for preview
        try:
            bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        except:
            pass
        
        summary_text = f"Manual segmentation complete! {len(obj.vertex_groups)} parts, {total_assigned:,} vertices assigned."
        self.report({'INFO'}, summary_text)
        
        return {'FINISHED'}


class PET_OT_cancel_part_selection(Operator):
    """Cancel manual part selection mode"""
    bl_idname = "pet.cancel_part_selection"
    bl_label = "Cancel Part Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        state = context.scene.pet_manual_part_selection_state
        
        # Deactivate manual part selection
        state.is_active = False
        state.current_part = ""
        state.current_part_index = 0
        state.current_selection_vertex_count = 0
        
        # Clean up object properties
        if obj:
            if "pet_manual_part_list" in obj:
                del obj["pet_manual_part_list"]
            if "pet_manual_completed_parts" in obj:
                del obj["pet_manual_completed_parts"]
            if "pet_manual_pet_type" in obj:
                del obj["pet_manual_pet_type"]
        
        # Switch to Object mode
        if context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except:
                pass
        
        self.report({'INFO'}, "Manual part selection cancelled")
        return {'FINISHED'}


# Operator classes to register
classes = [
    PET_OT_start_manual_part_selection,
    PET_OT_select_part_to_assign,
    PET_OT_click_to_assign_part,
    PET_OT_save_part_selection,
    PET_OT_edit_saved_part,
    PET_OT_preview_current_selection,
    PET_OT_preview_all_parts,
    PET_OT_add_custom_part,
    PET_OT_assign_body_remaining,
    PET_OT_finish_part_selection,
    PET_OT_cancel_part_selection,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
