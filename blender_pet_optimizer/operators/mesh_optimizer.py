"""
Mesh optimization operators using Blender's Decimate modifier.

Provides iterative, controlled mesh reduction with:
- Feature edge detection and protection
- Safe step sizes for large meshes
- Separate workflows for pre-segmentation and post-split optimization
"""

import bpy
from bpy.types import Operator
from bpy.props import (
    EnumProperty,
    FloatProperty,
    BoolProperty,
    IntProperty,
)

from ..utils import algorithms


# =============================================================================
# FEATURE DETECTION OPERATORS
# =============================================================================

class PET_OT_detect_features(Operator):
    """Detect and mark sharp edges for protection during decimation"""
    bl_idname = "pet.detect_features"
    bl_label = "Detect Features"
    bl_options = {'REGISTER', 'UNDO'}
    
    angle_threshold: FloatProperty(
        name="Angle Threshold",
        description="Edges with dihedral angle above this are marked sharp (degrees)",
        default=30.0,
        min=15.0,
        max=60.0,
        subtype='ANGLE'
    )
    
    mark_sharp: BoolProperty(
        name="Mark as Sharp",
        description="Mark detected edges as sharp",
        default=True
    )
    
    mark_seam: BoolProperty(
        name="Mark as Seam",
        description="Also mark as UV seams (stronger protection)",
        default=False
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Ensure object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        marked_count = algorithms.mark_feature_edges_for_protection(
            obj,
            angle_threshold=self.angle_threshold,
            mark_sharp=self.mark_sharp,
            mark_seam=self.mark_seam
        )
        
        # Store the count for UI display
        obj["pet_feature_edges_marked"] = marked_count
        
        # Invalidate feature edges cache (sharp/seam counts changed)
        if "pet_feature_edges_cache" in obj:
            del obj["pet_feature_edges_cache"]
        if "pet_feature_edges_sig" in obj:
            del obj["pet_feature_edges_sig"]
        
        self.report({'INFO'}, f"Marked {marked_count:,} sharp edges for protection")
        return {'FINISHED'}


class PET_OT_clear_feature_marks(Operator):
    """Clear all feature edge marks from mesh"""
    bl_idname = "pet.clear_feature_marks"
    bl_label = "Clear Feature Marks"
    bl_options = {'REGISTER', 'UNDO'}
    
    clear_sharp: BoolProperty(
        name="Clear Sharp",
        description="Clear sharp edge marks",
        default=True
    )
    
    clear_seam: BoolProperty(
        name="Clear Seams",
        description="Clear UV seam marks",
        default=False
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        cleared = algorithms.clear_feature_marks(obj, self.clear_sharp, self.clear_seam)
        
        if "pet_feature_edges_marked" in obj:
            del obj["pet_feature_edges_marked"]
        
        # Invalidate feature edges cache (sharp/seam counts changed)
        if "pet_feature_edges_cache" in obj:
            del obj["pet_feature_edges_cache"]
        if "pet_feature_edges_sig" in obj:
            del obj["pet_feature_edges_sig"]
        
        self.report({'INFO'}, f"Cleared {cleared:,} edge marks")
        return {'FINISHED'}


# =============================================================================
# MESH CLEANING OPERATORS
# =============================================================================

class PET_OT_analyze_mesh(Operator):
    """Analyze mesh for geometry problems (loose verts, degenerate faces, etc.)"""
    bl_idname = "pet.analyze_mesh"
    bl_label = "Analyze Mesh"
    bl_options = {'REGISTER'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        try:
            # Force re-analysis (ignore cache)
            problems = algorithms.analyze_mesh_problems(obj, use_cache=False)
            
            if not problems or not isinstance(problems, dict):
                self.report({'ERROR'}, "Analysis failed - could not get results")
                return {'CANCELLED'}
            
            total = problems.get('total_problems', 0)
            
            if total > 0:
                self.report({'WARNING'}, 
                    f"Found {total:,} issues: "
                    f"{problems.get('loose_verts', 0)} loose verts, "
                    f"{problems.get('loose_edges', 0)} loose edges, "
                    f"{problems.get('degenerate_faces', 0)} degenerate, "
                    f"{problems.get('non_manifold_edges', 0)} non-manifold"
                )
            else:
                self.report({'INFO'}, "No geometry issues detected")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Analysis failed: {str(e)}")
            return {'CANCELLED'}


class PET_OT_clean_mesh(Operator):
    """Clean mesh to prepare for decimation - removes loose geometry and merges close vertices"""
    bl_idname = "pet.clean_mesh"
    bl_label = "Clean Mesh"
    bl_options = {'REGISTER', 'UNDO'}
    
    merge_distance: FloatProperty(
        name="Merge Distance",
        description="Distance below which vertices are merged (in Blender units)",
        default=0.0001,
        min=0.00001,
        max=0.01,
        precision=5,
        step=0.0001
    )
    
    delete_loose: BoolProperty(
        name="Delete Loose",
        description="Remove vertices and edges not connected to faces",
        default=True
    )
    
    dissolve_degenerate: BoolProperty(
        name="Dissolve Degenerate",
        description="Remove zero-area faces and degenerate edges",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        try:
            # Ensure object mode
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception as e:
            self.report({'ERROR'}, f"Could not switch to object mode: {str(e)}")
            return {'CANCELLED'}
        
        try:
            # Run cleaning
            result = algorithms.clean_mesh_for_decimation(
                obj,
                merge_distance=self.merge_distance,
                delete_loose=self.delete_loose,
                dissolve_degenerate=self.dissolve_degenerate,
                fix_non_manifold=self.fix_non_manifold
            )
            
            if not result or not isinstance(result, dict):
                self.report({'ERROR'}, "Cleaning failed: Invalid result returned")
                return {'CANCELLED'}
            
            if not result.get('success', False):
                error_msg = result.get('error', 'Unknown error')
                self.report({'ERROR'}, f"Cleaning failed: {error_msg}")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Cleaning failed: {str(e)}")
            return {'CANCELLED'}
        
        # Build summary message
        changes = []
        if result.get('verts_merged', 0) > 0:
            changes.append(f"merged {result['verts_merged']:,} overlapping verts (within {self.merge_distance:.5f} units)")
        if result.get('loose_verts_removed', 0) > 0:
            changes.append(f"removed {result['loose_verts_removed']:,} loose verts")
        if result.get('loose_edges_removed', 0) > 0:
            changes.append(f"removed {result['loose_edges_removed']:,} loose edges")
        if result.get('degenerate_dissolved', 0) > 0:
            changes.append(f"dissolved {result['degenerate_dissolved']:,} degenerate")
        if result.get('non_manifold_fixed', 0) > 0:
            changes.append(f"fixed {result['non_manifold_fixed']} non-manifold edges")
        if result.get('faces_removed', 0) > 0:
            changes.append(f"removed {result['faces_removed']} duplicate faces")
        
        if changes:
            self.report({'INFO'}, f"Cleaned: {', '.join(changes)}")
        else:
            self.report({'INFO'}, "Mesh already clean - no issues found")
        
        # Store cleaning timestamp for UI
        obj["pet_last_cleaned"] = True
        
        # Invalidate all caches and re-analyze
        if "pet_mesh_analysis_cache" in obj:
            del obj["pet_mesh_analysis_cache"]
        if "pet_mesh_analysis_sig" in obj:
            del obj["pet_mesh_analysis_sig"]
        if "pet_feature_edges_cache" in obj:
            del obj["pet_feature_edges_cache"]
        if "pet_feature_edges_sig" in obj:
            del obj["pet_feature_edges_sig"]
        
        # Re-analyze to show new results (this will cache new results)
        algorithms.analyze_mesh_problems(obj, use_cache=False)
        
        return {'FINISHED'}


# =============================================================================
# PRE-SEGMENTATION DECIMATION OPERATORS
# =============================================================================

class PET_OT_decimate_step(Operator):
    """Apply one step of mesh decimation using Blender's Decimate modifier"""
    bl_idname = "pet.decimate_step"
    bl_label = "Reduce Mesh"
    bl_options = {'REGISTER', 'UNDO'}
    
    reduction_percent: FloatProperty(
        name="Reduction",
        description="Percentage of faces to remove this step (1-20%)",
        default=5.0,
        min=1.0,
        max=20.0,
        subtype='PERCENTAGE'
    )
    
    use_auto_step: BoolProperty(
        name="Auto Step Size",
        description="Automatically calculate safe step size based on mesh complexity",
        default=True
    )
    
    preserve_sharp: BoolProperty(
        name="Preserve Sharp Edges",
        description="Respect sharp edge marks during decimation",
        default=True
    )
    
    preserve_seams: BoolProperty(
        name="Preserve UV Seams", 
        description="Respect UV seam marks during decimation",
        default=True
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if not obj.data.polygons:
            self.report({'ERROR'}, "Mesh has no faces")
            return {'CANCELLED'}
        
        # Ensure object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Store initial stats if first time
        initial_faces = len(obj.data.polygons)
        initial_verts = len(obj.data.vertices)
        algorithms.store_optimization_stats(obj, initial_faces, initial_verts)
        
        # Calculate step ratio
        if self.use_auto_step:
            step_ratio = algorithms.calculate_safe_step_size(initial_verts)
            # Scale by user preference (if they want more/less than auto)
            user_scale = self.reduction_percent / 5.0  # 5% is default
            step_ratio = min(0.20, step_ratio * user_scale)
        else:
            step_ratio = self.reduction_percent / 100.0
        
        # Apply decimation
        result = algorithms.iterative_decimate(
            obj,
            step_ratio=step_ratio,
            preserve_sharp=self.preserve_sharp,
            preserve_seams=self.preserve_seams
        )
        
        if not result['success']:
            self.report({'ERROR'}, f"Decimation failed: {result['error']}")
            return {'CANCELLED'}
        
        # Update stats
        algorithms.update_optimization_stats(obj)
        
        # Get overall progress
        stats = algorithms.get_optimization_stats(obj)
        
        self.report(
            {'INFO'},
            f"Reduced: {result['initial_faces']:,} → {result['final_faces']:,} faces "
            f"(-{result['removed_faces']:,} this step, {stats['face_reduction_percent']:.1f}% total)"
        )
        
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # Auto-set step size based on mesh
        obj = context.active_object
        if obj and obj.type == 'MESH' and self.use_auto_step:
            recommended, _ = algorithms.get_recommended_step_size(obj)
            self.reduction_percent = recommended * 100
        
        return self.execute(context)


class PET_OT_decimate_to_target(Operator):
    """Automatically reduce mesh to target face count"""
    bl_idname = "pet.decimate_to_target"
    bl_label = "Reduce to Target"
    bl_options = {'REGISTER', 'UNDO'}
    
    target_faces: IntProperty(
        name="Target Faces",
        description="Target number of faces",
        default=50000,
        min=100,
        max=10000000
    )
    
    preserve_sharp: BoolProperty(
        name="Preserve Sharp Edges",
        description="Respect sharp edge marks",
        default=True
    )
    
    max_iterations: IntProperty(
        name="Max Iterations",
        description="Maximum reduction steps",
        default=50,
        min=1,
        max=200
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        initial_faces = len(obj.data.polygons)
        
        if self.target_faces >= initial_faces:
            self.report({'INFO'}, f"Mesh already at or below target ({initial_faces:,} faces)")
            return {'CANCELLED'}
        
        # Store initial stats
        algorithms.store_optimization_stats(obj, initial_faces, len(obj.data.vertices))
        
        # Progress tracking
        wm = context.window_manager
        wm.progress_begin(0, 100)
        
        def progress_callback(progress, status):
            wm.progress_update(int(progress * 100))
        
        try:
            result = algorithms.decimate_to_target(
                obj,
                target_faces=self.target_faces,
                max_iterations=self.max_iterations,
                preserve_sharp=self.preserve_sharp,
                progress_callback=progress_callback
            )
        finally:
            wm.progress_end()
        
        if not result['success']:
            self.report({'ERROR'}, f"Failed: {result['error']}")
            return {'CANCELLED'}
        
        # Update stats
        obj["pet_opt_step_count"] = result['iterations']
        
        reduction_pct = (1.0 - result['final_faces'] / result['initial_faces']) * 100
        
        self.report(
            {'INFO'},
            f"Reduced: {result['initial_faces']:,} → {result['final_faces']:,} faces "
            f"({reduction_pct:.1f}% reduction in {result['iterations']} steps)"
        )
        
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # Set default target based on current mesh
        obj = context.active_object
        if obj and obj.type == 'MESH':
            current_faces = len(obj.data.polygons)
            # Default to 25% of current
            self.target_faces = max(1000, int(current_faces * 0.25))
        
        return context.window_manager.invoke_props_dialog(self)


class PET_OT_reset_optimization(Operator):
    """Reset optimization stats and clear feature marks"""
    bl_idname = "pet.reset_optimization"
    bl_label = "Reset Optimization"
    bl_options = {'REGISTER', 'UNDO'}
    
    clear_stats: BoolProperty(
        name="Clear Stats",
        description="Clear optimization tracking statistics",
        default=True
    )
    
    clear_marks: BoolProperty(
        name="Clear Edge Marks",
        description="Clear sharp edge marks",
        default=False
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if self.clear_stats:
            algorithms.reset_optimization_stats(obj)
        
        if self.clear_marks:
            algorithms.clear_feature_marks(obj, clear_sharp=True, clear_seam=False)
        
        self.report({'INFO'}, "Optimization reset complete")
        return {'FINISHED'}


# =============================================================================
# POST-SPLIT PART OPTIMIZATION OPERATORS
# =============================================================================

class PET_OT_optimize_part(Operator):
    """Optimize a split mesh part while preserving boundaries"""
    bl_idname = "pet.optimize_part"
    bl_label = "Optimize Part"
    bl_options = {'REGISTER', 'UNDO'}
    
    reduction_percent: FloatProperty(
        name="Reduction",
        description="Percentage of faces to remove (1-20%)",
        default=5.0,
        min=1.0,
        max=20.0,
        subtype='PERCENTAGE'
    )
    
    preserve_boundaries: BoolProperty(
        name="Preserve Boundaries",
        description="Protect cut boundary edges from decimation",
        default=True
    )
    
    preserve_pivots: BoolProperty(
        name="Preserve Pivots",
        description="Avoid decimating near pivot points",
        default=True
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        step_ratio = self.reduction_percent / 100.0
        
        result = algorithms.optimize_split_part(
            obj,
            step_ratio=step_ratio,
            preserve_boundaries=self.preserve_boundaries,
            preserve_pivots=self.preserve_pivots
        )
        
        if not result['success']:
            self.report({'ERROR'}, f"Optimization failed: {result['error']}")
            return {'CANCELLED'}
        
        self.report(
            {'INFO'},
            f"Part optimized: {result['initial_faces']:,} → {result['final_faces']:,} faces "
            f"({result['boundaries_protected']} boundary edges protected)"
        )
        
        return {'FINISHED'}


class PET_OT_optimize_selected_parts(Operator):
    """Optimize all selected split parts"""
    bl_idname = "pet.optimize_selected_parts"
    bl_label = "Optimize Selected Parts"
    bl_options = {'REGISTER', 'UNDO'}
    
    reduction_percent: FloatProperty(
        name="Reduction",
        description="Percentage of faces to remove per part (1-20%)",
        default=5.0,
        min=1.0,
        max=20.0,
        subtype='PERCENTAGE'
    )
    
    preserve_boundaries: BoolProperty(
        name="Preserve Boundaries",
        description="Protect cut boundary edges",
        default=True
    )
    
    def execute(self, context):
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_meshes:
            self.report({'ERROR'}, "Please select mesh objects")
            return {'CANCELLED'}
        
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        step_ratio = self.reduction_percent / 100.0
        total_initial = 0
        total_final = 0
        parts_optimized = 0
        
        for obj in selected_meshes:
            # Make object active for modifier application
            context.view_layer.objects.active = obj
            
            result = algorithms.optimize_split_part(
                obj,
                step_ratio=step_ratio,
                preserve_boundaries=self.preserve_boundaries
            )
            
            if result['success']:
                total_initial += result['initial_faces']
                total_final += result['final_faces']
                parts_optimized += 1
        
        removed = total_initial - total_final
        
        self.report(
            {'INFO'},
            f"Optimized {parts_optimized} parts: {total_initial:,} → {total_final:,} faces "
            f"(-{removed:,} total)"
        )
        
        return {'FINISHED'}


class PET_OT_protect_boundaries(Operator):
    """Mark boundary edges on split parts for protection"""
    bl_idname = "pet.protect_boundaries"
    bl_label = "Protect Boundaries"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        selected_meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_meshes:
            self.report({'ERROR'}, "Please select mesh objects")
            return {'CANCELLED'}
        
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        total_marked = 0
        
        for obj in selected_meshes:
            marked = algorithms.protect_boundary_edges(obj)
            total_marked += marked
            obj["pet_boundary_edges_protected"] = marked
        
        self.report({'INFO'}, f"Protected {total_marked:,} boundary edges on {len(selected_meshes)} parts")
        return {'FINISHED'}


# =============================================================================
# LEGACY OPERATORS (kept for compatibility)
# =============================================================================

class PET_OT_optimize_mesh(Operator):
    """Legacy: Optimize mesh (redirects to new decimate_step)"""
    bl_idname = "pet.optimize_mesh"
    bl_label = "Optimize Mesh (Legacy)"
    bl_options = {'REGISTER', 'UNDO'}
    
    algorithm: EnumProperty(
        name="Algorithm",
        description="Decimation algorithm (legacy - now uses Blender Decimate)",
        items=[
            ('AUTO', "Auto", "Automatically select (uses Blender Decimate)"),
            ('QEM', "QEM Edge Collapse", "Uses Blender Decimate"),
            ('CENTROID', "Centroid Clustering", "Uses Blender Decimate"),
        ],
        default='AUTO'
    )
    
    reduction: FloatProperty(
        name="Reduction",
        description="Target face reduction ratio",
        min=0.0,
        max=0.9,
        default=0.5,
        subtype='PERCENTAGE'
    )
    
    preserve_sharp_features: BoolProperty(
        name="Preserve Sharp Features",
        description="Keep sharp edges during reduction",
        default=True
    )
    
    def execute(self, context):
        # Redirect to new operator with converted parameters
        bpy.ops.pet.decimate_step(
            reduction_percent=self.reduction * 100,
            preserve_sharp=self.preserve_sharp_features
        )
        return {'FINISHED'}


class PET_OT_lowpoly_prep(Operator):
    """Legacy: Low-poly prep (redirects to decimate_step)"""
    bl_idname = "pet.lowpoly_prep"
    bl_label = "Low-Poly Prep"
    bl_options = {'REGISTER', 'UNDO'}
    
    mode: EnumProperty(
        name="Mode",
        items=[
            ('PREVIEW', "Preview", "Preview reduction (creates duplicate)"),
            ('APPLY', "Apply Step", "Apply reduction step"),
        ],
        default='APPLY'
    )
    
    step_reduction: FloatProperty(
        name="Step Reduction",
        default=0.05,
        min=0.005,
        max=0.20,
        subtype='PERCENTAGE'
    )
    
    preserve_sharp_features: BoolProperty(
        name="Preserve Sharp Features",
        default=True
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        if self.mode == 'PREVIEW':
            # Create duplicate for preview
            bpy.ops.object.duplicate()
            obj = context.active_object
            if obj.name and not obj.name.endswith("_lowpoly"):
                base_name = obj.name.replace(".001", "")
                obj.name = f"{base_name}_lowpoly"
        
        # Apply decimation
        bpy.ops.pet.decimate_step(
            reduction_percent=self.step_reduction * 100,
            preserve_sharp=self.preserve_sharp_features
        )
        
        return {'FINISHED'}


class PET_OT_iterative_optimize(Operator):
    """Legacy: Iterative optimize (redirects to decimate_step)"""
    bl_idname = "pet.iterative_optimize"
    bl_label = "Iterative Optimize"
    bl_options = {'REGISTER', 'UNDO'}
    
    step_size: FloatProperty(
        name="Step Size",
        default=0.05,
        min=0.005,
        max=0.20,
        subtype='PERCENTAGE'
    )
    
    def execute(self, context):
        bpy.ops.pet.decimate_step(
            reduction_percent=self.step_size * 100,
            use_auto_step=True
        )
        return {'FINISHED'}


# =============================================================================
# REGISTRATION
# =============================================================================

classes = [
    # New operators
    PET_OT_detect_features,
    PET_OT_clear_feature_marks,
    PET_OT_analyze_mesh,
    PET_OT_clean_mesh,
    PET_OT_decimate_step,
    PET_OT_decimate_to_target,
    PET_OT_reset_optimization,
    PET_OT_optimize_part,
    PET_OT_optimize_selected_parts,
    PET_OT_protect_boundaries,
    # Legacy operators (for compatibility)
    PET_OT_optimize_mesh,
    PET_OT_lowpoly_prep,
    PET_OT_iterative_optimize,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
