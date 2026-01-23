import bpy
from bpy.types import Operator
from bpy.props import StringProperty, FloatProperty, IntProperty, BoolProperty, EnumProperty
import bmesh
import time

from ..utils.spatial_selection import fill_gaps_aggressive


MAX_VERTS_DIRECT = 100000


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


CHUNK_SIZE = 50000
TIMEOUT_SECONDS = 30


def process_in_chunks(vertices, chunk_size, process_func, context=None, timeout=TIMEOUT_SECONDS):
    """Process vertices in chunks with timeout handling and progress updates"""
    start_time = time.time()
    total = len(vertices)
    processed = 0
    results = []
    
    for i in range(0, total, chunk_size):
        if time.time() - start_time > timeout:
            return results, processed, True
        
        chunk = vertices[i:i + chunk_size]
        chunk_result = process_func(chunk)
        if chunk_result:
            results.extend(chunk_result)
        processed += len(chunk)
        
        if context and hasattr(context, 'window_manager'):
            context.window_manager.progress_update(processed / total * 100)
    
    return results, processed, False


class PET_OT_assign_selection_to_segment(Operator):
    """Assign current vertex/face selection to a named segment"""
    bl_idname = "pet.assign_selection_to_segment"
    bl_label = "Assign to Segment"
    bl_options = {'REGISTER', 'UNDO'}
    
    segment_name: StringProperty(
        name="Segment Name",
        description="Name for this segment (e.g., Head, Leg_Front_L)",
        default="Head"
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        start_time = time.time()
        
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode with vertices selected")
            return {'CANCELLED'}
        
        bm = bmesh.from_edit_mesh(obj.data)
        
        if len(bm.verts) > MAX_VERTS_DIRECT:
            context.window_manager.progress_begin(0, 100)
        
        selected_verts = [v for v in bm.verts if v.select]
        
        if not selected_verts:
            if len(bm.verts) > MAX_VERTS_DIRECT:
                context.window_manager.progress_end()
            self.report({'ERROR'}, "No vertices selected")
            return {'CANCELLED'}
        
        # Extract vertex data BEFORE mode switch (bmesh becomes invalid after mode switch)
        vert_count = len(bm.verts)
        vert_indices = [v.index for v in selected_verts]
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        group_name = f"Segment_{self.segment_name}"
        if group_name in obj.vertex_groups:
            vg = obj.vertex_groups[group_name]
        else:
            vg = obj.vertex_groups.new(name=group_name)
        
        if len(vert_indices) > CHUNK_SIZE:
            for i in range(0, len(vert_indices), CHUNK_SIZE):
                if time.time() - start_time > TIMEOUT_SECONDS:
                    self.report({'WARNING'}, f"Timeout after {i:,} vertices. Partial assignment completed.")
                    break
                chunk = vert_indices[i:i + CHUNK_SIZE]
                vg.add(chunk, 1.0, 'REPLACE')
                if vert_count > MAX_VERTS_DIRECT:
                    context.window_manager.progress_update((i / len(vert_indices)) * 100)
        else:
            vg.add(vert_indices, 1.0, 'REPLACE')
        
        if vert_count > MAX_VERTS_DIRECT:
            context.window_manager.progress_end()
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        elapsed = time.time() - start_time
        self.report({'INFO'}, f"Assigned {len(vert_indices):,} vertices to '{self.segment_name}' ({elapsed:.1f}s)")
        return {'FINISHED'}


class PET_OT_select_segment(Operator):
    """Select vertices belonging to a segment"""
    bl_idname = "pet.select_segment"
    bl_label = "Select Segment"
    bl_options = {'REGISTER', 'UNDO'}
    
    segment_name: StringProperty(
        name="Segment",
        description="Segment to select"
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        group_name = f"Segment_{self.segment_name}"
        if group_name not in obj.vertex_groups:
            self.report({'ERROR'}, f"Segment '{self.segment_name}' not found")
            return {'CANCELLED'}
        
        was_edit = obj.mode == 'EDIT'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        
        vg_index = obj.vertex_groups[group_name].index
        
        for v in obj.data.vertices:
            v.select = False
            for g in v.groups:
                if g.group == vg_index and g.weight > 0.5:
                    v.select = True
                    break
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        return {'FINISHED'}


class PET_OT_grow_selection(Operator):
    """Grow selection by specified number of rings"""
    bl_idname = "pet.grow_selection"
    bl_label = "Grow Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    iterations: IntProperty(
        name="Rings",
        description="Number of edge rings to grow",
        default=1,
        min=1,
        max=50
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode on a mesh")
            return {'CANCELLED'}
        
        for _ in range(self.iterations):
            bpy.ops.mesh.select_more()

        # If manual part selection is active, keep its selection count in sync
        state = getattr(context.scene, "pet_manual_part_selection_state", None)
        if state is not None and getattr(state, "is_active", False):
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            state.current_selection_vertex_count = sum(1 for v in bm.verts if v.select)

        return {'FINISHED'}


class PET_OT_grow_selection_boundary_aware(Operator):
    """
    Grow selection by one ring, respecting vertex group assignments and boundary edges.
    
    This is a less aggressive alternative to "Grow +" that:
    - Only grows one ring (one edge hop)
    - Excludes vertices already assigned to other vertex groups
    - Respects boundary edges if pet_separation_boundary_edges data exists
    - Prevents jumping from body to feet, head to body, etc.
    """
    bl_idname = "pet.grow_selection_boundary_aware"
    bl_label = "Grow Selection (Boundary Aware)"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode on a mesh")
            return {'CANCELLED'}
        
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        
        # Get current selection
        base_selection = {v.index for v in bm.verts if v.select}
        if not base_selection:
            self.report({'WARNING'}, "No vertices selected")
            bmesh.update_edit_mesh(mesh)
            return {'CANCELLED'}
        
        # Build exclusion set
        excluded = set()
        boundary_edge_indices = set()
        
        # Get current part from manual part selection state
        state = getattr(context.scene, "pet_manual_part_selection_state", None)
        current_part = getattr(state, "current_part", "") if state and getattr(state, "is_active", False) else ""
        
        # Vertex group exclusion (using mesh.vertices, NOT bm.verts)
        if current_part and obj.vertex_groups:
            for vg in obj.vertex_groups:
                if vg.name == current_part:
                    continue
                vg_index = vg.index
                for v in mesh.vertices:
                    # Never exclude vertices the user has explicitly selected
                    if v.index in base_selection:
                        continue
                    for g in v.groups:
                        if g.group == vg_index and g.weight > 0.5:
                            excluded.add(v.index)
                            break
        
        # Boundary edge identification (if pet_separation_boundary_edges exists)
        stored_boundaries = obj.get("pet_separation_boundary_edges", None)
        if stored_boundaries and len(stored_boundaries) > 0:
            # Build spatial index from stored boundaries
            spatial_index = build_spatial_index(stored_boundaries, tolerance=0.001)
            
            if spatial_index:
                # Find edges that match stored boundary coordinates
                for edge in bm.edges:
                    v1_co = edge.verts[0].co
                    v2_co = edge.verts[1].co
                    
                    # Check if BOTH vertices are in the stored boundary data
                    v1_match = coord_in_spatial_index(v1_co, spatial_index, tolerance=0.001)
                    v2_match = coord_in_spatial_index(v2_co, spatial_index, tolerance=0.001)
                    
                    if v1_match and v2_match:
                        boundary_edge_indices.add(edge.index)
                        # Add both vertices to excluded to prevent growing across boundary
                        excluded.add(edge.verts[0].index)
                        excluded.add(edge.verts[1].index)
        
        # Grow selection (single ring)
        new_selection = set()
        for vert_idx in base_selection:
            vert = bm.verts[vert_idx]
            for edge in vert.link_edges:
                # Skip if this is a boundary edge
                if edge.index in boundary_edge_indices:
                    continue
                other_vert = edge.other_vert(vert)
                # Only add if not excluded
                if other_vert.index not in excluded:
                    new_selection.add(other_vert.index)
        
        # Final selection (union to preserve original selection)
        final_selection = base_selection.union(new_selection)
        
        # Apply selection
        for v in bm.verts:
            v.select = v.index in final_selection
        
        bmesh.update_edit_mesh(mesh)
        
        # If manual part selection is active, keep its selection count in sync
        if state is not None and getattr(state, "is_active", False):
            state.current_selection_vertex_count = len(final_selection)
        
        added = len(final_selection) - len(base_selection)
        if added > 0:
            self.report({'INFO'}, f"Grew selection by {added:,} vertices (total {len(final_selection):,})")
        else:
            self.report({'INFO'}, "No additional vertices added (blocked by boundaries or vertex groups)")
        
        return {'FINISHED'}


class PET_OT_shrink_selection(Operator):
    """Shrink selection by specified number of rings"""
    bl_idname = "pet.shrink_selection"
    bl_label = "Shrink Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    iterations: IntProperty(
        name="Rings",
        description="Number of edge rings to shrink",
        default=1,
        min=1,
        max=50
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode on a mesh")
            return {'CANCELLED'}
        
        for _ in range(self.iterations):
            bpy.ops.mesh.select_less()

        # If manual part selection is active, keep its selection count in sync
        state = getattr(context.scene, "pet_manual_part_selection_state", None)
        if state is not None and getattr(state, "is_active", False):
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            state.current_selection_vertex_count = sum(1 for v in bm.verts if v.select)

        return {'FINISHED'}


class PET_OT_smooth_selection_boundary(Operator):
    """Smooth the boundary of current selection for cleaner cuts"""
    bl_idname = "pet.smooth_selection_boundary"
    bl_label = "Smooth Boundary"
    bl_options = {'REGISTER', 'UNDO'}
    
    iterations: IntProperty(
        name="Iterations",
        description="Smoothing iterations",
        default=2,
        min=1,
        max=10
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode on a mesh")
            return {'CANCELLED'}
        
        for _ in range(self.iterations):
            bpy.ops.mesh.select_less()
            bpy.ops.mesh.select_more()

        # If manual part selection is active, keep its selection count in sync
        state = getattr(context.scene, "pet_manual_part_selection_state", None)
        if state is not None and getattr(state, "is_active", False):
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            state.current_selection_vertex_count = sum(1 for v in bm.verts if v.select)

        self.report({'INFO'}, "Smoothed selection boundary")
        return {'FINISHED'}


class PET_OT_fill_gaps_selection(Operator):
    """Fill fully-surrounded cracks and small islands inside the current selection"""
    bl_idname = "pet.fill_gaps_selection"
    bl_label = "Fill Gaps"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode on a mesh")
            return {'CANCELLED'}

        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()

        base_selection = {v.index for v in bm.verts if v.select}
        if not base_selection:
            self.report({'WARNING'}, "No vertices selected. Select a part, then use Fill Gaps.")
            return {'CANCELLED'}

        start_time = time.time()
        total_verts = len(bm.verts)

        # Build an exclusion mask so we don't eat vertices that already belong
        # to other parts when manual part selection is active.
        excluded = set()
        state = getattr(context.scene, "pet_manual_part_selection_state", None)
        current_part = getattr(state, "current_part", "") if state and getattr(state, "is_active", False) else ""

        if current_part and obj.vertex_groups:
            vg_by_name = {vg.name: vg for vg in obj.vertex_groups}
            for vg_name, vg in vg_by_name.items():
                if vg_name == current_part:
                    continue
                vg_index = vg.index
                for v in mesh.vertices:
                    # Never exclude vertices the user has explicitly selected
                    if v.index in base_selection:
                        continue
                    for g in v.groups:
                        if g.group == vg_index and g.weight > 0.5:
                            excluded.add(v.index)
                            break

        expanded = fill_gaps_aggressive(
            bm,
            base_selection,
            max_gap_size=512,
            neighbor_selected_ratio=0.75,
            max_total_vertices=None,
            start_time=start_time,
            timeout_seconds=10.0,
            excluded_indices=excluded,
        )

        # Expand-only semantics: never shrink the user's selection.
        final_selection = base_selection.union(expanded or set())

        for v in bm.verts:
            v.select = v.index in final_selection
        bmesh.update_edit_mesh(mesh)

        # Keep Manual Part Selection's selection count in sync if it's active.
        if state is not None and getattr(state, "is_active", False):
            state.current_selection_vertex_count = len(final_selection)

        # Calculate added vertices - ensure all variables are defined
        base_count = len(base_selection) if base_selection else 0
        final_count = len(final_selection) if final_selection else 0
        added = final_count - base_count
        
        if added > 0:
            self.report({'INFO'}, f"Fill Gaps added {added:,} vertices (total {final_count:,}).")
        else:
            self.report({'INFO'}, "Fill Gaps did not find additional enclosed vertices. Your selection is unchanged.")

        return {'FINISHED'}


class PET_OT_select_linked_flat(Operator):
    """Select linked flat faces from current selection - good for organic surfaces"""
    bl_idname = "pet.select_linked_flat"
    bl_label = "Select Linked Flat"
    bl_options = {'REGISTER', 'UNDO'}
    
    angle_threshold: FloatProperty(
        name="Angle Threshold",
        description="Maximum angle between faces to consider linked",
        default=15.0,
        min=0.0,
        max=180.0,
        subtype='ANGLE'
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode on a mesh")
            return {'CANCELLED'}
        
        import math
        bpy.ops.mesh.select_linked(delimit={'NORMAL'})
        
        return {'FINISHED'}


class PET_OT_invert_and_assign_body(Operator):
    """Invert selection and assign remaining to Body segment"""
    bl_idname = "pet.invert_assign_body"
    bl_label = "Assign Remaining as Body"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        start_time = time.time()
        
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        total_verts = len(obj.data.vertices)
        use_progress = total_verts > MAX_VERTS_DIRECT
        
        if use_progress:
            context.window_manager.progress_begin(0, 100)
            self.report({'INFO'}, f"Processing {total_verts:,} vertices...")
        
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
        
        segment_groups = [vg for vg in obj.vertex_groups if vg.name.startswith("Segment_")]
        
        assigned_verts = set()
        processed = 0
        
        for vg in segment_groups:
            if vg.name == "Segment_Body":
                continue
            vg_index = vg.index
            
            for i, v in enumerate(obj.data.vertices):
                if time.time() - start_time > TIMEOUT_SECONDS:
                    if use_progress:
                        context.window_manager.progress_end()
                    self.report({'WARNING'}, f"Timeout after processing {processed:,} vertices. Try on decimated mesh.")
                    bpy.ops.object.mode_set(mode='EDIT')
                    return {'CANCELLED'}
                
                for g in v.groups:
                    if g.group == vg_index and g.weight > 0.5:
                        assigned_verts.add(v.index)
                
                if use_progress and i % 10000 == 0:
                    context.window_manager.progress_update((i / total_verts) * 50)
            
            processed = len(assigned_verts)
        
        if use_progress:
            context.window_manager.progress_update(60)
        
        body_verts = [v.index for v in obj.data.vertices if v.index not in assigned_verts]
        
        if use_progress:
            context.window_manager.progress_update(70)
        
        if "Segment_Body" in obj.vertex_groups:
            body_group = obj.vertex_groups["Segment_Body"]
        else:
            body_group = obj.vertex_groups.new(name="Segment_Body")
        
        if len(body_verts) > CHUNK_SIZE:
            for i in range(0, len(body_verts), CHUNK_SIZE):
                if time.time() - start_time > TIMEOUT_SECONDS:
                    self.report({'WARNING'}, f"Timeout during body assignment. Partial completion.")
                    break
                chunk = body_verts[i:i + CHUNK_SIZE]
                body_group.add(chunk, 1.0, 'REPLACE')
                if use_progress:
                    context.window_manager.progress_update(70 + (i / len(body_verts)) * 30)
        else:
            body_group.add(body_verts, 1.0, 'REPLACE')
        
        if use_progress:
            context.window_manager.progress_end()
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        elapsed = time.time() - start_time
        self.report({'INFO'}, f"Assigned {len(body_verts):,} vertices to Body ({len(assigned_verts):,} in other segments) - {elapsed:.1f}s")
        return {'FINISHED'}


class PET_OT_quick_decimate(Operator):
    """Quickly reduce mesh complexity for easier selection"""
    bl_idname = "pet.quick_decimate"
    bl_label = "Quick Decimate"
    bl_options = {'REGISTER', 'UNDO'}
    
    ratio: FloatProperty(
        name="Ratio",
        description="Target polygon ratio (0.1 = 10% of original)",
        default=0.1,
        min=0.01,
        max=1.0
    )
    
    keep_original: BoolProperty(
        name="Keep Original",
        description="Create decimated copy, keep original mesh",
        default=True
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        original_faces = len(obj.data.polygons)
        
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        if self.keep_original:
            bpy.ops.object.duplicate()
            obj = context.active_object
            obj.name = obj.name.replace(".001", "_lowpoly")
        
        mod = obj.modifiers.new(name="QuickDecimate", type='DECIMATE')
        mod.ratio = self.ratio
        bpy.ops.object.modifier_apply(modifier=mod.name)
        
        new_faces = len(obj.data.polygons)
        reduction = (1 - new_faces / original_faces) * 100
        
        self.report({'INFO'}, f"Reduced from {original_faces:,} to {new_faces:,} faces ({reduction:.1f}% reduction)")
        return {'FINISHED'}


class PET_OT_preview_segments(Operator):
    """Preview all assigned segments with colors"""
    bl_idname = "pet.preview_segments"
    bl_label = "Preview Segments"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        start_time = time.time()
        
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        total_verts = len(obj.data.vertices)
        total_loops = len(obj.data.loops)
        use_progress = total_verts > MAX_VERTS_DIRECT
        
        if use_progress:
            context.window_manager.progress_begin(0, 100)
            self.report({'INFO'}, f"Building preview for {total_verts:,} vertices...")
        
        if not obj.data.vertex_colors:
            obj.data.vertex_colors.new(name="SegmentPreview")
        
        color_layer = obj.data.vertex_colors.active
        
        segment_colors = {
            'Head': (1.0, 0.3, 0.3, 1.0),
            'Body': (0.3, 1.0, 0.3, 1.0),
            'Leg_Front_L': (0.3, 0.3, 1.0, 1.0),
            'Leg_Front_R': (0.3, 0.6, 1.0, 1.0),
            'Leg_Back_L': (1.0, 0.6, 0.3, 1.0),
            'Leg_Back_R': (1.0, 0.8, 0.3, 1.0),
            'Tail': (0.8, 0.3, 0.8, 1.0),
            'Wing_L': (0.3, 0.8, 0.8, 1.0),
            'Wing_R': (0.5, 0.9, 0.9, 1.0),
        }
        
        vert_segment = {}
        for vg in obj.vertex_groups:
            if vg.name.startswith("Segment_"):
                segment_name = vg.name[8:]
                vg_index = vg.index
                for i, v in enumerate(obj.data.vertices):
                    if use_progress and i % 20000 == 0:
                        if time.time() - start_time > TIMEOUT_SECONDS:
                            context.window_manager.progress_end()
                            self.report({'WARNING'}, "Timeout building segment map. Try on smaller mesh.")
                            return {'CANCELLED'}
                        context.window_manager.progress_update((i / total_verts) * 50)
                    
                    for g in v.groups:
                        if g.group == vg_index and g.weight > 0.5:
                            vert_segment[v.index] = segment_name
        
        if use_progress:
            context.window_manager.progress_update(50)
        
        default_color = (0.5, 0.5, 0.5, 1.0)
        for i, poly in enumerate(obj.data.polygons):
            if use_progress and i % 10000 == 0:
                if time.time() - start_time > TIMEOUT_SECONDS:
                    context.window_manager.progress_end()
                    self.report({'WARNING'}, "Timeout coloring polygons. Partial preview available.")
                    break
                context.window_manager.progress_update(50 + (i / len(obj.data.polygons)) * 50)
            
            for loop_index in poly.loop_indices:
                vert_index = obj.data.loops[loop_index].vertex_index
                segment = vert_segment.get(vert_index, None)
                if segment and segment in segment_colors:
                    color_layer.data[loop_index].color = segment_colors[segment]
                else:
                    color_layer.data[loop_index].color = default_color
        
        if use_progress:
            context.window_manager.progress_end()
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'SOLID'
                        space.shading.color_type = 'VERTEX'
        
        elapsed = time.time() - start_time
        self.report({'INFO'}, f"Previewing {len(vert_segment):,} vertices across segments ({elapsed:.1f}s)")
        return {'FINISHED'}


class PET_OT_clear_segment(Operator):
    """Remove a segment vertex group"""
    bl_idname = "pet.clear_segment"
    bl_label = "Clear Segment"
    bl_options = {'REGISTER', 'UNDO'}
    
    segment_name: StringProperty(name="Segment")
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        
        group_name = f"Segment_{self.segment_name}"
        if group_name in obj.vertex_groups:
            obj.vertex_groups.remove(obj.vertex_groups[group_name])
            self.report({'INFO'}, f"Cleared segment '{self.segment_name}'")
        
        return {'FINISHED'}


class PET_OT_split_by_segments(Operator):
    """Split mesh into separate objects based on assigned segments"""
    bl_idname = "pet.split_by_segments"
    bl_label = "Split by Segments"
    bl_options = {'REGISTER', 'UNDO'}
    
    timeout_per_segment: IntProperty(
        name="Timeout per Segment",
        description="Maximum seconds per segment split (0 = no limit)",
        default=60,
        min=0,
        max=300
    )
    
    def execute(self, context):
        start_time = time.time()
        
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        segment_groups = [vg for vg in obj.vertex_groups if vg.name.startswith("Segment_")]
        
        if not segment_groups:
            self.report({'ERROR'}, "No segments defined. Assign vertices to segments first.")
            return {'CANCELLED'}
        
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        total_verts = len(obj.data.vertices)
        use_progress = total_verts > MAX_VERTS_DIRECT
        
        if use_progress:
            context.window_manager.progress_begin(0, 100)
            self.report({'INFO'}, f"Splitting {total_verts:,} vertex mesh into {len(segment_groups)} segments...")
        
        base_name = obj.name
        created_objects = []
        segment_timeout = self.timeout_per_segment if self.timeout_per_segment > 0 else 300
        
        for seg_idx, vg in enumerate(segment_groups):
            segment_start = time.time()
            segment_name = vg.name[8:]
            
            if use_progress:
                context.window_manager.progress_update((seg_idx / len(segment_groups)) * 100)
            
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.duplicate()
            new_obj = context.active_object
            new_obj.name = f"{base_name}_{segment_name}"
            
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')
            
            vg_index = new_obj.vertex_groups[vg.name].index
            timed_out = False
            
            for i, v in enumerate(new_obj.data.vertices):
                if i % 10000 == 0 and time.time() - segment_start > segment_timeout:
                    self.report({'WARNING'}, f"Timeout splitting '{segment_name}'. Skipping.")
                    timed_out = True
                    break
                
                in_group = False
                for g in v.groups:
                    if g.group == vg_index and g.weight > 0.5:
                        in_group = True
                        break
                v.select = not in_group
            
            if timed_out:
                bpy.data.objects.remove(new_obj, do_unlink=True)
                continue
            
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.delete(type='VERT')
            bpy.ops.object.mode_set(mode='OBJECT')
            
            for old_vg in list(new_obj.vertex_groups):
                new_obj.vertex_groups.remove(old_vg)
            
            created_objects.append(new_obj.name)
        
        if use_progress:
            context.window_manager.progress_end()
        
        bpy.data.objects.remove(obj, do_unlink=True)
        
        elapsed = time.time() - start_time
        self.report({'INFO'}, f"Created {len(created_objects)} segment objects in {elapsed:.1f}s")
        return {'FINISHED'}


classes = [
    PET_OT_assign_selection_to_segment,
    PET_OT_select_segment,
    PET_OT_grow_selection,
    PET_OT_grow_selection_boundary_aware,
    PET_OT_shrink_selection,
    PET_OT_smooth_selection_boundary,
    PET_OT_fill_gaps_selection,
    PET_OT_select_linked_flat,
    PET_OT_invert_and_assign_body,
    PET_OT_quick_decimate,
    PET_OT_preview_segments,
    PET_OT_clear_segment,
    PET_OT_split_by_segments,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
