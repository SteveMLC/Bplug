"""
UI panels for Pet Model Optimizer
N-panel interface for all addon operations
"""

import bpy
from bpy.types import Panel, PropertyGroup
from bpy.props import EnumProperty, BoolProperty, FloatProperty
from ..utils import bmesh_helpers


class PET_SegmentationSettings(PropertyGroup):
    """PropertyGroup for segmentation settings stored on Scene"""
    
    pet_type: EnumProperty(
        name="Pet Type",
        description="Type of pet to segment",
        items=[
            ('quadruped', "Quadruped", "Four-legged animals (dogs, cats, etc.)"),
            ('biped', "Biped", "Two-legged animals"),
            ('flying', "Flying", "Flying animals (birds, etc.)"),
        ],
        default='quadruped'
    )
    
    use_geometry_based: BoolProperty(
        name="Use Geometry-Based Detection",
        description="Use geometry-relative positioning (enhancement mode). Detects body parts by actual mesh shape, not bounding box percentages. Use after preview to refine results.",
        default=False
    )
    
    use_connectivity_refinement: BoolProperty(
        name="Use Connectivity Refinement",
        description="Industry-standard connectivity-based boundary refinement (Recommended for 85-95% accuracy)",
        default=True
    )
    
    auto_detect_protrusions: BoolProperty(
        name="Auto-Detect Protrusions",
        description="Automatically detect legs, wings, and tails using connectivity analysis",
        default=True
    )
    
    sensitivity: FloatProperty(
        name="Boundary Sensitivity",
        description="Sensitivity for boundary detection (0.0 = strict, 1.0 = relaxed)",
        default=0.5,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )
    
    clear_existing: BoolProperty(
        name="Clear Existing Groups",
        description="Clear existing vertex groups before segmenting",
        default=True
    )
    
    auto_split: BoolProperty(
        name="Auto Split",
        description="Automatically split mesh into separate objects after segmentation",
        default=False
    )
    
    use_fast_mode: BoolProperty(
        name="Fast Mode",
        description="Use faster algorithms for large meshes (skips expensive connectivity analysis). Recommended for meshes > 200k vertices.",
        default=False
    )


class PET_ManualAssignmentState(PropertyGroup):
    """PropertyGroup for manual assignment wizard state stored on Scene"""
    
    is_active: BoolProperty(
        name="Manual Assignment Active",
        description="Whether manual assignment wizard is currently active",
        default=False
    )
    
    current_step: IntProperty(
        name="Current Step",
        description="Current step index in the wizard (0-based)",
        default=0,
        min=0
    )
    
    remaining_vertex_count: IntProperty(
        name="Remaining Vertex Count",
        description="Count of unassigned vertices",
        default=0,
        min=0
    )


class PET_PT_main_panel(Panel):
    """Main panel for Pet Model Optimizer"""
    bl_label = "Pet Model Optimizer"
    bl_idname = "PET_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="Workflow: Segment → Optimize → Rig → Export")


class PET_PT_mesh_optimization(Panel):
    """Mesh optimization panel"""
    bl_label = "Mesh Optimization"
    bl_idname = "PET_PT_mesh_optimization"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Object selector
        row = layout.row()
        row.label(text="Object:")
        row.prop(context, "active_object", text="")
        
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return
        
        # Face count info
        face_count = len(obj.data.polygons) if obj.data.polygons else 0
        layout.label(text=f"Faces: {face_count:,}", icon='MESH_DATA')
        
        # Algorithm selection
        op = layout.operator("pet.optimize_mesh", text="Optimize Mesh")
        
        col = layout.column()
        col.prop(op, "algorithm", expand=True)
        
        # Reduction slider
        layout.prop(op, "reduction", slider=True)
        
        # Grid size (only for centroid clustering)
        if op.algorithm in ['AUTO', 'CENTROID']:
            layout.prop(op, "grid_size")


