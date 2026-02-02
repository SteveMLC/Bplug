"""
UI panels for Pet Model Optimizer
N-panel interface for all addon operations
"""

import bpy
import math
from bpy.types import Panel, PropertyGroup
from bpy.props import EnumProperty, BoolProperty, FloatProperty, IntProperty, StringProperty
from ..utils import bmesh_helpers
from ..config.animal_presets import get_preset_names


# Part definitions for each pet type (for UI display)
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


def get_cached_vertex_group_counts(obj):
    """
    Get cached vertex counts for all vertex groups.
    Cache is invalidated when mesh or vertex groups change.
    This avoids expensive recalculation on every UI redraw.
    
    Returns:
        dict: {vertex_group_name: vertex_count, ...}
    """
    cache_key = "pet_vg_counts_cache"
    cache_version_key = "pet_vg_counts_version"
    
    # Generate a version identifier based on mesh state
    mesh_hash = hash((
        len(obj.data.vertices),
        len(obj.vertex_groups),
        tuple(vg.name for vg in obj.vertex_groups),
        tuple(vg.index for vg in obj.vertex_groups)
    ))
    
    # Check if cache is valid
    cached_counts = obj.get(cache_key, None)
    cached_version = obj.get(cache_version_key, None)
    
    if cached_counts is None or cached_version != mesh_hash:
        # Cache miss or invalid - recalculate counts
        # This is expensive but only happens when mesh/groups change
        cached_counts = {}
        for vg in obj.vertex_groups:
            vert_count = 0
            vg_index = vg.index
            # Use direct index access for better performance
            for v in obj.data.vertices:
                # Check groups list efficiently
                for g in v.groups:
                    if g.group == vg_index and g.weight > 0.0:
                        vert_count += 1
                        break
            cached_counts[vg.name] = vert_count
        
        # Store cache - WRAP IN TRY/EXCEPT to handle "Writing to ID classes" error
        # This can fail during UI drawing, but that's OK - we still return the calculated counts
        try:
            obj[cache_key] = cached_counts
            obj[cache_version_key] = mesh_hash
        except (AttributeError, RuntimeError, TypeError):
            # Writing to object properties is not allowed during UI drawing
            # This is fine - we'll just recalculate next time (performance hit, but functional)
            # The calculated counts are still valid and returned
            pass
    
    return cached_counts


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
    
    invert_forward_axis: BoolProperty(
        name="Invert Forward Axis",
        description="Manually invert the forward axis if auto-detection gets head/tail reversed. Use this if head is detected as tail and vice versa.",
        default=False
    )


