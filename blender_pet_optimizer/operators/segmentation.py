"""
Body part segmentation operators
Segments meshes into labeled body parts using spatial region detection
"""

import bpy
import time
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty, FloatProperty, StringProperty

from ..utils import segmentation_templates
from ..utils import bmesh_helpers


class PET_OT_segment_model(Operator):
    """Segment mesh into body parts using spatial regions"""
    bl_idname = "pet.segment_model"
    bl_label = "Segment Model"
    bl_options = {'REGISTER', 'UNDO'}
    
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
    
    clear_existing: BoolProperty(
        name="Clear Existing Groups",
        description="Clear existing vertex groups before segmenting",
        default=True
    )
    
    auto_split: BoolProperty(
        name="Auto Split",
        description="Automatically split mesh into separate objects after segmentation (Recommended: OFF - preview first, then split manually)",
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
    
    use_geometry_based: BoolProperty(
        name="Use Geometry-Based Detection",
        description="Use geometry-relative positioning (enhancement mode). Detects body parts by actual mesh shape, not bounding box percentages. Use after preview to refine results.",
        default=False
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if not obj.data.vertices:
            self.report({'ERROR'}, "Mesh has no vertices")
            return {'CANCELLED'}
        
        # Get settings from scene properties (fallback to operator properties for backwards compatibility)
        settings = context.scene.pet_segmentation_settings
        pet_type = settings.pet_type if hasattr(settings, 'pet_type') else self.pet_type
        use_geometry_based = settings.use_geometry_based if hasattr(settings, 'use_geometry_based') else self.use_geometry_based
        use_connectivity_refinement = settings.use_connectivity_refinement if hasattr(settings, 'use_connectivity_refinement') else self.use_connectivity_refinement
        auto_detect_protrusions = settings.auto_detect_protrusions if hasattr(settings, 'auto_detect_protrusions') else self.auto_detect_protrusions
        sensitivity = settings.sensitivity if hasattr(settings, 'sensitivity') else self.sensitivity
        clear_existing = settings.clear_existing if hasattr(settings, 'clear_existing') else self.clear_existing
        auto_split = settings.auto_split if hasattr(settings, 'auto_split') else self.auto_split
        use_fast_mode = settings.use_fast_mode if hasattr(settings, 'use_fast_mode') else False
        invert_forward_axis = settings.invert_forward_axis if hasattr(settings, 'invert_forward_axis') else False
        
        # Get template for pet type
        template = segmentation_templates.TEMPLATES.get(pet_type)
        if not template:
            self.report({'ERROR'}, f"Unknown pet type: {pet_type}")
            return {'CANCELLED'}
        
        # Analyze template match and warn if needed
        from ..utils import segmentation_refinement
        from ..utils import bmesh_helpers
        match_analysis = segmentation_refinement.analyze_template_match(
            obj, template, bmesh_helpers.get_mesh_bounds
        )
        
        if match_analysis['confidence'] < 0.7 and match_analysis['warnings']:
            self.report(
                {'WARNING'},
                f"Template match: {match_analysis['confidence']:.0%} confidence. "
                f"Warnings: {'; '.join(match_analysis['warnings'][:2])}"
            )
        
        # Clear existing vertex groups if requested
        if clear_existing:
            obj.vertex_groups.clear()
        
        # Ensure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Segment mesh with timing and guaranteed fallback
        try:
            start_time = time.time()
            
            # In fast mode, disable expensive operations
            effective_connectivity = use_connectivity_refinement and not use_fast_mode
            effective_auto_detect = auto_detect_protrusions and not use_fast_mode
            
            # Robust segmentation chain (never fail completely)
            vertex_groups, method_used = bmesh_helpers.segment_by_regions_robust(
                obj,
                template,
                use_connectivity_refinement=effective_connectivity,
                sensitivity=sensitivity,
                auto_detect_protrusions=effective_auto_detect,
                use_geometry_based=use_geometry_based,
                template_type=pet_type,
                use_fast_mode=use_fast_mode,
                timeout=None,  # adaptive in helper
                invert_forward_axis=invert_forward_axis,  # user override only
                auto_orientation=True,
            )
            
            # Check elapsed time
            elapsed = time.time() - start_time
            if elapsed > 30.0:
                self.report({'WARNING'}, 
                    f"Segmentation took {elapsed:.1f} seconds. "
                    f"Consider enabling Fast Mode for better performance on large meshes.")
                print(f"WARNING: Segmentation took {elapsed:.1f}s (consider Fast Mode)")
            
            processing_time = time.time() - start_time
            
            total_vertices = 0
            for part_name, indices in vertex_groups.items():
                total_vertices += len(indices)
            
            # Store results for UI display
            self.report(
                {'INFO'},
                f"Segmented into {len(vertex_groups)} parts ({method_used}): {', '.join(vertex_groups.keys())}"
            )
            
            # Store metrics on object for UI display
            obj["pet_segmentation_parts"] = len(vertex_groups)
            obj["pet_segmentation_vertices"] = total_vertices
            obj["pet_segmentation_time"] = processing_time
            obj["pet_segmentation_method"] = method_used
            obj["pet_segmentation_timestamp"] = time.time()
            
            # Update mesh
            obj.data.update()
            
            # Auto-split if requested
            if auto_split:
                # Call split operator via operator ID
                result = bpy.ops.pet.split_by_vertex_groups(
                    create_pivots=True,
                    keep_original=True,
                    verify_data=True
                )
                if result != {'FINISHED'}:
                    self.report({'WARNING'}, "Segmentation completed, but auto-split failed. Use manual split button.")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Segmentation failed: {str(e)}")
            return {'CANCELLED'}


class PET_OT_preview_segmentation(Operator):
    """Preview segmentation without applying (shows vertex groups in Edit mode)"""
    bl_idname = "pet.preview_segmentation"
    bl_label = "Preview Segmentation"
    bl_options = {'REGISTER', 'UNDO'}
    
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
    
    use_connectivity_refinement: BoolProperty(
        name="Use Connectivity Refinement",
        description="Industry-standard connectivity-based boundary refinement",
        default=True
    )
    
    auto_detect_protrusions: BoolProperty(
        name="Auto-Detect Protrusions",
        description="Automatically detect legs, wings, and tails",
        default=True
    )
    
    sensitivity: FloatProperty(
        name="Boundary Sensitivity",
        description="Sensitivity for boundary detection",
        default=0.5,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )
    
    use_geometry_based: BoolProperty(
        name="Use Geometry-Based Detection",
        description="Use geometry-relative positioning (enhancement mode). Use after preview to refine results.",
        default=False
    )
    
    clear_existing: BoolProperty(
        name="Clear Existing Groups",
        description="Clear existing vertex groups before previewing",
        default=True
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Get settings from scene properties (fallback to operator properties for backwards compatibility)
        settings = context.scene.pet_segmentation_settings
        pet_type = settings.pet_type if hasattr(settings, 'pet_type') else self.pet_type
        use_geometry_based = settings.use_geometry_based if hasattr(settings, 'use_geometry_based') else self.use_geometry_based
        use_connectivity_refinement = settings.use_connectivity_refinement if hasattr(settings, 'use_connectivity_refinement') else self.use_connectivity_refinement
        auto_detect_protrusions = settings.auto_detect_protrusions if hasattr(settings, 'auto_detect_protrusions') else self.auto_detect_protrusions
        sensitivity = settings.sensitivity if hasattr(settings, 'sensitivity') else self.sensitivity
        clear_existing = settings.clear_existing if hasattr(settings, 'clear_existing') else self.clear_existing
        use_fast_mode = settings.use_fast_mode if hasattr(settings, 'use_fast_mode') else False
        invert_forward_axis = settings.invert_forward_axis if hasattr(settings, 'invert_forward_axis') else False
        
        # Perform segmentation
        template = segmentation_templates.TEMPLATES.get(pet_type)
        if not template:
            self.report({'ERROR'}, f"Unknown pet type: {pet_type}")
            return {'CANCELLED'}
        
        # Validate mesh before processing
        mesh = obj.data
        vertex_count = len(mesh.vertices)
        
        if vertex_count == 0:
            self.report({'ERROR'}, "Mesh has no vertices")
            return {'CANCELLED'}
        
        # Hard limit: reject meshes that are too large to process
        if vertex_count > 500000:
            self.report({'ERROR'}, 
                f"Mesh too large ({vertex_count:,} vertices). "
                f"Maximum supported: 500,000 vertices. "
                f"Please reduce mesh complexity (decimate) or disable Geometry-Based detection.")
            return {'CANCELLED'}
        
        # Auto-enable fast mode for large meshes in preview
        if vertex_count > 100000:
            use_fast_mode = True  # Auto-enable for large meshes
            if not settings.use_fast_mode:
                print(f"INFO: Large mesh ({vertex_count:,} vertices) - auto-enabling fast mode for preview")
        
        # Check mesh complexity (edges per vertex ratio)
        # Very dense meshes (high edge count) are slower to process
        try:
            edge_count = len(mesh.edges) if hasattr(mesh, 'edges') else 0
            if edge_count > 0:
                complexity_ratio = edge_count / vertex_count
                if complexity_ratio > 3.0:  # Very dense mesh
                    self.report({'WARNING'}, 
                        f"Very dense mesh detected ({complexity_ratio:.1f} edges per vertex). "
                        f"Consider enabling Fast Mode for better performance.")
        except:
            pass  # Edge count check is optional
        
        # Initialize progress reporting
        wm = context.window_manager
        wm.progress_begin(0, 100)
        
        try:
            wm.progress_update(5)
            
            # Clear existing groups for preview (temporary)
            # We'll restore them if user cancels, but for preview we want fresh results
            if clear_existing:
                obj.vertex_groups.clear()
            
            wm.progress_update(10)
            
            # Perform segmentation with progress updates, timeout check, and guaranteed fallback
            vertex_groups = None
            seg_start_time = time.time()
            preview_timeout = 2.0  # 2 second timeout for preview
            
            # Skip connectivity refinement in preview by default for speed
            effective_connectivity = False  # Preview doesn't use refinement
            effective_auto_detect = False   # Preview doesn't use auto-detect
            
            try:
                wm.progress_update(20)
                
                # Try geometry-based if enabled, but with timeout check
                if use_geometry_based:
                    try:
                        vertex_groups = bmesh_helpers.segment_by_regions(
                            obj, 
                            template,
                            use_connectivity_refinement=effective_connectivity,
                            sensitivity=sensitivity,
                            auto_detect_protrusions=effective_auto_detect,
                            use_geometry_based=True,
                            template_type=pet_type,
                            use_fast_mode=use_fast_mode,
                            invert_forward_axis=invert_forward_axis
                        )
                        
                        # Check if we exceeded timeout
                        seg_elapsed = time.time() - seg_start_time
                        if seg_elapsed > preview_timeout:
                            print(f"INFO: Geometry-based exceeded {preview_timeout}s timeout ({seg_elapsed:.1f}s), using spatial-only fallback")
                            vertex_groups = None  # Force fallback
                    except Exception as e:
                        print(f"INFO: Geometry-based failed ({str(e)}), falling back to spatial-only")
                        vertex_groups = None  # Force fallback
                
                # Fallback to spatial-only if geometry-based failed or timed out
                if not vertex_groups:
                    wm.progress_update(40)
                    print("Using spatial-only mode (fast, reliable)")
                    vertex_groups = bmesh_helpers.segment_by_regions(
                        obj, 
                        template,
                        use_connectivity_refinement=False,  # Never use refinement in preview
                        sensitivity=sensitivity,
                        auto_detect_protrusions=False,  # Never use auto-detect in preview
                        use_geometry_based=False,  # Force spatial-only
                        template_type=pet_type,
                        use_fast_mode=True  # Always fast mode for preview
                    )
                
                wm.progress_update(80)
                
            except Exception as e:
                # Ultimate fallback - try spatial-only one more time
                print(f"WARNING: Segmentation attempt failed ({str(e)}), trying spatial-only fallback...")
                try:
                    vertex_groups = bmesh_helpers.segment_by_regions(
                        obj, 
                        template,
                        use_connectivity_refinement=False,
                        sensitivity=sensitivity,
                        auto_detect_protrusions=False,
                        use_geometry_based=False,
                        template_type=pet_type,
                        use_fast_mode=True
                    )
                except Exception as e2:
                    wm.progress_end()
                    self.report({'ERROR'}, f"Segmentation failed even with fallback: {str(e2)}")
                    import traceback
                    traceback.print_exc()
                    return {'CANCELLED'}
            
            # Final check - should never happen, but just in case
            if not vertex_groups:
                wm.progress_end()
                self.report({'WARNING'}, "No vertex groups created. Check model orientation and template selection.")
                return {'CANCELLED'}
            
            wm.progress_update(85)
            
            # Switch to Weight Paint mode for visual preview (with error handling)
            try:
                if context.mode != 'WEIGHT_PAINT':
                    bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
            except RuntimeError as e:
                wm.progress_end()
                self.report({'WARNING'}, f"Could not switch to Weight Paint mode: {str(e)}. Vertex groups created but not visualized.")
                # Continue anyway - vertex groups are still created
            
            wm.progress_update(90)
            
            # Select the first vertex group to visualize it
            if obj.vertex_groups:
                try:
                    obj.vertex_groups.active_index = 0
                    obj.vertex_groups.active = obj.vertex_groups[0]
                except (IndexError, AttributeError):
                    pass  # If selection fails, continue anyway
            
            wm.progress_update(95)
            
            # Store metrics for UI
            # Calculate total vertices assigned (may have overlaps, so count unique)
            all_assigned_verts = set()
            for indices in vertex_groups.values():
                all_assigned_verts.update(indices)
            total_vertices = len(all_assigned_verts)
            
            obj["pet_segmentation_parts"] = len(vertex_groups)
            obj["pet_segmentation_vertices"] = total_vertices
            obj["pet_segmentation_time"] = 0.0  # Preview doesn't time
            obj["pet_segmentation_timestamp"] = time.time()
            
            wm.progress_update(100)
            wm.progress_end()
            
            method_used = "geometry-based" if use_geometry_based and vertex_groups else "spatial-only"
            self.report(
                {'INFO'}, 
                f"Preview: {len(vertex_groups)} parts detected ({total_vertices:,} vertices) [{method_used}]. "
                f"Adjust settings and preview again to refine, or click 'Segment Model' to finalize."
            )
            
            return {'FINISHED'}
            
        except KeyboardInterrupt:
            wm.progress_end()
            self.report({'WARNING'}, "Preview cancelled by user")
            return {'CANCELLED'}
        except Exception as e:
            wm.progress_end()
            self.report({'ERROR'}, f"Preview failed: {str(e)}")
            import traceback
            print(f"Preview error traceback:\n{traceback.format_exc()}")
            traceback.print_exc()
            return {'CANCELLED'}


class PET_OT_view_vertex_group(Operator):
    """View a specific vertex group in Weight Paint mode"""
    bl_idname = "pet.view_vertex_group"
    bl_label = "View Vertex Group"
    bl_options = {'REGISTER', 'UNDO'}
    
    vertex_group_name: StringProperty(
        name="Vertex Group Name",
        description="Name of vertex group to view"
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Find vertex group
        vg_index = obj.vertex_groups.find(self.vertex_group_name)
        if vg_index == -1:
            self.report({'ERROR'}, f"Vertex group '{self.vertex_group_name}' not found")
            return {'CANCELLED'}
        
        # Switch to Weight Paint mode if not already
        try:
            if context.mode != 'WEIGHT_PAINT':
                bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        except RuntimeError:
            self.report({'WARNING'}, "Could not switch to Weight Paint mode")
            return {'CANCELLED'}
        
        # Set active vertex group
        obj.vertex_groups.active_index = vg_index
        obj.vertex_groups.active = obj.vertex_groups[vg_index]
        
        self.report({'INFO'}, f"Viewing vertex group: {self.vertex_group_name}")
        return {'FINISHED'}


class PET_OT_start_manual_assignment(Operator):
    """Start manual vertex assignment wizard - creates empty vertex groups and switches to Edit mode"""
    bl_idname = "pet.start_manual_assignment"
    bl_label = "Start Manual Assignment"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Get template for current pet type
        settings = context.scene.pet_segmentation_settings
        pet_type = settings.pet_type if hasattr(settings, 'pet_type') else 'quadruped'
        template = segmentation_templates.TEMPLATES.get(pet_type)
        
        if not template:
            self.report({'ERROR'}, f"Unknown pet type: {pet_type}")
            return {'CANCELLED'}
        
        # Clear existing vertex groups if requested
        if settings.clear_existing:
            obj.vertex_groups.clear()
        
        # Order parts: appendages first, body last
        if pet_type == 'biped':
            appendage_parts = ['head', 'arm_l', 'arm_r', 'leg_l', 'leg_r', 'tail']
        elif pet_type == 'flying':
            appendage_parts = ['head', 'leg_front_l', 'leg_front_r', 'leg_back_l', 'leg_back_r', 'wing_l', 'wing_r', 'tail']
        else:  # quadruped
            appendage_parts = ['head', 'leg_front_l', 'leg_front_r', 'leg_back_l', 'leg_back_r', 'tail']
        
        # Filter to parts that exist in template
        part_list = [p for p in appendage_parts if p in template]
        if 'body' in template:
            part_list.append('body')  # Body always last
        
        # Create empty vertex groups for all parts
        for part_name in part_list:
            if part_name not in obj.vertex_groups:
                obj.vertex_groups.new(name=part_name)
        
        # Initialize wizard state
        wizard_state = context.scene.pet_manual_assignment_state
        wizard_state.is_active = True
        wizard_state.current_step = 0
        
        # Store part list (we'll need to serialize this somehow, or use a different approach)
        # For now, we'll store it as a string list in a custom property
        obj["pet_manual_part_list"] = part_list
        obj["pet_manual_part_list_count"] = len(part_list)
        
        # Ensure we're in Edit mode
        if context.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        # Update remaining vertex count
        PET_OT_start_manual_assignment._update_remaining_count(context, obj)
        
        self.report({'INFO'}, f"Manual assignment started: {len(part_list)} parts. Start with '{part_list[0]}'.")
        return {'FINISHED'}
    
    @staticmethod
    def _update_remaining_count(context, obj):
        """Update count of unassigned vertices"""
        mesh = obj.data
        wizard_state = context.scene.pet_manual_assignment_state
        
        # Count vertices not assigned to any group
        unassigned_count = 0
        for vert in mesh.vertices:
            assigned = False
            for group in vert.groups:
                if group.weight > 0.0:
                    assigned = True
                    break
            if not assigned:
                unassigned_count += 1
        
        wizard_state.remaining_vertex_count = unassigned_count


class PET_OT_assign_selected_vertices(Operator):
    """Assign currently selected vertices to the current part in manual assignment wizard"""
    bl_idname = "pet.assign_selected_vertices"
    bl_label = "Assign Selected Vertices"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode to assign vertices")
            return {'CANCELLED'}
        
        wizard_state = context.scene.pet_manual_assignment_state
        if not wizard_state.is_active:
            self.report({'ERROR'}, "Manual assignment wizard is not active")
            return {'CANCELLED'}
        
        # Get current part from wizard state
        part_list = obj.get("pet_manual_part_list", [])
        if not part_list:
            self.report({'ERROR'}, "No part list found. Restart manual assignment.")
            return {'CANCELLED'}
        
        if wizard_state.current_step >= len(part_list):
            self.report({'ERROR'}, "Current step is out of range")
            return {'CANCELLED'}
        
        current_part = part_list[wizard_state.current_step]
        
        # Get selected vertices in Edit mode
        mesh = obj.data
        bpy.ops.object.mode_set(mode='OBJECT')
        selected_vertices = [v.index for v in mesh.vertices if v.select]
        
        if not selected_vertices:
            self.report({'WARNING'}, "No vertices selected")
            bpy.ops.object.mode_set(mode='EDIT')
            return {'CANCELLED'}
        
        # Get or create vertex group for current part
        vg_index = obj.vertex_groups.find(current_part)
        if vg_index == -1:
            vg = obj.vertex_groups.new(name=current_part)
            vg_index = vg.index
        else:
            vg = obj.vertex_groups[vg_index]
        
        # Assign selected vertices to current part (weight 1.0)
        vg.add(selected_vertices, 1.0, 'REPLACE')
        
        # Remove from other vertex groups to avoid overlaps
        for other_vg in obj.vertex_groups:
            if other_vg.index != vg_index:
                other_vg.remove(selected_vertices)
        
        # Switch back to Edit mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Update remaining count
        PET_OT_start_manual_assignment._update_remaining_count(context, obj)
        
        self.report({'INFO'}, f"Assigned {len(selected_vertices)} vertices to '{current_part}'")
        return {'FINISHED'}
        """Update count of unassigned vertices"""
        mesh = obj.data
        wizard_state = context.scene.pet_manual_assignment_state
        
        unassigned_count = 0
        for vert in mesh.vertices:
            assigned = False
            for group in vert.groups:
                if group.weight > 0.0:
                    assigned = True
                    break
            if not assigned:
                unassigned_count += 1
        
        wizard_state.remaining_vertex_count = unassigned_count


class PET_OT_assign_remaining_to_body(Operator):
    """Assign all unassigned vertices to body"""
    bl_idname = "pet.assign_remaining_to_body"
    bl_label = "Assign Remaining to Body"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        wizard_state = context.scene.pet_manual_assignment_state
        if not wizard_state.is_active:
            self.report({'ERROR'}, "Manual assignment wizard is not active")
            return {'CANCELLED'}
        
        # Get body vertex group
        body_vg_index = obj.vertex_groups.find('body')
        if body_vg_index == -1:
            body_vg = obj.vertex_groups.new(name='body')
            body_vg_index = body_vg.index
        else:
            body_vg = obj.vertex_groups[body_vg_index]
        
        # Find all unassigned vertices
        mesh = obj.data
        unassigned_vertices = []
        
        for vert in mesh.vertices:
            assigned = False
            for group in vert.groups:
                if group.group != body_vg_index and group.weight > 0.0:
                    assigned = True
                    break
            if not assigned:
                unassigned_vertices.append(vert.index)
        
        if not unassigned_vertices:
            self.report({'INFO'}, "All vertices are already assigned")
            return {'FINISHED'}
        
        # Assign unassigned vertices to body
        body_vg.add(unassigned_vertices, 1.0, 'REPLACE')
        
        # Update remaining count
        wizard_state.remaining_vertex_count = 0
        
        self.report({'INFO'}, f"Assigned {len(unassigned_vertices)} remaining vertices to body")
        return {'FINISHED'}


class PET_OT_next_manual_part(Operator):
    """Move to next part in manual assignment wizard"""
    bl_idname = "pet.next_manual_part"
    bl_label = "Next Part"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        
        wizard_state = context.scene.pet_manual_assignment_state
        if not wizard_state.is_active:
            return {'CANCELLED'}
        
        part_list = obj.get("pet_manual_part_list", [])
        if not part_list:
            return {'CANCELLED'}
        
        if wizard_state.current_step < len(part_list) - 1:
            wizard_state.current_step += 1
            next_part = part_list[wizard_state.current_step]
            self.report({'INFO'}, f"Now assigning: {next_part}")
        
        return {'FINISHED'}


class PET_OT_previous_manual_part(Operator):
    """Move to previous part in manual assignment wizard"""
    bl_idname = "pet.previous_manual_part"
    bl_label = "Previous Part"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        
        wizard_state = context.scene.pet_manual_assignment_state
        if not wizard_state.is_active:
            return {'CANCELLED'}
        
        if wizard_state.current_step > 0:
            wizard_state.current_step -= 1
            part_list = obj.get("pet_manual_part_list", [])
            if part_list:
                prev_part = part_list[wizard_state.current_step]
                self.report({'INFO'}, f"Now assigning: {prev_part}")
        
        return {'FINISHED'}


class PET_OT_cancel_manual_assignment(Operator):
    """Cancel manual assignment wizard"""
    bl_idname = "pet.cancel_manual_assignment"
    bl_label = "Cancel Manual Assignment"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        wizard_state = context.scene.pet_manual_assignment_state
        if wizard_state.is_active:
            wizard_state.is_active = False
            wizard_state.current_step = 0
            wizard_state.remaining_vertex_count = 0
            
            # Clean up custom properties
            obj = context.active_object
            if obj and "pet_manual_part_list" in obj:
                del obj["pet_manual_part_list"]
            if obj and "pet_manual_part_list_count" in obj:
                del obj["pet_manual_part_list_count"]
            
            self.report({'INFO'}, "Manual assignment cancelled")
        return {'FINISHED'}


class PET_OT_finish_manual_assignment(Operator):
    """Finish manual assignment wizard and show summary"""
    bl_idname = "pet.finish_manual_assignment"
    bl_label = "Finish Manual Assignment"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        wizard_state = context.scene.pet_manual_assignment_state
        if not wizard_state.is_active:
            self.report({'WARNING'}, "Manual assignment wizard is not active")
            return {'CANCELLED'}
        
        # Calculate summary
        mesh = obj.data
        part_list = obj.get("pet_manual_part_list", [])
        summary_parts = []
        
        for part_name in part_list:
            vg_index = obj.vertex_groups.find(part_name)
            if vg_index != -1:
                count = sum(1 for v in mesh.vertices 
                           for g in v.groups 
                           if g.group == vg_index and g.weight > 0.0)
                summary_parts.append(f"{part_name}: {count:,} vertices")
        
        # Exit wizard mode
        wizard_state.is_active = False
        wizard_state.current_step = 0
        wizard_state.remaining_vertex_count = 0
        
        # Clean up custom properties
        if "pet_manual_part_list" in obj:
            del obj["pet_manual_part_list"]
        if "pet_manual_part_list_count" in obj:
            del obj["pet_manual_part_list_count"]
        
        # Switch to Weight Paint mode for review
        if context.mode != 'WEIGHT_PAINT':
            try:
                bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
            except RuntimeError:
                pass  # Continue even if mode switch fails
        
        summary_text = "Manual assignment complete: " + ", ".join(summary_parts)
        self.report({'INFO'}, summary_text)
        
        return {'FINISHED'}


classes = [
    PET_OT_segment_model,
    PET_OT_preview_segmentation,
    PET_OT_view_vertex_group,
    PET_OT_start_manual_assignment,
    PET_OT_assign_selected_vertices,
    PET_OT_assign_remaining_to_body,
    PET_OT_next_manual_part,
    PET_OT_previous_manual_part,
    PET_OT_cancel_manual_assignment,
    PET_OT_finish_manual_assignment,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