class PET_PT_segmentation(Panel):
    """Segmentation panel"""
    bl_label = "Segmentation"
    bl_idname = "PET_PT_segmentation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return
        
        # ===== Status Indicators Box =====
        status_box = layout.box()
        status_box.label(text="Status Indicators", icon='CHECKMARK')
        status_box.label(text="✓ Fast Preview (<2 seconds)", icon='TIME')
        status_box.label(text="✓ Spatial-Only (Default, Reliable)", icon='CHECKMARK')
        status_box.label(text="✓ Geometry-Based (Enhancement Mode)", icon='SETTINGS')
        status_box.label(text="✓ Iterative Refinement Workflow", icon='INFO')
        layout.separator()
        
        # ===== Data Preservation Box =====
        data_info = bmesh_helpers.get_mesh_data_info(obj)
        if data_info['uv_layers'] > 0 or data_info['color_attributes'] > 0 or data_info['materials'] > 0:
            data_box = layout.box()
            data_box.label(text="Data Preservation", icon='INFO')
            row = data_box.row()
            if data_info['uv_layers'] > 0:
                row.label(text=f"✓ UV Layers: {data_info['uv_layers']}", icon='UV')
            if data_info['color_attributes'] > 0:
                row.label(text=f"✓ Colors: {data_info['color_attributes']}", icon='GROUP_VCOL')
            if data_info['materials'] > 0:
                row.label(text=f"✓ Mats: {data_info['materials']}", icon='MATERIAL')
            data_box.label(text="All data will be preserved during split")
            layout.separator()
        
        # ===== Pet Type Selector =====
        # Use Scene properties for editable settings
        settings = context.scene.pet_segmentation_settings
        
        # Show properties - these are now editable!
        layout.label(text="Pet Type:")
        row = layout.row()
        row.prop(settings, "pet_type", expand=True)
        layout.separator()
        
        # ===== Manual Assignment Wizard =====
        wizard_state = context.scene.pet_manual_assignment_state
        
        if wizard_state.is_active:
            # Wizard is active - show wizard UI
            wizard_box = layout.box()
            wizard_box.label(text="Manual Assignment Wizard", icon='ARMATURE_DATA')
            
            # Get current part info
            part_list = obj.get("pet_manual_part_list", [])
            total_steps = len(part_list) if part_list else 0
            current_step_idx = wizard_state.current_step
            
            # Validate current step
            if not part_list or current_step_idx >= len(part_list):
                wizard_box.label(text="Error: Invalid wizard state", icon='ERROR')
                cancel_op = wizard_box.operator("pet.cancel_manual_assignment", text="Cancel", icon='X')
                layout.separator()
                return
            
            current_part = part_list[current_step_idx]
            is_body_step = (current_part == 'body')
            
            # Progress indicator
            progress_row = wizard_box.row()
            progress_row.label(text=f"Step {current_step_idx + 1} of {total_steps}: {current_part.capitalize()}")
            
            # Visual progress dots
            progress_dots = wizard_box.row()
            for i in range(total_steps):
                if i <= current_step_idx:
                    progress_dots.label(text="●", icon='BLANK1')
                else:
                    progress_dots.label(text="○", icon='BLANK1')
            
            wizard_box.separator()
            
            # Instructions
            wizard_box.label(text="Instructions:", icon='INFO')
            if is_body_step:
                wizard_box.label(text="Assign remaining vertices to body")
                wizard_box.label(text="or select specific vertices if needed")
            else:
                wizard_box.label(text=f"1. Select vertices for '{current_part}' in viewport (Edit mode)")
                wizard_box.label(text="2. Click 'Assign Selected Vertices' below")
            
            wizard_box.separator()
            
            # Vertex count display
            count_row = wizard_box.row()
            count_row.label(text=f"Remaining unassigned: {wizard_state.remaining_vertex_count:,} vertices")
            
            wizard_box.separator()
            
            # Assignment buttons
            if is_body_step:
                # Body step: show both options
                assign_row = wizard_box.row()
                assign_row.scale_y = 1.5
                assign_op = assign_row.operator("pet.assign_selected_vertices", text="Assign Selected")
                assign_remaining_op = assign_row.operator("pet.assign_remaining_to_body", text="Assign Remaining to Body", icon='BRUSH_DATA')
            else:
                # Normal step: just assign selected
                assign_row = wizard_box.row()
                assign_row.scale_y = 1.5
                assign_op = assign_row.operator("pet.assign_selected_vertices", text="Assign Selected Vertices", icon='BRUSH_DATA')
            
            wizard_box.separator()
            
            # Navigation
            nav_row = wizard_box.row()
            prev_op = nav_row.operator("pet.previous_manual_part", text="◄ Previous")
            prev_op.enabled = current_step_idx > 0
            
            if current_step_idx < total_steps - 1:
                next_op = nav_row.operator("pet.next_manual_part", text="Next ►")
            else:
                # Last step - show Finish button
                finish_op = nav_row.operator("pet.finish_manual_assignment", text="Finish", icon='CHECKMARK')
            
            wizard_box.separator()
            
            # Cancel button
            cancel_row = wizard_box.row()
            cancel_op = cancel_row.operator("pet.cancel_manual_assignment", text="Cancel Manual Assignment", icon='X')
            
            layout.separator()
        else:
            # Wizard is inactive - show start button
            manual_box = layout.box()
            manual_box.label(text="Manual Assignment", icon='BRUSH_DATA')
            manual_box.label(text="Step-by-step guide: Select vertices and assign to each body part")
            start_op = manual_box.operator("pet.start_manual_assignment", text="Start Manual Assignment", icon='PLAY')
            layout.separator()
        
        # ===== Detection Method Box =====
        method_box = layout.box()
        method_box.label(text="Detection Method", icon='SETTINGS')
        method_box.prop(settings, "use_geometry_based", text="Geometry-Based (Enhancement Mode)")
        
        # Show description based on method
        if settings.use_geometry_based:
            method_box.label(text="Uses actual mesh shape for detection", icon='INFO')
            method_box.label(text="• Head = Top front relative to body")
            method_box.label(text="• Legs = Bottom front/back")
            method_box.label(text="• Tail = Back of body")
            method_box.label(text="(Slower, use after preview to refine)", icon='TIME')
        else:
            method_box.label(text="Spatial-Only: Uses bounding box percentages", icon='INFO')
            method_box.label(text="(Fast, reliable, works on all meshes)", icon='CHECKMARK')
            method_box.label(text="Preview completes in <2 seconds", icon='TIME')
        layout.separator()
        
        # Hide auto-segmentation options while wizard is active
        if not wizard_state.is_active:
            # ===== Precision Options Box =====
            precision_box = layout.box()
            precision_box.label(text="Refinement Options", icon='MODIFIER')
            precision_box.prop(settings, "use_connectivity_refinement", text="Connectivity Refinement")
            precision_box.prop(settings, "auto_detect_protrusions", text="Auto-Detect Protrusions")
            precision_box.prop(settings, "sensitivity", slider=True)
            layout.separator()
        
        # ===== Performance Options =====
        perf_box = layout.box()
        perf_box.label(text="Performance", icon='PREFERENCES')
        perf_box.prop(settings, "use_fast_mode", text="Fast Mode (for large meshes)")
        if settings.use_fast_mode:
            perf_box.label(text="Fast mode skips expensive operations", icon='INFO')
            perf_box.label(text="Use for meshes > 200k vertices", icon='INFO')
        layout.separator()
        
        # ===== Options =====
        layout.prop(settings, "clear_existing")
        
        # Workflow instructions
        workflow_box = layout.box()
        workflow_box.label(text="Workflow", icon='INFO')
        workflow_box.label(text="1. Click 'Preview' (completes in <2 seconds)")
        workflow_box.label(text="2. Evaluate results - check if 'close enough'")
        workflow_box.label(text="3. Adjust settings and preview again if needed")
        workflow_box.label(text="   • Try Geometry-Based for better accuracy")
        workflow_box.label(text="   • Adjust Sensitivity slider")
        workflow_box.label(text="   • Or manually paint in Weight Paint mode")
        workflow_box.label(text="4. Click 'Segment Model' when satisfied")
        workflow_box.label(text="5. Use 'Split Manually' when ready")
        workflow_box.separator()
        workflow_box.label(text="💡 Iterate quickly: Preview → Evaluate → Adjust → Preview", icon='INFO')
        layout.separator()
        
        # Component viewing instructions (shown after preview)
        if obj.vertex_groups:
            view_box = layout.box()
            view_box.label(text="How to View Components", icon='HIDE_OFF')
            view_box.label(text="After Preview, you can view each component:")
            view_box.label(text="• Weight Paint Mode: Parts are color-coded")
            view_box.label(text="• Properties Panel → Vertex Groups:")
            view_box.label(text="  Click a vertex group name to highlight that part")
            view_box.label(text="• Red = Selected part, Blue = Other parts")
            view_box.separator()
            view_box.label(text="To Select a Component for Editing:")
            view_box.label(text="1. Switch to Edit Mode (Tab)")
            view_box.label(text="2. Select → Select by Vertex Group")
            view_box.label(text="3. Choose the component you want")
            layout.separator()
        
        layout.prop(settings, "auto_split")
        if settings.auto_split:
            layout.label(text="⚠ Auto-split will split immediately", icon='ERROR')
        layout.separator()
        
        # ===== Action Buttons =====
        row = layout.row(align=True)
        row.scale_y = 1.5
        
        # Preview button - operators will read from scene settings
        preview_op = row.operator("pet.preview_segmentation", text="Preview", icon='HIDE_OFF')
        
        # Segment button - operators will read from scene settings
        segment_btn = row.operator("pet.segment_model", text="Segment Model", icon='GROUP_VERTEX')
        layout.separator()
        
        # ===== Results Box (shown after segmentation) =====
        if obj.vertex_groups:
            results_box = layout.box()
            results_box.label(text="Results", icon='TEXT')
            
            # Get metrics from object custom properties (stored by operator)
            parts_detected = obj.get("pet_segmentation_parts", len(obj.vertex_groups))
            vertices_assigned = obj.get("pet_segmentation_vertices", 0)
            processing_time = obj.get("pet_segmentation_time", 0.0)
            
            # Verify vertex count by counting directly from vertex groups if stored count is 0 or seems wrong
            if vertices_assigned == 0 or vertices_assigned < len(obj.data.vertices) * 0.1:
                # Recalculate from actual vertex groups
                actual_count = 0
                all_assigned_verts = set()
                for vg in obj.vertex_groups:
                    for v in obj.data.vertices:
                        for g in v.groups:
                            if g.group == vg.index and g.weight > 0.0:
                                if v.index not in all_assigned_verts:
                                    actual_count += 1
                                    all_assigned_verts.add(v.index)
                                break
                if actual_count > 0:
                    vertices_assigned = actual_count
                    # Update stored value for next time
                    obj["pet_segmentation_vertices"] = actual_count
            
            results_box.label(text=f"Parts Detected: {parts_detected}", icon='MESH_DATA')
            results_box.label(text=f"Vertices Assigned: {vertices_assigned:,}", icon='VERTEXSEL')
            if vertices_assigned == 0:
                results_box.label(text="⚠ No vertices assigned - check segmentation settings", icon='ERROR')
            if processing_time > 0:
                results_box.label(text=f"Segmentation Time: {processing_time:.2f}s", icon='TIME')
            
            # Show vertex groups list
            results_box.separator()
            results_box.label(text="Vertex Groups:", icon='GROUP_VERTEX')
            
            # Count vertices more accurately
            for vg in obj.vertex_groups:
                # Count vertices that have this group with weight > 0
                vert_count = 0
                for v in obj.data.vertices:
                    for g in v.groups:
                        if g.group == vg.index and g.weight > 0.0:
                            vert_count += 1
                            break  # Count each vertex only once
                
                # Color code: green if has vertices, red if empty
                if vert_count > 0:
                    results_box.label(text=f"  ✓ {vg.name}: {vert_count:,} vertices", icon='CHECKMARK')
                else:
                    results_box.label(text=f"  ✗ {vg.name}: 0 vertices (empty)", icon='ERROR')
            
            # Component selection UI
            results_box.separator()
            results_box.label(text="View Components:", icon='HIDE_OFF')
            
            # Show active vertex group
            if obj.vertex_groups.active:
                active_vg = obj.vertex_groups.active
                results_box.label(text=f"Active: {active_vg.name}", icon='RESTRICT_SELECT_OFF')
            
            # Component list with view buttons
            comp_col = results_box.column(align=True)
            for vg in obj.vertex_groups:
                row = comp_col.row(align=True)
                
                # Show if this is the active group
                if vg == obj.vertex_groups.active:
                    row.label(text="→", icon='RESTRICT_SELECT_OFF')
                else:
                    row.label(text="", icon='BLANK1')
                
                # Component name
                row.label(text=vg.name)
                
                # View button - selects this vertex group
                view_op = row.operator("pet.view_vertex_group", text="View", icon='HIDE_OFF')
                view_op.vertex_group_name = vg.name
            
            results_box.separator()
            
            # Instructions for viewing
            if context.mode == 'WEIGHT_PAINT':
                results_box.label(text="💡 Click 'View' buttons above or switch", icon='INFO')
                results_box.label(text="   vertex groups in Properties panel")
            else:
                results_box.label(text="💡 Switch to Weight Paint mode to", icon='INFO')
                results_box.label(text="   visualize vertex groups (or click Preview)")
        
        layout.separator()
        
        # ===== Manual Adjustment Instructions =====
        if obj.vertex_groups:
            adjust_box = layout.box()
            adjust_box.label(text="Manual Adjustment", icon='BRUSH_DATA')
            adjust_box.label(text="To adjust vertex groups:")
            adjust_box.label(text="1. Switch to Weight Paint mode")
            adjust_box.label(text="2. Select vertex group in Properties")
            adjust_box.label(text="3. Use Blender's paint tools to modify")
            adjust_box.label(text="4. Or use Edit mode + Select → Select by Vertex Group")
            layout.separator()
        
        # ===== Split Options (if vertex groups exist) =====
        if obj.vertex_groups:
            split_box = layout.box()
            split_box.label(text="Split Options", icon='OUTLINER_OB_MESH')
            split_box.label(text="Ready to split? Make sure segmentation looks good first!")
            split_op = split_box.operator("pet.split_by_vertex_groups", text="Split Manually", icon='MODIFIER_ON')
            split_op.create_pivots = True
            split_op.keep_original = True
            split_op.verify_data = True
            split_box.prop(split_op, "keep_original")
            split_box.prop(split_op, "verify_data")
            split_box.prop(split_op, "create_pivots")
            
            layout.separator()
        
        # ===== Pivot Points Info =====
        pivot_collection = None
        pivot_collection_name = f"{obj.name}_Pivots"
        for collection in bpy.data.collections:
            if collection.name == pivot_collection_name:
                pivot_collection = collection
                break
        
        if pivot_collection and len(pivot_collection.objects) > 0:
            pivot_box = layout.box()
            pivot_box.label(text=f"Pivot Points: {len(pivot_collection.objects)}", icon='EMPTY_ARROWS')
            for pivot in pivot_collection.objects:
                if pivot.type == 'EMPTY' and 'pet_pivot_type' in pivot:
                    source = pivot.get("pet_source_part", "?")
                    target = pivot.get("pet_target_part", "?")
                    pivot_box.label(text=f"  {source} ↔ {target}")


