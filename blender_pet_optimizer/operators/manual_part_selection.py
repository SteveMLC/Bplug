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
    intelligent_select_head_from_seeds,
    intelligent_select_leg,
    intelligent_select_tail,
    intelligent_select_wing,
    intelligent_select_body,
    fill_small_surrounded_gaps,
    generic_bfs_expand,
)
from ..utils import segmentation_templates


# Performance / safety constants (aligned with manual_segment & symmetry operators)
MAX_VERTS_DIRECT = 100000
TIMEOUT_SECONDS = 30


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
        
        # Orientation hint for head selection
        scene = context.scene if hasattr(context, "scene") else None
        settings = getattr(scene, "pet_segmentation_settings", None) if scene else None
        invert_forward_axis = bool(getattr(settings, "invert_forward_axis", False)) if settings else False

        try:
            if part_type == 'head':
                selected_verts = intelligent_select_head(start_vertex_idx, self.obj, bm, invert_forward_axis=invert_forward_axis)
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


class PET_OT_auto_grow_current_selection(Operator):
    """Auto-grow current selection for the active part using intelligent spatial logic"""
    bl_idname = "pet.auto_grow_current_selection"
    bl_label = "Auto-Grow Current Selection"
    bl_options = {'REGISTER', 'UNDO'}

    part_type: StringProperty(
        name="Part Type",
        description="Type of part to expand selection for (head, leg_front_l, etc.)"
    )

    def execute(self, context):
        start_time = time.time()
        obj = context.active_object

        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}

        state = context.scene.pet_manual_part_selection_state
        if not getattr(state, "is_active", False):
            self.report({'ERROR'}, "Manual part selection is not active")
            return {'CANCELLED'}

        # Ensure Edit mode
        if context.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        # Capture current selection as seed set and backup
        seed_indices = {v.index for v in bm.verts if v.select}
        if not seed_indices:
            self.report({'WARNING'}, "No vertices selected. Select vertices for the part, then run auto-grow.")
            return {'CANCELLED'}

        original_selection = set(seed_indices)

        total_verts = len(mesh.vertices)
        use_progress = total_verts > MAX_VERTS_DIRECT

        if use_progress:
            context.window_manager.progress_begin(0, 100)

        try:
            target_part = (self.part_type or state.current_part or "").lower()
            expanded = self._auto_expand_from_seeds(
                obj, bm, seed_indices, target_part, context, start_time
            )

            if not expanded:
                # Nothing better found – keep original selection
                final_selection = original_selection
                improved = False
            else:
                # Expand-only semantics: never shrink the user's selection.
                if len(expanded) <= len(original_selection) or expanded.issubset(original_selection):
                    final_selection = original_selection
                    improved = False
                else:
                    final_selection = original_selection.union(expanded)
                    improved = len(final_selection) > len(original_selection)

            # Apply final selection (either unchanged or expanded)
            self._apply_selection(context, obj, final_selection)
            state.current_selection_vertex_count = len(final_selection)

            elapsed = time.time() - start_time
            part_label = get_part_display_name(target_part or 'part')

            if not improved:
                msg = (
                    f"Auto-grow did not find additional vertices for {part_label}. "
                    "Your current selection has been preserved."
                )
                # Treat timeout as informational if we didn't change anything
                if time.time() - start_time > TIMEOUT_SECONDS:
                    msg += " (stopped early due to timeout)."
                self.report({'INFO'}, msg)
            else:
                added = len(final_selection) - len(original_selection)
                msg = (
                    f"Auto-selected {added:,} additional vertices "
                    f"(total {len(final_selection):,}) for {part_label} ({elapsed:.1f}s)"
                )
                if time.time() - start_time > TIMEOUT_SECONDS:
                    msg += " (stopped early due to timeout)."
                    self.report({'WARNING'}, msg)
                else:
                    self.report({'INFO'}, msg)

            return {'FINISHED'}
        except Exception as e:
            # On error, restore original selection
            print(f"[PET_OT_auto_grow_current_selection] Error: {e}")
            self._apply_selection(context, obj, original_selection)
            state.current_selection_vertex_count = len(original_selection)
            self.report({'ERROR'}, "Auto-grow failed. Original selection has been restored.")
            return {'CANCELLED'}
        finally:
            if use_progress:
                context.window_manager.progress_end()

    def _auto_expand_from_seeds(self, obj, bm, seeds, part_type, context, start_time):
        """Use part-specific intelligent selection from multiple seeds with timeout safeguards."""
        # Limit number of seeds to avoid combinatorial explosion
        seed_list = list(seeds)
        MAX_SEEDS = 10
        seed_list = seed_list[:MAX_SEEDS]

        expanded = set()
        total_verts = len(bm.verts)
        # Generic guardrail to avoid whole-body selections for any part
        MAX_PART_FRACTION = 0.6
        max_part_vertices = max(500, int(total_verts * MAX_PART_FRACTION))

        # Orientation hint for head selection: use segmentation settings if available
        scene = context.scene if hasattr(context, "scene") else None
        settings = getattr(scene, "pet_segmentation_settings", None) if scene else None
        invert_forward_axis = bool(getattr(settings, "invert_forward_axis", False)) if settings else False

        try:
            if part_type == 'head':
                # Use seed-set-aware helper for head to keep growth local.
                expanded = intelligent_select_head_from_seeds(seed_list, obj, bm, invert_forward_axis=invert_forward_axis)
            else:
                for idx, seed in enumerate(seed_list):
                    if time.time() - start_time > TIMEOUT_SECONDS:
                        break

                    try:
                        if part_type.startswith('leg_') or part_type in {'leg_l', 'leg_r'}:
                            leg_side = 'left' if part_type.endswith('_l') else 'right'
                            leg_position = 'front' if 'front' in part_type else 'back'
                            part_verts = intelligent_select_leg(seed, obj, bm, leg_side, leg_position)
                        elif part_type.startswith('arm_'):
                            arm_side = 'left' if part_type.endswith('_l') else 'right'
                            part_verts = intelligent_select_leg(seed, obj, bm, arm_side, 'front')
                        elif part_type == 'tail':
                            part_verts = intelligent_select_tail(seed, obj, bm)
                        elif part_type.startswith('wing_'):
                            wing_side = 'left' if part_type.endswith('_l') else 'right'
                            part_verts = intelligent_select_wing(seed, obj, bm, wing_side)
                        elif part_type == 'body':
                            assigned_parts = self._get_assigned_parts_for_body(obj)
                            part_verts = intelligent_select_body(obj, bm, assigned_parts)
                        else:
                            part_verts = generic_bfs_expand(seed, obj, bm)
                    except Exception as e:
                        print(f"[PET_OT_auto_grow_current_selection] Intelligent selection error for seed {seed}: {e}")
                        part_verts = generic_bfs_expand(seed, obj, bm)

                    if part_verts:
                        expanded.update(part_verts)

                    # Lightweight progress feedback for very large meshes
                    if len(bm.verts) > MAX_VERTS_DIRECT and idx % 2 == 0 and hasattr(context, "window_manager"):
                        progress = min(99, int((idx + 1) / max(1, len(seed_list)) * 100))
                        context.window_manager.progress_update(progress)
        finally:
            # Apply generic guardrail: if a part selection tries to eat most of the mesh,
            # fall back to the original seeds so the user doesn't lose their work.
            if part_type != 'body' and len(expanded) > max_part_vertices:
                # Log a helpful message when we clamp a runaway selection
                fraction = len(expanded) / max(1, total_verts) * 100.0
                print(
                    f"[PET_OT_auto_grow_current_selection] Guardrail triggered for part '{part_type}': "
                    f"{len(expanded)} verts (~{fraction:.1f}% of mesh). "
                    "Falling back to original seed selection."
                )
                expanded = set(seeds)

        # Fallback: if nothing expanded beyond seeds, just return seeds
        if not expanded:
            return set(seeds)

        # After guardrails, conservatively fill tiny, mostly-surrounded gaps.
        # This runs for all parts and only ever ADDS vertices.
        have_time = (time.time() - start_time) < TIMEOUT_SECONDS
        if have_time:
            max_total = max_part_vertices if part_type != 'body' else None
            try:
                expanded = fill_small_surrounded_gaps(
                    bm,
                    expanded,
                    # Slightly higher cap than the head-specific call so
                    # deeper enclosed cracks on any part can be closed,
                    # still bounded by per-part max_total.
                    max_gap_size=96,
                    # Allow up to ~10% of neighbors to be external so that
                    # mostly-enclosed strips can still be filled.
                    neighbor_selected_ratio=0.9,
                    max_total_vertices=max_total,
                    start_time=start_time,
                    timeout_seconds=TIMEOUT_SECONDS,
                )
            except Exception as e:
                print(f"[PET_OT_auto_grow_current_selection] gap-fill error for part '{part_type}': {e}")

        return expanded

    def _get_assigned_parts_for_body(self, obj):
        """Rebuild mapping of already assigned parts for intelligent body selection."""
        assigned = {}
        mesh = obj.data

        for vg in obj.vertex_groups:
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

    def _apply_selection(self, context, obj, vertex_indices):
        """Apply a vertex index set as the active Edit Mode selection."""
        if context.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        mesh = obj.data

        # Deselect all first
        bpy.ops.mesh.select_all(action='DESELECT')

        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()

        for vidx in vertex_indices:
            if 0 <= vidx < len(bm.verts):
                bm.verts[vidx].select = True

        bmesh.update_edit_mesh(mesh)


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

        # If the user is explicitly saving BODY, remember that this BODY
        # selection was defined manually (authoritative) rather than being
        # created by Assign Remaining to Body.
        if current_part == 'body':
            obj["pet_manual_body_explicit"] = True
        
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
        
        # Any call to Assign Remaining to Body defines BODY automatically,
        # so clear any explicit-body marker.
        if "pet_manual_body_explicit" in obj:
            del obj["pet_manual_body_explicit"]
        
        # Switch to Object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        mesh = obj.data
        total_verts = len(mesh.vertices)
        start_time = time.time()
        
        # Build mapping from vertex index -> list of non-body part names
        vert_to_parts = {i: [] for i in range(total_verts)}
        non_body_groups = [vg for vg in obj.vertex_groups if vg.name != 'body']
        
        for vg in non_body_groups:
            vg_index = vg.index
            part_name = vg.name
            for vert in mesh.vertices:
                for group in vert.groups:
                    if group.group == vg_index and group.weight > 0.5:
                        vert_to_parts[vert.index].append(part_name)
                        break
        
        # Vertices with any non-body part are considered already assigned.
        assigned_verts = {idx for idx, parts in vert_to_parts.items() if parts}
        
        # Find unassigned vertices (no non-body part membership)
        unassigned_verts = [i for i in range(total_verts) if i not in assigned_verts]
        
        if not unassigned_verts:
            self.report({'INFO'}, "All vertices are already assigned")
            return {'FINISHED'}
        
        # Build adjacency (vertex index -> neighbor indices) for components
        neighbors = {i: [] for i in range(total_verts)}
        for edge in mesh.edges:
            v1, v2 = edge.vertices
            neighbors[v1].append(v2)
            neighbors[v2].append(v1)
        
        visited = set()
        components = []
        
        for v_idx in unassigned_verts:
            if v_idx in visited:
                continue
            comp = set()
            queue = [v_idx]
            visited.add(v_idx)
            
            while queue:
                if time.time() - start_time > TIMEOUT_SECONDS:
                    self.report({'WARNING'}, "Timeout while analyzing leftover components. Partial BODY assignment applied.")
                    queue.clear()
                    break
                
                current = queue.pop(0)
                comp.add(current)
                for nb in neighbors.get(current, []):
                    if nb in visited or nb not in unassigned_verts:
                        continue
                    visited.add(nb)
                    queue.append(nb)
            
            if comp:
                components.append(comp)
        
        # Prepare vertex groups for reassignment
        vg_by_name = {vg.name: vg for vg in obj.vertex_groups}
        if 'body' in vg_by_name:
            body_vg = vg_by_name['body']
        else:
            body_vg = obj.vertex_groups.new(name='body')
            vg_by_name['body'] = body_vg
        
        body_vertices = set()
        reassigned_counts = {}
        
        SMALL_COMPONENT_MAX = 500  # Heuristic: small islands near limbs/head
        MIN_CONFIDENCE = 0.6       # At least 60% of contacts to a single part
        
        for comp in components:
            if time.time() - start_time > TIMEOUT_SECONDS:
                # On timeout, assign remaining components to BODY to guarantee completion
                body_vertices.update(comp)
                continue
            
            # Measure adjacency to existing non-body parts via edge contacts
            neighbor_counts = {}
            for v_idx in comp:
                for nb in neighbors.get(v_idx, []):
                    if nb in comp:
                        continue
                    for part_name in vert_to_parts.get(nb, []):
                        neighbor_counts[part_name] = neighbor_counts.get(part_name, 0) + 1
            
            if not neighbor_counts:
                # No strong attachment to any part – treat as BODY mass
                body_vertices.update(comp)
                continue
            
            best_part, best_count = max(neighbor_counts.items(), key=lambda kv: kv[1])
            total_contacts = sum(neighbor_counts.values())
            confidence = best_count / max(1, total_contacts)
            
            if len(comp) <= SMALL_COMPONENT_MAX and confidence >= MIN_CONFIDENCE and best_part in vg_by_name:
                # Small island clearly attached to a single part – reassign to that part
                part_vg = vg_by_name[best_part]
                part_vg.add(list(comp), 1.0, 'REPLACE')
                reassigned_counts[best_part] = reassigned_counts.get(best_part, 0) + len(comp)
            else:
                # Large or ambiguous component – assign to BODY
                body_vertices.update(comp)
        
        if body_vertices:
            body_vg.add(list(body_vertices), 1.0, 'REPLACE')
        
        # Update completed parts
        completed = list(obj.get("pet_manual_completed_parts", []))
        if 'body' not in completed:
            completed.append('body')
            obj["pet_manual_completed_parts"] = completed
        
        # Build a helpful summary message
        body_count = len(body_vertices)
        msg_parts = [f"Assigned {body_count} vertices to BODY"]
        if reassigned_counts:
            for part_name, count in reassigned_counts.items():
                msg_parts.append(f"reassigned {count} leftover vertices to {get_part_display_name(part_name)}")
        self.report({'INFO'}, "; ".join(msg_parts))
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
        
        # Auto-assign remaining to body only if BODY has not been explicitly
        # defined by the user via \"Use Current Selection as BODY\".
        body_explicit = bool(obj.get("pet_manual_body_explicit", False))
        if not body_explicit:
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
        if "pet_manual_body_explicit" in obj:
            del obj["pet_manual_body_explicit"]
        
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
            if "pet_manual_body_explicit" in obj:
                del obj["pet_manual_body_explicit"]
        
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
    PET_OT_auto_grow_current_selection,
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