class PET_SplitSettings(PropertyGroup):
    """PropertyGroup for split settings stored on Scene"""
    
    keep_original: BoolProperty(
        name="Keep Original Mesh",
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
    
    create_pivots: BoolProperty(
        name="Create Pivot Points",
        description="Create pivot points at disconnect boundaries",
        default=True
    )
    
    strict_mode: BoolProperty(
        name="Strict Mode",
        description="Only include faces where ALL vertices are in the group (100% match)",
        default=False
    )


class PET_EdgeCleanupSettings(PropertyGroup):
    """PropertyGroup for edge cleanup settings stored on Scene"""

    iterations: IntProperty(
        name="Iterations",
        description="Number of smoothing passes",
        default=2,
        min=1,
        max=10,
    )

    smooth_factor: FloatProperty(
        name="Smooth Factor",
        description="Strength of smoothing per iteration (0.0 = no smoothing, 1.0 = full smoothing).",
        default=0.5,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
    )

    only_boundary: BoolProperty(
        name="Only Boundary Edges",
        description="Only smooth edges on cut boundaries (recommended)",
        default=True,
    )

    boundary_band_steps: IntProperty(
        name="Boundary Band",
        description="Expand smoothing selection by this many vertex rings from the boundary",
        default=1,
        min=0,
        max=6,
    )

    max_vertex_displacement: FloatProperty(
        name="Max Displacement",
        description="Clamp how far smoothed vertices can move (0 = unlimited)",
        default=0.0,
        min=0.0,
        max=10.0,
        step=0.01,
        precision=4,
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


class PET_SymmetrySettings(PropertyGroup):
    """PropertyGroup for symmetry tools settings"""
    
    def get_preset_items(self, context):
        items = [('none', "None", "No preset - detect automatically")]
        items.extend(get_preset_names())
        return items
    
    animal_preset: EnumProperty(
        name="Animal Type",
        description="Select animal type for proportion hints",
        items=get_preset_items,
        default=0
    )
    
    mirror_threshold: FloatProperty(
        name="Mirror Threshold",
        description="Distance threshold for matching mirrored vertices",
        default=0.05,
        min=0.001,
        max=1.0
    )


class PET_ManualPartSelectionState(PropertyGroup):
    """PropertyGroup for manual part selection state stored on Scene"""
    
    is_active: BoolProperty(
        name="Manual Part Selection Active",
        description="Whether manual part selection mode is currently active",
        default=False
    )
    
    current_part: StringProperty(
        name="Current Part",
        description="Name of the part currently being assigned",
        default=""
    )
    
    current_part_index: IntProperty(
        name="Current Part Index",
        description="Index of current part in the part list",
        default=0,
        min=0
    )
    
    total_parts: IntProperty(
        name="Total Parts",
        description="Total number of parts to assign",
        default=0,
        min=0
    )
    
    current_selection_vertex_count: IntProperty(
        name="Current Selection Vertex Count",
        description="Number of vertices in current selection",
        default=0,
        min=0
    )


class PET_PreOptimizationSettings(PropertyGroup):
    """Settings for pre-segmentation mesh optimization"""
    
    # === CLEANING SETTINGS ===
    merge_distance: FloatProperty(
        name="Merge Distance",
        description="Distance below which vertices are merged (in Blender units)",
        default=0.0001,
        min=0.00001,
        max=0.01,
        precision=5,
    )
    
    delete_loose: BoolProperty(
        name="Delete Loose Geometry",
        description="Remove vertices and edges not connected to any faces",
        default=True,
    )
    
    dissolve_degenerate: BoolProperty(
        name="Dissolve Degenerate",
        description="Remove zero-area faces and degenerate edges",
        default=True,
    )
    
    fix_non_manifold: BoolProperty(
        name="Fix Non-Manifold Edges",
        description="Remove duplicate faces causing non-manifold edges (edges shared by 3+ faces)",
        default=True,
    )
    
    # === REDUCTION SETTINGS ===
    reduction_percent: FloatProperty(
        name="Reduction Step",
        description="Percentage of faces to remove per click (1-20%)",
        default=5.0,
        min=1.0,
        max=20.0,
        subtype='PERCENTAGE',
        precision=1,
    )
    
    use_auto_step: BoolProperty(
        name="Auto Step Size",
        description="Automatically calculate safe step size based on mesh complexity",
        default=True,
    )
    
    feature_angle: FloatProperty(
        name="Feature Angle",
        description="Angle threshold for detecting sharp edges (degrees)",
        default=30.0,
        min=15.0,
        max=60.0,
    )
    
    preserve_sharp: BoolProperty(
        name="Preserve Sharp Edges",
        description="Respect sharp edge marks during decimation",
        default=True,
    )
    
    preserve_seams: BoolProperty(
        name="Preserve UV Seams",
        description="Respect UV seam marks during decimation",
        default=True,
    )
    
    target_faces: IntProperty(
        name="Target Faces",
        description="Target face count for auto-reduce (0 = manual only)",
        default=0,
        min=0,
    )


class PET_PostSplitOptimizationSettings(PropertyGroup):
    """Settings for post-split part optimization"""
    
    reduction_percent: FloatProperty(
        name="Reduction Step",
        description="Percentage of faces to remove per click (1-20%)",
        default=5.0,
        min=1.0,
        max=20.0,
        subtype='PERCENTAGE',
        precision=1,
    )
    
    preserve_boundaries: BoolProperty(
        name="Preserve Boundaries",
        description="Protect cut boundary edges from decimation",
        default=True,
    )
    
    preserve_pivots: BoolProperty(
        name="Preserve Pivots",
        description="Avoid decimating near pivot points",
        default=True,
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
    """Pre-segmentation mesh optimization panel"""
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
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return
        
        # Get settings (always available after registration)
        settings = scene.pet_pre_optimization_settings
        
        # =================================================================
        # MESH INFO SECTION
        # =================================================================
        info_box = layout.box()
        info_box.label(text="Mesh Information", icon='MESH_DATA')
        
        mesh = obj.data
        vert_count = len(mesh.vertices)
        face_count = len(mesh.polygons)
        
        row = info_box.row()
        row.label(text=f"Vertices: {vert_count:,}")
        row.label(text=f"Faces: {face_count:,}")
        
        # Show optimization progress if available
        from ..utils import algorithms
        try:
            stats = algorithms.get_optimization_stats(obj)
        except:
            stats = {}
        
        if stats.get('has_history', False):
            progress_box = info_box.box()
            progress_box.label(text="Optimization Progress", icon='TIME')
            progress_box.label(
                text=f"Original: {stats['initial_faces']:,} faces"
            )
            progress_box.label(
                text=f"Current: {stats['current_faces']:,} faces "
                     f"({stats['face_reduction_percent']:.1f}% reduced)"
            )
            progress_box.label(text=f"Steps taken: {stats['step_count']}")
        
        # Recommended step size
        recommended, explanation = algorithms.get_recommended_step_size(obj)
        info_box.label(text=explanation, icon='INFO')
        
        layout.separator()
        
        # =================================================================
        # MESH CLEANING SECTION (First Step!)
        # =================================================================
        clean_box = layout.box()
        clean_box.label(text="Step 1: Mesh Cleaning", icon='BRUSH_DATA')
        clean_box.label(text="Fix geometry issues before decimation", icon='INFO')
        
        # Check if we have cached analysis results (with error handling)
        # Read cache directly instead of calling function (INSTANT - no function call)
        has_analysis = False
        problems = None
        
        try:
            if "pet_mesh_analysis_cache" in obj:
                cached = obj.get("pet_mesh_analysis_cache", {})
                # Use duck-typing: check for key existence, not dict type
                # IDPropertyGroup from Blender doesn't pass isinstance(dict) check
                if cached and 'total_problems' in cached:
                    problems = dict(cached)  # Convert to dict to ensure consistent access
                    has_analysis = True
        except Exception as e:
            # Cache read failed - show error but don't crash UI
            clean_box.label(text=f"Cache error: {str(e)[:50]}", icon='ERROR')
            has_analysis = False
            problems = None
        
        if has_analysis and problems:
            try:
                if problems.get('total_problems', 0) > 0:
                    # Show problem counts in warning style
                    problem_col = clean_box.column(align=True)
                    problem_col.alert = True
                    
                    row1 = problem_col.row()
                    row1.label(text=f"Loose verts: {problems.get('loose_verts', 0):,}")
                    row1.label(text=f"Loose edges: {problems.get('loose_edges', 0):,}")
                    
                    row2 = problem_col.row()
                    row2.label(text=f"Degenerate: {problems.get('degenerate_faces', 0):,}")
                    row2.label(text=f"Non-manifold: {problems.get('non_manifold_edges', 0):,}")
                    
                    clean_box.label(
                        text=f"Total: {problems.get('total_problems', 0):,} issues found!",
                        icon='ERROR'
                    )
                else:
                    # Check if already cleaned
                    try:
                        if obj.get("pet_last_cleaned", False):
                            clean_box.label(text="Mesh is clean", icon='CHECKMARK')
                        else:
                            clean_box.label(text="No obvious issues detected", icon='CHECKMARK')
                    except:
                        clean_box.label(text="No obvious issues detected", icon='CHECKMARK')
            except Exception as e:
                # Error displaying results - show fallback
                clean_box.label(text="Error displaying results", icon='ERROR')
                clean_box.label(text="Click 'Analyze' to re-check", icon='INFO')
        else:
            # No analysis yet - show info message
            clean_box.label(text="Click 'Analyze' to check for issues", icon='INFO')
        
        # Cleaning settings
        settings_col = clean_box.column(align=True)
        try:
            settings_col.prop(settings, "merge_distance")
            settings_col.prop(settings, "delete_loose")
            settings_col.prop(settings, "dissolve_degenerate")
        except Exception as e:
            # Settings property missing - show error but don't crash
            clean_box.label(text=f"Settings error: {str(e)[:50]}", icon='ERROR')
            clean_box.label(text="Try reloading the addon", icon='INFO')
        
        # Buttons row
        button_row = clean_box.row(align=True)
        
        # Analyze button
        try:
            analyze_op = button_row.operator(
                "pet.analyze_mesh",
                text="Analyze",
                icon='VIEWZOOM'
            )
        except Exception as e:
            clean_box.label(text=f"Error creating Analyze button: {str(e)[:50]}", icon='ERROR')
        
        # Clean button
        try:
            if has_analysis and problems:
                total = problems.get('total_problems', 0)
                clean_text = "Clean Mesh" if total == 0 else f"Clean ({total} issues)"
            else:
                # Try to get from cache if available
                try:
                    cached = obj.get("pet_mesh_analysis_cache", {})
                    total = cached.get('total_problems', 0) if isinstance(cached, dict) else 0
                    clean_text = "Clean Mesh" if total == 0 else f"Clean ({total} issues)"
                except:
                    clean_text = "Clean Mesh"
            
            clean_op = button_row.operator(
                "pet.clean_mesh",
                text=clean_text,
                icon='BRUSH_DATA'
            )
            # Safely get settings values with defaults
            try:
                clean_op.merge_distance = getattr(settings, "merge_distance", 0.0001)
                clean_op.delete_loose = getattr(settings, "delete_loose", True)
                clean_op.dissolve_degenerate = getattr(settings, "dissolve_degenerate", True)
                clean_op.fix_non_manifold = getattr(settings, "fix_non_manifold", True)
            except Exception as e:
                # If settings access fails, use operator defaults
                clean_op.merge_distance = 0.0001
                clean_op.delete_loose = True
                clean_op.dissolve_degenerate = True
        except Exception as e:
            clean_box.label(text=f"Error creating Clean button: {str(e)[:50]}", icon='ERROR')
        
        layout.separator()
        
        # =================================================================
        # FEATURE DETECTION SECTION
        # =================================================================
        feature_box = layout.box()
        feature_box.label(text="Step 2: Feature Detection", icon='SNAP_MIDPOINT')
        feature_box.label(text="Detect sharp edges to protect during reduction")
        
        feature_box.prop(settings, "feature_angle", text="Angle Threshold")
        
        # Feature counts (use cache for performance)
        edge_counts = algorithms.count_feature_edges(obj, use_cache=True)
        if edge_counts['sharp'] > 0 or edge_counts['boundary'] > 0:
            count_row = feature_box.row()
            count_row.label(text=f"Sharp: {edge_counts['sharp']:,}")
            count_row.label(text=f"Boundary: {edge_counts['boundary']:,}")
        
        # Show marked count after detection
        marked_count = obj.get("pet_feature_edges_marked", 0)
        if marked_count > 0:
            feature_box.label(text=f"Last detection marked: {marked_count:,} edges", icon='CHECKMARK')
        
        # Detect/Clear buttons
        detect_row = feature_box.row(align=True)
        detect_op = detect_row.operator("pet.detect_features", text="Detect Features", icon='VIEWZOOM')
        detect_op.angle_threshold = settings.feature_angle
        
        detect_row.operator("pet.clear_feature_marks", text="Clear", icon='X')
        
        layout.separator()
        
        # =================================================================
        # ITERATIVE REDUCTION SECTION
        # =================================================================
        reduce_box = layout.box()
        reduce_box.label(text="Step 3: Iterative Reduction", icon='MOD_DECIM')
        reduce_box.label(text="Click repeatedly to reduce mesh in controlled steps")
        
        reduce_box.prop(settings, "reduction_percent", slider=True)
        reduce_box.prop(settings, "use_auto_step")
        
        col = reduce_box.column(align=True)
        col.prop(settings, "preserve_sharp")
        col.prop(settings, "preserve_seams")
        
        # Calculate expected reduction for display
        if settings.use_auto_step:
            expected_ratio = recommended
        else:
            expected_ratio = settings.reduction_percent / 100.0
        expected_verts = int(vert_count * expected_ratio)
        reduce_box.label(
            text=f"Will remove ~{expected_verts:,} vertices per step",
            icon='INFO'
        )
        
        # Main reduce button
        reduce_row = reduce_box.row()
        reduce_row.scale_y = 1.5
        reduce_op = reduce_row.operator(
            "pet.decimate_step",
            text=f"Reduce by {settings.reduction_percent:.0f}%",
            icon='PLAY'
        )
        reduce_op.reduction_percent = settings.reduction_percent
        reduce_op.use_auto_step = settings.use_auto_step
        reduce_op.preserve_sharp = settings.preserve_sharp
        reduce_op.preserve_seams = settings.preserve_seams
        
        layout.separator()
        
        # =================================================================
        # TARGET-BASED REDUCTION SECTION
        # =================================================================
        target_box = layout.box()
        target_box.label(text="Target-Based Reduction", icon='DRIVER_DISTANCE')
        target_box.label(text="Automatically reduce to target face count (multi-step)")
        target_box.label(text="This will run multiple iterations automatically", icon='INFO')
        
        target_box.prop(settings, "target_faces", text="Target Faces")
        
        target_row = target_box.row()
        target_row.scale_y = 1.2
        target_op = target_row.operator(
            "pet.decimate_to_target",
            text="Auto-Reduce to Target",
            icon='FORWARD'
        )
        if settings.target_faces > 0:
            target_op.target_faces = settings.target_faces
        target_op.preserve_sharp = settings.preserve_sharp
        
        layout.separator()
        
        # =================================================================
        # RESET SECTION
        # =================================================================
        reset_row = layout.row(align=True)
        reset_row.operator("pet.reset_optimization", text="Reset Stats", icon='FILE_REFRESH')
        
        # Undo hint
        layout.label(text="Use Ctrl+Z to undo reduction steps", icon='LOOP_BACK')


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
            prev_row = nav_row.row()
            prev_row.enabled = current_step_idx > 0
            prev_op = prev_row.operator("pet.previous_manual_part", text="◄ Previous")
            
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
            method_box.label(text="• Head = Blocky/square shape at front")
            method_box.label(text="• Legs = Cylindrical/squarish at bottom (pairs)")
            method_box.label(text="• Tail = Elongated/thin at back")
            method_box.label(text="• Horns = Top lateral (included with head)")
            method_box.label(text="(Slower, use after preview to refine)", icon='TIME')
            
            # Orientation override option
            method_box.separator()
            method_box.prop(settings, "invert_forward_axis", text="Invert Forward Axis (Manual Override)")
            if settings.invert_forward_axis:
                method_box.label(text="Forward axis inverted - head/tail swapped", icon='INFO')
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
            
            # Use cached vertex counts for performance
            vg_counts = get_cached_vertex_group_counts(obj)
            for vg in obj.vertex_groups:
                vert_count = vg_counts.get(vg.name, 0)
                
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


class PET_PT_split(Panel):
    """Split panel - split segmented mesh into separate objects"""
    bl_label = "Split"
    bl_idname = "PET_PT_split"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    # Removed DEFAULT_CLOSED - panel is always visible when vertex groups exist
    
    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return
        
        if not obj.vertex_groups:
            info_box = layout.box()
            info_box.label(text="No vertex groups found", icon='INFO')
            info_box.label(text="Segment your model first using:")
            info_box.label(text="• Segmentation panel")
            info_box.label(text="• Quick Segment (Edge Cuts)")
            info_box.label(text="• Manual Part Segmentation")
            return
        
        # ===== Status Info =====
        status_box = layout.box()
        status_box.label(text="Status", icon='INFO')
        status_box.label(text=f"Vertex Groups: {len(obj.vertex_groups)}")
        
        # List vertex groups with cached vertex counts for performance
        vg_counts = get_cached_vertex_group_counts(obj)
        
        vg_list = status_box.column(align=True)
        for vg in obj.vertex_groups:
            vert_count = vg_counts.get(vg.name, 0)
            
            row = vg_list.row(align=True)
            if vert_count > 0:
                row.label(text=f"  ✓ {vg.name}: {vert_count:,} vertices", icon='CHECKMARK')
            else:
                row.label(text=f"  ✗ {vg.name}: 0 vertices (empty)", icon='ERROR')
        
        layout.separator()
        
        # ===== Split Options =====
        split_box = layout.box()
        split_box.label(text="Split Into Parts", icon='MODIFIER_ON')
        split_box.label(text="Ready to split? Make sure segmentation looks good first!", icon='INFO')
        
        split_box.separator()
        
        # Get settings from scene properties
        settings = context.scene.pet_split_settings
        
        # Display all properties using PropertyGroup (this works!)
        split_box.prop(settings, "keep_original", text="Keep Original Mesh")
        split_box.prop(settings, "verify_data", text="Verify Data Preservation")
        
        split_box.separator()
        
        split_box.prop(settings, "gap_distance", slider=True)
        split_box.label(text="Gap: Creates space between parts for workflow", icon='INFO')
        split_box.label(text="(Makes cut edges accessible for smoothing/filling)")
        
        split_box.separator()
        
        split_box.prop(settings, "create_pivots", text="Create Pivot Points")
        split_box.label(text="⚠️ Pivots calculated BEFORE gaps (for R6 joints)", icon='ERROR')
        
        split_box.separator()
        
        # Split button - operator will read from scene settings
        split_op = split_box.operator("pet.split_by_vertex_groups", text="Split Into Parts", icon='MODIFIER_ON')
        
        layout.separator()
        
        # ===== Clean Split Section =====
        clean_box = layout.box()
        clean_box.label(text="Clean Split (For Pre-Cleaned Meshes)", icon='CHECKMARK')
        
        # Help text explaining when to use clean split
        help_col = clean_box.column(align=True)
        help_col.scale_y = 0.8
        help_col.label(text="Use when mesh has been cleaned and vertex")
        help_col.label(text="groups precisely assigned. Strictly follows")
        help_col.label(text="highlighted regions without expansion.")
        
        clean_box.separator()
        
        # Clean split button
        clean_box.operator("pet.split_clean", text="Clean Split", icon='CHECKMARK')
        
        # Strict mode toggle - now from settings, not operator
        row = clean_box.row()
        row.prop(settings, "strict_mode", text="Strict Mode (100% vertex match)")
        
        clean_box.separator()
        
        # Comparison info
        compare_col = clean_box.column(align=True)
        compare_col.scale_y = 0.75
        compare_col.label(text="Standard Split vs Clean Split:", icon='INFO')
        compare_col.label(text="• Standard: Expands to fill gaps, includes")
        compare_col.label(text="  adjacent geometry, uses spatial boundaries")
        compare_col.label(text="• Clean: ONLY includes faces where vertices")
        compare_col.label(text="  are assigned to the vertex group")
        
        layout.separator()
        
        # ===== What Happens Info =====
        info_box = layout.box()
        info_box.label(text="What Happens When You Split:", icon='INFO')
        info_box.label(text="1. Pivot positions calculated (from vertex group boundaries)")
        info_box.label(text="2. Mesh split into separate objects")
        info_box.label(text="3. Gaps created between parts (workflow convenience)")
        info_box.label(text="4. Pivot markers created (for visualization)")
        info_box.label(text="")
        info_box.label(text="After splitting, use Post-Split Cleanup to:", icon='MODIFIER')
        info_box.label(text="• Clean edges (smooth cut boundaries)")
        info_box.label(text="• Fill cuts (cap open surfaces)")
        
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
        info_box.label(text="1. Click 'Find Edge Loop for [Part]' to auto-detect boundary")
        info_box.label(text="2. (Optional) Refine selection with Grow/Shrink/Smooth")
        info_box.label(text="3. Mark each cut with segment name")
        info_box.label(text="4. Apply - remaining mesh becomes body")
        info_box.label(text="Auto-find uses grow logic for accurate boundaries", icon='INFO')
        layout.separator()
        
        # Pet Type Selector
        settings = context.scene.pet_segmentation_settings
        layout.label(text="Pet Type:")
        row = layout.row()
        row.prop(settings, "pet_type", expand=True)
        layout.separator()
        
        # Auto-Find Edge Loops Section
        auto_find_box = layout.box()
        auto_find_box.label(text="Auto-Find Edge Loops", icon='LOOP_FORWARDS')
        auto_find_box.label(text="Select vertices for part, then click to find boundary loop")
        
        col = auto_find_box.column(align=True)
        
        row = col.row(align=True)
        op = row.operator("pet.find_edge_loop_for_part", text="Find Edge Loop for Head")
        op.part_type = 'head'
        
        row = col.row(align=True)
        op = row.operator("pet.find_edge_loop_for_part", text="Find Edge Loop for Front L Leg")
        op.part_type = 'leg_front_l'
        op = row.operator("pet.find_edge_loop_for_part", text="Find Edge Loop for Front R Leg")
        op.part_type = 'leg_front_r'
        
        row = col.row(align=True)
        op = row.operator("pet.find_edge_loop_for_part", text="Find Edge Loop for Back L Leg")
        op.part_type = 'leg_back_l'
        op = row.operator("pet.find_edge_loop_for_part", text="Find Edge Loop for Back R Leg")
        op.part_type = 'leg_back_r'
        
        row = col.row(align=True)
        op = row.operator("pet.find_edge_loop_for_part", text="Find Edge Loop for Tail")
        op.part_type = 'tail'
        
        row = col.row(align=True)
        op = row.operator("pet.find_edge_loop_for_part", text="Find Edge Loop for Left Wing")
        op.part_type = 'wing_l'
        op = row.operator("pet.find_edge_loop_for_part", text="Find Edge Loop for Right Wing")
        op.part_type = 'wing_r'
        
        layout.separator()
        
        # Refine Selection Section - for improving edge loop accuracy
        refine_box = layout.box()
        refine_box.label(text="Refine Edge Selection", icon='MODIFIER')
        refine_box.label(text="Improve edge loop accuracy before marking")
        
        if context.mode != 'EDIT_MESH':
            refine_box.label(text="Switch to Edit Mode to refine selection", icon='INFO')
        else:
            # Selection refinement tools
            refine_col = refine_box.column(align=True)
            
            # Grow/Shrink row
            grow_shrink_row = refine_col.row(align=True)
            # Add Grow - button first (weakest - plane aware)
            grow_minus_op = grow_shrink_row.operator("pet.grow_selection_plane_aware", text="Grow -", icon='FULLSCREEN_ENTER')
            # Grow + button (strongest - no restrictions)
            grow_op = grow_shrink_row.operator("pet.grow_selection", text="Grow +", icon='FULLSCREEN_ENTER')
            grow_op.iterations = 1
            shrink_op = grow_shrink_row.operator("pet.shrink_selection", text="Shrink -", icon='FULLSCREEN_EXIT')
            shrink_op.iterations = 1
            
            # Smooth boundary
            smooth_row = refine_col.row(align=True)
            smooth_op = smooth_row.operator("pet.smooth_selection_boundary", text="Smooth Boundary", icon='BRUSH_DATA')
            smooth_op.iterations = 2
            
            refine_box.separator()
            refine_box.label(text="💡 Use after 'Find Edge Loop' to refine the boundary", icon='INFO')
            refine_box.label(text="Grow/Shrink: Expand or contract edge selection", icon='INFO')
            refine_box.label(text="Smooth: Clean up jagged boundary edges", icon='INFO')
        
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
            create_box.separator()
            create_box.prop(create_op, "use_stored_pivots")
            if create_op.use_stored_pivots:
                create_box.label(text="✓ Uses pivot positions from split operation", icon='CHECKMARK')
                create_box.label(text="Pivots are at actual boundaries (before gaps)", icon='INFO')
            else:
                create_box.label(text="⚠️ Will recalculate (may place in gap center)", icon='ERROR')
            
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
        
        if body_found and segments_found:
            info_box.separator()
            info_box.label(text="⚠️ Critical: Pivot Positions", icon='ERROR')
            create_op = layout.operator("pet.create_r6_joints", text="Create R6 Joints")
            info_box.prop(create_op, "use_stored_pivots")
            info_box.label(text="Stored pivots are at actual boundaries", icon='INFO')
            info_box.label(text="(calculated BEFORE gaps were created)", icon='INFO')


class PET_PT_post_split_optimization(Panel):
    """Post-split mesh optimization panel for reducing split parts"""
    bl_label = "Post-Split Optimization"
    bl_idname = "PET_PT_post_split_optimization"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Get selected mesh parts
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_meshes:
            layout.label(text="Select split part objects", icon='INFO')
            layout.label(text="(Objects created from splitting)")
            return
        
        # Get settings (always available after registration)
        settings = scene.pet_post_split_optimization_settings
        
        # =================================================================
        # SELECTED PARTS INFO
        # =================================================================
        info_box = layout.box()
        info_box.label(text=f"Selected Parts: {len(selected_meshes)}", icon='MESH_DATA')
        
        total_faces = 0
        total_verts = 0
        
        # Show per-part info (limit to 6 to avoid UI clutter)
        parts_col = info_box.column(align=True)
        for i, obj in enumerate(selected_meshes[:6]):
            faces = len(obj.data.polygons)
            verts = len(obj.data.vertices)
            total_faces += faces
            total_verts += verts
            
            # Check for boundary protection
            boundaries = obj.get("pet_boundary_edges_protected", 0)
            boundary_text = f" ({boundaries} edges protected)" if boundaries > 0 else ""
            
            parts_col.label(text=f"  {obj.name}: {faces:,} faces{boundary_text}")
        
        if len(selected_meshes) > 6:
            parts_col.label(text=f"  ... and {len(selected_meshes) - 6} more")
            for obj in selected_meshes[6:]:
                total_faces += len(obj.data.polygons)
                total_verts += len(obj.data.vertices)
        
        info_box.label(text=f"Total: {total_verts:,} vertices, {total_faces:,} faces")
        
        layout.separator()
        
        # =================================================================
        # BOUNDARY PROTECTION SECTION
        # =================================================================
        boundary_box = layout.box()
        boundary_box.label(text="Boundary Protection", icon='LOCKED')
        boundary_box.label(text="Protect cut edges from decimation")
        
        boundary_box.prop(settings, "preserve_boundaries")
        boundary_box.prop(settings, "preserve_pivots")
        
        # Protect boundaries button
        protect_row = boundary_box.row()
        protect_row.operator("pet.protect_boundaries", text="Mark Boundaries", icon='EDGESEL')
        
        # Show boundary counts
        from ..utils import algorithms
        total_boundaries = 0
        for obj in selected_meshes:
            counts = algorithms.count_feature_edges(obj)
            total_boundaries += counts.get('boundary', 0)
        
        if total_boundaries > 0:
            boundary_box.label(text=f"Total boundary edges: {total_boundaries:,}", icon='INFO')
        
        layout.separator()
        
        # =================================================================
        # PER-PART REDUCTION SECTION
        # =================================================================
        reduce_box = layout.box()
        reduce_box.label(text="Per-Part Reduction", icon='MOD_DECIM')
        reduce_box.label(text="Reduce all selected parts while preserving boundaries")
        
        reduce_box.prop(settings, "reduction_percent", slider=True)
        
        # Calculate expected reduction
        expected_ratio = settings.reduction_percent / 100.0
        expected_faces = int(total_faces * expected_ratio)
        reduce_box.label(
            text=f"Will remove ~{expected_faces:,} faces total",
            icon='INFO'
        )
        
        # Main reduce button
        reduce_row = reduce_box.row()
        reduce_row.scale_y = 1.5
        reduce_op = reduce_row.operator(
            "pet.optimize_selected_parts",
            text=f"Reduce All by {settings.reduction_percent:.0f}%",
            icon='PLAY'
        )
        reduce_op.reduction_percent = settings.reduction_percent
        reduce_op.preserve_boundaries = settings.preserve_boundaries
        
        layout.separator()
        
        # =================================================================
        # SINGLE PART REDUCTION
        # =================================================================
        single_box = layout.box()
        single_box.label(text="Single Part Reduction", icon='OBJECT_DATA')
        
        obj = context.active_object
        if obj and obj.type == 'MESH':
            single_box.label(text=f"Active: {obj.name}", icon='RESTRICT_SELECT_OFF')
            
            single_op = single_box.operator(
                "pet.optimize_part",
                text=f"Reduce {obj.name}",
                icon='PLAY'
            )
            single_op.reduction_percent = settings.reduction_percent
            single_op.preserve_boundaries = settings.preserve_boundaries
        else:
            single_box.label(text="No active mesh object", icon='INFO')
        
        layout.separator()
        
        # =================================================================
        # WORKFLOW GUIDANCE
        # =================================================================
        workflow_box = layout.box()
        workflow_box.label(text="Workflow", icon='INFO')
        workflow_box.label(text="1. Select split parts to optimize")
        workflow_box.label(text="2. Click 'Mark Boundaries' to protect cut edges")
        workflow_box.label(text="3. Adjust reduction percentage (3-5% recommended)")
        workflow_box.label(text="4. Click 'Reduce All' - repeat as needed")
        workflow_box.label(text="5. Use Ctrl+Z to undo if over-reduced")


class PET_PT_post_split_cleanup(Panel):
    """Post-split cleanup panel for edge smoothing and cut filling"""
    bl_label = "Post-Split Cleanup"
    bl_idname = "PET_PT_post_split_cleanup"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_meshes:
            layout.label(text="Select split part objects", icon='INFO')
            layout.label(text="(Objects created from splitting)")
            return
        
        layout.label(text=f"{len(selected_meshes)} mesh object(s) selected", icon='MESH_DATA')
        layout.separator()
        
        # Edge Cleaning Section
        edge_box = layout.box()
        edge_box.label(text="Edge Cleaning", icon='MODIFIER')
        edge_box.label(text="Smooth cut boundary edges for cleaner surfaces")
        
        if context.mode != 'OBJECT':
            edge_box.label(text="Switch to Object Mode", icon='INFO')
        else:
            ec = context.scene.pet_edge_cleanup_settings

            edge_box.prop(ec, "iterations")
            edge_box.prop(ec, "smooth_factor", slider=True)
            edge_box.prop(ec, "only_boundary")
            edge_box.prop(ec, "boundary_band_steps")
            edge_box.prop(ec, "max_vertex_displacement")

            edge_box.operator("pet.smooth_cut_edges", text="Smooth Cut Edges", icon='BRUSH_DATA')

            edge_box.separator()
            edge_box.operator("pet.select_cut_boundaries", text="Select Cut Boundaries", icon='RESTRICT_SELECT_OFF')
            edge_box.label(text="Tip: boundary band improves seam quality", icon='INFO')
        
        layout.separator()
        
        # Cut Filling Section
        fill_box = layout.box()
        fill_box.label(text="Cut Face Filling", icon='MESH_ICOSPHERE')
        fill_box.label(text="Fill open cut boundaries with material-matched faces")
        
        if context.mode != 'OBJECT':
            fill_box.label(text="Switch to Object Mode", icon='INFO')
        else:
            fill_op = fill_box.operator("pet.fill_cut_faces", text="Fill Cut Faces", icon='FULLSCREEN_ENTER')
            fill_box.prop(fill_op, "use_material_color")
            
            if fill_op.use_material_color:
                fill_box.prop(fill_op, "color_darkening_factor", slider=True)
                fill_box.prop(fill_op, "sample_depth")
            else:
                fill_box.prop(fill_op, "fallback_color")
            
            fill_box.separator()
            fill_box.prop(fill_op, "auto_smooth_filled")
            
            if fill_op.auto_smooth_filled:
                fill_box.prop(fill_op, "smooth_iterations")
                fill_box.prop(fill_op, "smooth_factor", slider=True)
            
            fill_box.separator()
            fill_box.label(text="Color Detection:", icon='INFO')
            fill_box.label(text="1. Adjacent faces (sample_depth)")
            fill_box.label(text="2. Principled BSDF base color")
            fill_box.label(text="3. Material diffuse color")
            fill_box.label(text="4. Vertex colors (average)")
            fill_box.label(text="5. Fallback color")
        
        layout.separator()
        
        # Gap Creation Section
        gap_box = layout.box()
        gap_box.label(text="Gap Creation", icon='ARROW_LEFTRIGHT')
        gap_box.label(text="Create gaps between split parts for visual review")
        
        if context.mode != 'OBJECT':
            gap_box.label(text="Switch to Object Mode", icon='INFO')
        else:
            gap_op = gap_box.operator("pet.create_gaps", text="Create Gaps", icon='ARROW_LEFTRIGHT')
            gap_box.prop(gap_op, "gap_distance")
        
        layout.separator()
        
        # Workflow Guidance
        workflow_box = layout.box()
        workflow_box.label(text="Workflow Order", icon='SORTALPHA')
        workflow_box.label(text="1. Split model")
        workflow_box.label(text="2. Create gaps (optional, for visual review)")
        workflow_box.label(text="3. Clean edges (smooth cut boundaries)")
        workflow_box.label(text="4. Fill cuts (cap open surfaces)")
        workflow_box.label(text="5. Create R6 joints (uses stored pivots)")
        workflow_box.label(text="6. Export to Roblox")
        
        workflow_box.separator()
        workflow_box.label(text="⚠️ Gaps are workflow-only", icon='ERROR')
        workflow_box.label(text="Pivot points are at actual boundaries")


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


class PET_PT_manual_part_selection(Panel):
    """Manual Part Segmentation panel - click-to-select with intelligent auto-selection"""
    bl_label = "Manual Part Segmentation"
    bl_idname = "PET_PT_manual_part_selection"
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
        
        state = context.scene.pet_manual_part_selection_state
        settings = context.scene.pet_segmentation_settings
        
        # ===== Mode Status =====
        if state.is_active:
            # Manual Part Segmentation is ACTIVE
            status_box = layout.box()
            status_box.label(text="Manual Part Segmentation ACTIVE", icon='PLAY')
            
            # Get part list and completed parts
            part_list = obj.get("pet_manual_part_list", [])
            completed_parts = list(obj.get("pet_manual_completed_parts", []))
            
            # Progress indicator
            completed_count = len(completed_parts)
            total_count = len(part_list)
            progress_text = f"Progress: {completed_count} of {total_count} parts completed"
            status_box.label(text=progress_text, icon='TIME')
            
            layout.separator()
            
            # ===== Part List with Status =====
            parts_box = layout.box()
            parts_box.label(text="Parts to Assign:", icon='GROUP_VERTEX')
            
            for part_name in part_list:
                row = parts_box.row(align=True)
                
                # Status indicator
                if part_name in completed_parts:
                    row.label(text="", icon='CHECKMARK')
                elif part_name == state.current_part:
                    row.label(text="", icon='FORWARD')
                else:
                    row.label(text="", icon='RADIOBUT_OFF')
                
                # Part name button
                display_name = get_part_display_name(part_name)
                
                if part_name == state.current_part:
                    # Current part - highlighted
                    row.alert = True
                    op = row.operator("pet.select_part_to_assign", text=display_name, icon='RESTRICT_SELECT_OFF')
                    op.part_name = part_name
                    row.alert = False
                elif part_name in completed_parts:
                    # Completed part - can edit
                    op = row.operator("pet.edit_saved_part", text=display_name, icon='GREASEPENCIL')
                    op.part_name = part_name
                else:
                    # Not started
                    op = row.operator("pet.select_part_to_assign", text=display_name)
                    op.part_name = part_name
            
            layout.separator()
            
            # ===== Current Part Actions =====
            if state.current_part:
                current_box = layout.box()
                current_box.label(text=f"Currently Assigning: {get_part_display_name(state.current_part)}", icon='RESTRICT_SELECT_OFF')
                
                # Primary: auto-grow from current selection using intelligent logic
                click_row = current_box.row()
                click_row.scale_y = 1.5
                auto_op = click_row.operator(
                    "pet.auto_grow_current_selection",
                    text=f"Click to Select {get_part_display_name(state.current_part)}",
                    icon='EYEDROPPER',
                )
                auto_op.part_type = state.current_part
                
                # Secondary: use current selection as-is for this part
                as_is_row = current_box.row()
                as_is_row.scale_y = 1.1
                as_is_row.operator(
                    "pet.save_part_selection",
                    text=f"Use Current Selection as {get_part_display_name(state.current_part)}",
                    icon='CHECKMARK',
                )
                
                # Selection info
                if state.current_selection_vertex_count > 0:
                    current_box.label(text=f"Selected: {state.current_selection_vertex_count:,} vertices", icon='VERTEXSEL')
                
                current_box.separator()
                
                # Selection editing tools
                current_box.label(text="Adjust Selection:", icon='MODIFIER')
                
                edit_row = current_box.row(align=True)
                # Add Grow - button first (weakest)
                edit_row.operator("pet.grow_selection_plane_aware", text="Grow -")
                # Grow button (medium strength)
                edit_row.operator("pet.grow_selection_boundary_aware", text="Grow")
                # Grow + button (strongest)
                edit_row.operator("pet.grow_selection", text="Grow +")
                edit_row.operator("pet.shrink_selection", text="Shrink -")
                
                edit_row2 = current_box.row(align=True)
                edit_row2.operator("pet.smooth_selection_boundary", text="Smooth Boundary")
                edit_row2.operator("pet.fill_gaps_selection", text="Fill Gaps")
                
                current_box.separator()
                
                # Preview and Save buttons
                action_row = current_box.row(align=True)
                action_row.operator("pet.preview_current_selection", text="Preview", icon='HIDE_OFF')
                
                save_row = current_box.row()
                save_row.scale_y = 1.3
                save_row.operator("pet.save_part_selection", text="Save Part", icon='CHECKMARK')
            
            layout.separator()
            
            # ===== Body Assignment =====
            body_box = layout.box()
            body_box.label(text="Body Assignment", icon='MESH_CUBE')
            body_box.operator("pet.assign_body_remaining", text="Assign Remaining to Body", icon='BRUSH_DATA')
            
            layout.separator()
            
            # ===== Segment & Cut Section =====
            # Only show when all parts are completed
            all_parts_completed = len(completed_parts) >= len(part_list) if part_list else False
            
            if all_parts_completed:
                segment_cut_box = layout.box()
                segment_cut_box.label(text="Segment & Cut", icon='SCULPTMODE_HLT')
                segment_cut_box.label(text="Find edge loops and mark cuts for each part", icon='INFO')
                segment_cut_box.label(text="After marking all cuts, click 'Apply Cuts' to create vertex groups", icon='INFO')
                
                segment_cut_box.separator()
                
                # Check which segments have been marked
                marked_segments = obj.get("pet_marked_segments", [])
                
                # Show status for each part
                status_col = segment_cut_box.column(align=True)
                for part_name in part_list:
                    if part_name == 'body':
                        continue  # Skip body - it's the remaining mesh
                    
                    row = status_col.row(align=True)
                    display_name = get_part_display_name(part_name)
                    
                    # Check if this part has marked cuts
                    has_cuts = part_name in marked_segments
                    
                    if has_cuts:
                        row.label(text="", icon='CHECKMARK')
                        row.label(text=f"{display_name}: Marked")
                        # Button to select marked edges
                        select_op = row.operator("pet.select_segment_edges", text="", icon='RESTRICT_SELECT_OFF')
                        select_op.segment_name = part_name
                    else:
                        row.label(text="", icon='RADIOBUT_OFF')
                        row.label(text=f"{display_name}: Not marked")
                    
                    # Find edge loop button
                    find_row = status_col.row(align=True)
                    find_row.scale_y = 1.1
                    find_op = find_row.operator("pet.find_edge_loop_for_part", text=f"Find Edge Loop for {display_name}")
                    find_op.part_type = part_name
                    find_op.use_selected_as_seed = True
                    
                    # Mark as cut button (only enabled if in Edit mode with edges selected)
                    if context.mode == 'EDIT_MESH':
                        mark_row = status_col.row(align=True)
                        mark_op = mark_row.operator("pet.mark_segment_cut", text=f"Mark Selected Edges as {display_name}")
                        mark_op.segment_name = part_name
                    else:
                        mark_row = status_col.row(align=True)
                        mark_row.enabled = False
                        mark_row.label(text="Switch to Edit Mode to mark edges", icon='INFO')
                    
                    status_col.separator()
                
                segment_cut_box.separator()
                
                # Actions
                action_row = segment_cut_box.row(align=True)
                action_row.scale_y = 1.2
                
                # Preview cuts
                action_row.operator("pet.preview_segment_cuts", text="Preview Cuts", icon='HIDE_OFF')
                
                # Clear all cuts
                action_row.operator("pet.clear_segment_cuts", text="Clear All", icon='X')
                
                segment_cut_box.separator()
                
                # Apply cuts button (main action)
                apply_row = segment_cut_box.row()
                apply_row.scale_y = 1.5
                apply_op = apply_row.operator("pet.apply_segment_cuts", text="Apply Cuts & Create Vertex Groups", icon='CHECKMARK')
                apply_op.keep_markings = False
                
                if not marked_segments:
                    segment_cut_box.label(text="⚠ No cuts marked yet. Find edge loops and mark them first.", icon='ERROR')
                
                layout.separator()
            
            # ===== Preview All Parts =====
            preview_box = layout.box()
            preview_box.label(text="Preview & Review", icon='HIDE_OFF')
            preview_box.operator("pet.preview_all_parts", text="Preview All Parts", icon='COLOR')
            
            layout.separator()
            
            # ===== Finish / Cancel =====
            finish_box = layout.box()
            finish_box.label(text="Complete Segmentation", icon='CHECKMARK')
            
            finish_row = finish_box.row()
            finish_row.scale_y = 1.5
            finish_row.operator("pet.finish_part_selection", text="Finish & Create Vertex Groups", icon='CHECKMARK')
            
            cancel_row = finish_box.row()
            cancel_row.operator("pet.cancel_part_selection", text="Cancel", icon='X')
            
            layout.separator()
            
            # ===== Add Custom Part =====
            custom_box = layout.box()
            custom_box.label(text="Custom Parts", icon='ADD')
            custom_box.operator("pet.add_custom_part", text="Add Custom Part", icon='ADD')
            
        else:
            # Manual Part Segmentation is NOT active
            intro_box = layout.box()
            intro_box.label(text="Manual Part Segmentation", icon='BRUSH_DATA')
            intro_box.label(text="Click-to-select with intelligent auto-selection")
            intro_box.label(text="")
            intro_box.label(text="Workflow:")
            intro_box.label(text="1. Click 'Start' to begin")
            intro_box.label(text="2. Select a part from the list")
            intro_box.label(text="3. Click on model to auto-select")
            intro_box.label(text="4. Adjust selection if needed")
            intro_box.label(text="5. Save and move to next part")
            intro_box.label(text="6. Finish when all parts done")
            
            layout.separator()
            
            # Pet type selector
            layout.label(text="Pet Type:")
            row = layout.row()
            row.prop(settings, "pet_type", expand=True)
            
            layout.separator()
            
            # Start button
            start_row = layout.row()
            start_row.scale_y = 1.5
            start_row.operator("pet.start_manual_part_selection", text="Start Manual Part Segmentation", icon='PLAY')
            
            layout.separator()
            
            # Info about existing vertex groups
            if obj.vertex_groups:
                info_box = layout.box()
                info_box.label(text="Existing Vertex Groups:", icon='INFO')
                for vg in obj.vertex_groups:
                    info_box.label(text=f"  - {vg.name}")
                info_box.label(text="")
                info_box.label(text="Note: Starting will clear existing groups")
                info_box.label(text="if 'Clear Existing Groups' is enabled")




class PET_PT_symmetry(Panel):
    """Symmetry detection and mirror selection tools"""
    bl_label = "Symmetry Tools"
    bl_idname = "PET_PT_symmetry"
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
        
        settings = context.scene.pet_symmetry_settings
        
        preset_box = layout.box()
        preset_box.label(text="Animal Preset", icon='PRESET')
        preset_box.prop(settings, "animal_preset", text="")
        preset_box.label(text="Provides proportion hints for segmentation", icon='INFO')
        
        layout.separator()
        
        detect_box = layout.box()
        detect_box.label(text="Symmetry Detection", icon='MOD_MIRROR')
        
        axis = obj.get("pet_symmetry_axis")
        score = obj.get("pet_symmetry_score", 0)
        
        if axis:
            detect_box.label(text=f"Detected: {axis}-axis ({score:.0%} confidence)")
        else:
            detect_box.label(text="Not detected yet")
        
        detect_box.operator("pet.detect_symmetry", text="Detect Symmetry Axis", icon='ORIENTATION_GLOBAL')
        
        layout.separator()
        
        mirror_box = layout.box()
        mirror_box.label(text="Mirror Selection", icon='MOD_MIRROR')
        mirror_box.prop(settings, "mirror_threshold")
        
        row = mirror_box.row(align=True)
        row.operator("pet.mirror_selection", text="Mirror Selection", icon='ARROW_LEFTRIGHT')
        
        layout.separator()
        
        half_box = layout.box()
        half_box.label(text="Select Half", icon='SELECT_INTERSECT')
        
        row = half_box.row(align=True)
        op_pos = row.operator("pet.select_half", text="+ Side")
        op_pos.side = 'POSITIVE'
        op_neg = row.operator("pet.select_half", text="- Side")
        op_neg.side = 'NEGATIVE'
        
        layout.separator()
        
        sym_box = layout.box()
        sym_box.label(text="Symmetrize Segments", icon='UV_SYNC_SELECT')
        sym_box.label(text="Copy segment assignments across axis")
        
        row = sym_box.row(align=True)
        op_lr = row.operator("pet.symmetrize_segments", text="L → R")
        op_lr.direction = 'LEFT_TO_RIGHT'
        op_rl = row.operator("pet.symmetrize_segments", text="R → L")
        op_rl.direction = 'RIGHT_TO_LEFT'


classes = [
    # Property Groups (must be registered before panels that use them)
    PET_SegmentationSettings,
    PET_ManualAssignmentState,
    PET_SymmetrySettings,
    PET_ManualPartSelectionState,
    PET_PreOptimizationSettings,
    PET_PostSplitOptimizationSettings,
    PET_SplitSettings,
    # Panels
    PET_PT_main_panel,
    PET_PT_mesh_optimization,
    PET_PT_segmentation,
    PET_PT_symmetry,
    PET_PT_manual_part_selection,
    PET_PT_edge_cut_segmentation,
    PET_PT_split,
    PET_PT_rigging,
    PET_PT_r6_joints,
    PET_PT_standardization,
    PET_PT_export,
    PET_PT_post_split_optimization,
    PET_PT_post_split_cleanup,
    PET_PT_batch_operations,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register Scene properties
    bpy.types.Scene.pet_segmentation_settings = bpy.props.PointerProperty(type=PET_SegmentationSettings)
    bpy.types.Scene.pet_manual_assignment_state = bpy.props.PointerProperty(type=PET_ManualAssignmentState)
    bpy.types.Scene.pet_symmetry_settings = bpy.props.PointerProperty(type=PET_SymmetrySettings)
    bpy.types.Scene.pet_manual_part_selection_state = bpy.props.PointerProperty(type=PET_ManualPartSelectionState)
    bpy.types.Scene.pet_pre_optimization_settings = bpy.props.PointerProperty(type=PET_PreOptimizationSettings)
    bpy.types.Scene.pet_post_split_optimization_settings = bpy.props.PointerProperty(type=PET_PostSplitOptimizationSettings)
    bpy.types.Scene.pet_split_settings = bpy.props.PointerProperty(type=PET_SplitSettings)
    bpy.types.Scene.pet_edge_cleanup_settings = bpy.props.PointerProperty(type=PET_EdgeCleanupSettings)

def unregister():
    # Unregister Scene properties
    if hasattr(bpy.types.Scene, 'pet_segmentation_settings'):
        del bpy.types.Scene.pet_segmentation_settings
    if hasattr(bpy.types.Scene, 'pet_manual_assignment_state'):
        del bpy.types.Scene.pet_manual_assignment_state
    if hasattr(bpy.types.Scene, 'pet_symmetry_settings'):
        del bpy.types.Scene.pet_symmetry_settings
    if hasattr(bpy.types.Scene, 'pet_manual_part_selection_state'):
        del bpy.types.Scene.pet_manual_part_selection_state
    if hasattr(bpy.types.Scene, 'pet_pre_optimization_settings'):
        del bpy.types.Scene.pet_pre_optimization_settings
    if hasattr(bpy.types.Scene, 'pet_post_split_optimization_settings'):
        del bpy.types.Scene.pet_post_split_optimization_settings
    if hasattr(bpy.types.Scene, 'pet_split_settings'):
        del bpy.types.Scene.pet_split_settings
    if hasattr(bpy.types.Scene, 'pet_edge_cleanup_settings'):
        del bpy.types.Scene.pet_edge_cleanup_settings
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