class PET_PT_rigging(Panel):
    """Rigging panel"""
    bl_label = "Rigging"
    bl_idname = "PET_PT_rigging"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return
        
        if not obj.vertex_groups:
            layout.label(text="Segment model first", icon='INFO')
            return
        
        # Create armature operator
        op_create = layout.operator("pet.create_armature", text="Create Armature")
        layout.prop(op_create, "bone_prefix")
        layout.prop(op_create, "auto_weights")
        
        layout.separator()
        
        # Setup rig operator
        op_setup = layout.operator("pet.setup_rig", text="Setup Rig")
        
        # Check for existing armature
        has_armature = any(o.type == 'ARMATURE' and o.name.startswith(obj.name) 
                          for o in context.scene.objects)
        if has_armature:
            layout.label(text="Armature found", icon='CHECKMARK')


class PET_PT_standardization(Panel):
    """Standardization panel"""
    bl_label = "Standardization"
    bl_idname = "PET_PT_standardization"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected:
            layout.label(text="Select mesh objects", icon='INFO')
            return
        
        layout.label(text=f"{len(selected)} object(s) selected")
        
        # Standardize parts operator
        op = layout.operator("pet.standardize_parts", text="Standardize Selected Parts")
        layout.prop(op, "normalize_scale")
        layout.prop(op, "standardize_orientation")
        
        if op.normalize_scale:
            layout.prop(op, "reference_part")
        
        layout.separator()
        
        # Create attachments operator
        op_att = layout.operator("pet.create_attachments", text="Create Attachment Points")


class PET_PT_export(Panel):
    """Export panel"""
    bl_label = "Export"
    bl_idname = "PET_PT_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        op_export = layout.operator("pet.export_model", text="Export Model")
        layout.prop(op_export, "format", expand=True)
        layout.prop(op_export, "include_metadata")
        
        layout.separator()
        
        op_lib = layout.operator("pet.export_part_library", text="Export Part Library")
        layout.prop(op_lib, "format", expand=True)


class PET_PT_edge_cut_segmentation(Panel):
    """Edge-cut based segmentation for efficient batch workflow"""
    bl_label = "Quick Segment (Edge Cuts)"
    bl_idname = "PET_PT_edge_cut_segmentation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return
        
        info_box = layout.box()
        info_box.label(text="Fast Segmentation Workflow", icon='INFO')
        info_box.label(text="1. Select edge loops around appendages")
        info_box.label(text="2. Mark each cut with segment name")
        info_box.label(text="3. Apply - remaining mesh becomes body")
        layout.separator()
        
        marked_segments = obj.get("pet_marked_segments", [])
        if marked_segments:
            status_box = layout.box()
            status_box.label(text="Marked Segments:", icon='CHECKMARK')
            for seg in marked_segments:
                row = status_box.row()
                row.label(text=f"  {seg}")
                select_op = row.operator("pet.select_segment_edges", text="", icon='RESTRICT_SELECT_OFF')
                select_op.segment_name = seg
        
        layout.separator()
        
        layout.label(text="Mark Selected Edges As:", icon='EDGESEL')
        
        col = layout.column(align=True)
        
        row = col.row(align=True)
        op = row.operator("pet.mark_segment_cut", text="Head")
        op.segment_name = 'head'
        
        row = col.row(align=True)
        op = row.operator("pet.mark_segment_cut", text="Front L Leg")
        op.segment_name = 'leg_front_l'
        op = row.operator("pet.mark_segment_cut", text="Front R Leg")
        op.segment_name = 'leg_front_r'
        
        row = col.row(align=True)
        op = row.operator("pet.mark_segment_cut", text="Back L Leg")
        op.segment_name = 'leg_back_l'
        op = row.operator("pet.mark_segment_cut", text="Back R Leg")
        op.segment_name = 'leg_back_r'
        
        row = col.row(align=True)
        op = row.operator("pet.mark_segment_cut", text="Tail")
        op.segment_name = 'tail'
        
        row = col.row(align=True)
        op = row.operator("pet.mark_segment_cut", text="Left Wing")
        op.segment_name = 'wing_l'
        op = row.operator("pet.mark_segment_cut", text="Right Wing")
        op.segment_name = 'wing_r'
        
        layout.separator()
        
        action_box = layout.box()
        action_box.label(text="Actions", icon='PLAY')
        
        row = action_box.row(align=True)
        row.operator("pet.preview_segment_cuts", text="Preview", icon='HIDE_OFF')
        row.operator("pet.clear_segment_cuts", text="Clear All", icon='X')
        
        action_box.separator()
        
        apply_row = action_box.row()
        apply_row.scale_y = 1.5
        apply_op = apply_row.operator("pet.apply_segment_cuts", text="Apply Cuts & Create Groups", icon='CHECKMARK')
        
        if obj.vertex_groups:
            action_box.separator()
            split_op = action_box.operator("pet.split_by_vertex_groups", text="Split Into Parts", icon='MODIFIER_ON')
            split_op.create_pivots = True
            split_op.keep_original = True


class PET_PT_r6_joints(Panel):
    """Roblox R6 Joint System panel"""
    bl_label = "Roblox R6 Joints"
    bl_idname = "PET_PT_r6_joints"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        body_found = False
        segments_found = []
        joints_found = []
        
        for obj in context.scene.objects:
            if obj.type == 'MESH':
                name_lower = obj.name.lower()
                if 'body' in name_lower or 'torso' in name_lower:
                    body_found = True
                elif any(x in name_lower for x in ['head', 'leg', 'tail', 'wing']):
                    segments_found.append(obj.name)
            elif obj.type == 'EMPTY' and 'r6_joint_type' in obj:
                joints_found.append(obj.name)
        
        status_box = layout.box()
        status_box.label(text="Scene Status", icon='SCENE_DATA')
        
        if body_found:
            status_box.label(text="Body mesh found", icon='CHECKMARK')
        else:
            status_box.label(text="No body mesh found", icon='ERROR')
        
        if segments_found:
            status_box.label(text=f"{len(segments_found)} segment meshes found", icon='CHECKMARK')
        else:
            status_box.label(text="No segment meshes found", icon='INFO')
        
        if joints_found:
            status_box.label(text=f"{len(joints_found)} R6 joints created", icon='CHECKMARK')
        
        layout.separator()
        
        if body_found and segments_found:
            create_box = layout.box()
            create_box.label(text="Create R6 Joints", icon='CON_PIVOT')
            
            row = create_box.row()
            row.scale_y = 1.5
            create_op = row.operator("pet.create_r6_joints", text="Create R6 Joints", icon='CON_PIVOT')
            
            create_box.prop(create_op, "joint_scale")
            create_box.prop(create_op, "use_custom_offsets")
            
            layout.separator()
        else:
            layout.label(text="Split mesh into parts first", icon='INFO')
        
        if joints_found:
            viz_box = layout.box()
            viz_box.label(text="Visualization", icon='HIDE_OFF')
            viz_box.operator("pet.visualize_r6_hierarchy", text="Show Joint Hierarchy", icon='OUTLINER')
            
            layout.separator()
            
            export_box = layout.box()
            export_box.label(text="Export for Roblox", icon='EXPORT')
            export_box.operator("pet.export_r6_metadata", text="Export R6 Metadata (JSON)", icon='FILE')
        
        layout.separator()
        
        info_box = layout.box()
        info_box.label(text="R6 Joint Info", icon='INFO')
        info_box.label(text="Motor6D joints for Roblox animation")
        info_box.label(text="Export as FBX + JSON metadata")
        info_box.label(text="Use Roblox import script with JSON")


class PET_PT_batch_operations(Panel):
    """Batch operations panel for processing multiple models"""
    bl_label = "Batch Operations"
    bl_idname = "PET_PT_batch_operations"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        mesh_count = sum(1 for obj in context.scene.objects if obj.type == 'MESH')
        segmented_count = sum(1 for obj in context.scene.objects 
                            if obj.type == 'MESH' and obj.vertex_groups)
        
        status_box = layout.box()
        status_box.label(text="Scene Overview", icon='SCENE_DATA')
        status_box.label(text=f"Total meshes: {mesh_count}")
        status_box.label(text=f"Segmented meshes: {segmented_count}")
        
        layout.separator()
        
        layout.operator("pet.list_models", text="Detect Pet Models", icon='VIEWZOOM')
        
        layout.separator()
        
        process_box = layout.box()
        process_box.label(text="Batch Processing", icon='CON_ACTION')
        
        row = process_box.row()
        op = row.operator("pet.batch_process_scene", text="Auto-Segment All")
        op.action = 'SEGMENT'
        
        row = process_box.row()
        op = row.operator("pet.batch_process_scene", text="Split All Segmented")
        op.action = 'SPLIT'
        
        row = process_box.row()
        op = row.operator("pet.batch_process_scene", text="Create All R6 Joints")
        op.action = 'CREATE_JOINTS'
        
        layout.separator()
        
        export_box = layout.box()
        export_box.label(text="Batch Export", icon='EXPORT')
        
        export_op = export_box.operator("pet.batch_export_models", text="Export All Models", icon='FILE_FOLDER')
        
        export_box.prop(export_op, "format", expand=True)
        export_box.prop(export_op, "include_metadata")
        export_box.prop(export_op, "include_r6_joints")
        export_box.prop(export_op, "create_manifest")
        
        layout.separator()
        
        tip_box = layout.box()
        tip_box.label(text="Workflow Tips", icon='INFO')
        tip_box.label(text="1. Import all models into scene")
        tip_box.label(text="2. Click 'Auto-Segment All' or use Quick Segment")
        tip_box.label(text="3. Click 'Split All Segmented'")
        tip_box.label(text="4. Click 'Create All R6 Joints'")
        tip_box.label(text="5. Click 'Export All Models'")


classes = [
    PET_SegmentationSettings,
    PET_ManualAssignmentState,
    PET_PT_main_panel,
    PET_PT_mesh_optimization,
    PET_PT_segmentation,
    PET_PT_edge_cut_segmentation,
    PET_PT_rigging,
    PET_PT_r6_joints,
    PET_PT_standardization,
    PET_PT_export,
    PET_PT_batch_operations,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register PropertyGroup on Scene
    bpy.types.Scene.pet_segmentation_settings = bpy.props.PointerProperty(type=PET_SegmentationSettings)
    bpy.types.Scene.pet_manual_assignment_state = bpy.props.PointerProperty(type=PET_ManualAssignmentState)

def unregister():
    # Unregister PropertyGroup from Scene
    if hasattr(bpy.types.Scene, 'pet_segmentation_settings'):
        del bpy.types.Scene.pet_segmentation_settings
    if hasattr(bpy.types.Scene, 'pet_manual_assignment_state'):
        del bpy.types.Scene.pet_manual_assignment_state
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
