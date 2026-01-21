"""
Mesh optimization operators
Implements centroid clustering and QEM edge collapse decimation
"""

import bpy
from bpy.types import Operator
from bpy.props import (
    EnumProperty,
    FloatProperty,
    StringProperty,
    BoolProperty,
    IntProperty,
)

from ..utils import algorithms
import math


class PET_OT_optimize_mesh(Operator):
    """Optimize mesh using centroid clustering or QEM edge collapse"""
    bl_idname = "pet.optimize_mesh"
    bl_label = "Optimize Mesh"
    bl_options = {'REGISTER', 'UNDO'}
    
    algorithm: EnumProperty(
        name="Algorithm",
        description="Decimation algorithm to use",
        items=[
            ('AUTO', "Auto", "Automatically select best algorithm based on mesh"),
            ('QEM', "QEM Edge Collapse", "Quadric Error Metric edge collapse"),
            ('CENTROID', "Centroid Clustering", "Centroid clustering decimation"),
        ],
        default='AUTO'
    )
    
    reduction: FloatProperty(
        name="Reduction",
        description="Target face reduction ratio (0.0-0.9)",
        min=0.0,
        max=0.9,
        default=0.6,
        subtype='PERCENTAGE',
        precision=1
    )
    
    grid_size: FloatProperty(
        name="Grid Size",
        description="Grid cell size for centroid clustering",
        min=0.01,
        max=10.0,
        default=0.3,
        precision=3
    )
    
    preserve_sharp_features: BoolProperty(
        name="Preserve Sharp Features",
        description="Try to keep creases, seams, and outer borders when reducing polygons",
        default=True,
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if not obj.data.polygons:
            self.report({'ERROR'}, "Mesh has no faces")
            return {'CANCELLED'}
        
        # Ensure we're in object mode and have the mesh data
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        mesh = obj.data
        initial_face_count = len(mesh.polygons)
        
        # Select algorithm
        algo = self.algorithm
        if algo == 'AUTO':
            # Auto-select: use centroid for very dense meshes, QEM for others
            if initial_face_count > 10000:
                algo = 'CENTROID'
            else:
                algo = 'QEM'
        
        # Apply decimation
        try:
            if algo == 'CENTROID':
                removed = algorithms.centroid_cluster_decimate(
                    mesh,
                    self.grid_size,
                    self.reduction,
                    preserve_sharp_features=self.preserve_sharp_features,
                )
                algo_name = "Centroid Clustering"
            else:  # QEM
                removed = algorithms.qem_edge_collapse(
                    mesh,
                    self.reduction,
                    preserve_sharp_features=self.preserve_sharp_features,
                )
                algo_name = "QEM Edge Collapse"
            
            final_face_count = len(mesh.polygons)
            reduction_actual = (removed / initial_face_count) * 100 if initial_face_count > 0 else 0
            
            self.report(
                {'INFO'},
                f"{algo_name}: {initial_face_count} → {final_face_count} faces "
                f"({reduction_actual:.1f}% reduction)"
            )
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Optimization failed: {str(e)}")
            return {'CANCELLED'}
    
    def invoke(self, context, event):
        # Set default grid size based on object bounds
        obj = context.active_object
        if obj and obj.type == 'MESH' and obj.data.vertices:
            from mathutils import Vector
            bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            size = max(
                max(v.x for v in bbox) - min(v.x for v in bbox),
                max(v.y for v in bbox) - min(v.y for v in bbox),
                max(v.z for v in bbox) - min(v.z for v in bbox)
            )
            self.grid_size = size * 0.05  # 5% of object size
        
        return self.execute(context)


class PET_OT_lowpoly_prep(Operator):
    """Gently reduce mesh complexity before segmentation/splitting"""
    bl_idname = "pet.lowpoly_prep"
    bl_label = "Low-Poly Prep"
    bl_options = {'REGISTER', 'UNDO'}
    
    mode: EnumProperty(
        name="Mode",
        description="How to apply the low-poly prep step",
        items=[
            ('PREVIEW', "Preview", "Create a low-poly duplicate for comparison"),
            ('APPLY', "Apply Step", "Apply a gentle decimation step to the active mesh"),
        ],
        default='APPLY',
    )
    
    step_reduction: FloatProperty(
        name="Step Reduction",
        description="Gentle face reduction for this step (0.5%-20% for fine control)",
        min=0.005,
        max=0.20,
        default=0.05,
        subtype='PERCENTAGE',
        precision=3,
    )
    
    max_faces: IntProperty(
        name="Target Max Faces",
        description="Optional target face count to stop at (0 = ignore)",
        default=0,
        min=0,
    )
    
    algorithm: EnumProperty(
        name="Algorithm",
        description="Decimation algorithm to use for low-poly prep",
        items=[
            ('AUTO', "Auto", "Automatically select best algorithm based on mesh"),
            ('QEM', "QEM Edge Collapse", "Quadric Error Metric edge collapse"),
            ('CENTROID', "Centroid Clustering", "Centroid clustering decimation"),
        ],
        default='AUTO',
    )
    
    preserve_sharp_features: BoolProperty(
        name="Preserve Sharp Features",
        description="Prefer to keep creases, seams, and outer borders when reducing polygons",
        default=True,
    )
    
    def _get_settings_from_scene(self, context):
        """Read shared low-poly settings from Scene if available."""
        settings = getattr(context.scene, "pet_lowpoly_settings", None)
        if not settings:
            return
        
        # Only overwrite if properties exist (for backwards compatibility)
        if hasattr(settings, "step_reduction"):
            self.step_reduction = settings.step_reduction
        if hasattr(settings, "algorithm"):
            self.algorithm = settings.algorithm
        if hasattr(settings, "preserve_sharp_features"):
            self.preserve_sharp_features = settings.preserve_sharp_features
        if hasattr(settings, "max_faces"):
            self.max_faces = settings.max_faces
    
    def _store_stats(self, obj, initial_faces, final_faces):
        """Store cumulative low-poly prep stats on the object for UI display."""
        if initial_faces <= 0 or final_faces < 0:
            return
        
        # Store initial faces only once
        if "pet_lowpoly_initial_faces" not in obj:
            obj["pet_lowpoly_initial_faces"] = int(initial_faces)
        
        obj["pet_lowpoly_last_faces"] = int(final_faces)
        
        base = int(obj.get("pet_lowpoly_initial_faces", initial_faces))
        if base > 0:
            reduction_ratio = 1.0 - (final_faces / base)
            obj["pet_lowpoly_total_reduction"] = float(max(0.0, min(1.0, reduction_ratio)))
    
    def invoke(self, context, event):
        # Sync from Scene-level settings for a consistent slider UI
        self._get_settings_from_scene(context)
        return self.execute(context)
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if not obj.data.polygons:
            self.report({'ERROR'}, "Mesh has no faces")
            return {'CANCELLED'}
        
        # Ensure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        source_obj = obj
        target_obj = obj
        
        # Duplicate for preview mode so the original stays untouched
        if self.mode == 'PREVIEW':
            bpy.ops.object.duplicate()
            target_obj = context.active_object
            if target_obj is None or target_obj.type != 'MESH':
                self.report({'ERROR'}, "Preview duplication failed")
                return {'CANCELLED'}
            # Give the duplicate a lowpoly-style name
            if not target_obj.name.lower().endswith("_lowpoly"):
                base_name = target_obj.name
                base_name = base_name.replace(".001", "")
                target_obj.name = f"{base_name}_lowpoly"
        
        mesh = target_obj.data
        initial_face_count = len(mesh.polygons)
        
        # Respect optional max_faces target
        if self.max_faces > 0 and initial_face_count <= self.max_faces:
            self.report({'INFO'}, f"Mesh already at or below target face count ({initial_face_count} ≤ {self.max_faces})")
            return {'CANCELLED'}
        
        step = max(0.0, min(0.9, self.step_reduction))
        if step <= 0.0:
            self.report({'ERROR'}, "Step reduction must be greater than 0")
            return {'CANCELLED'}
        
        # Warn if step is too large for large meshes
        if initial_face_count > 100000 and step > 0.10:
            self.report(
                {'WARNING'},
                f"Step reduction {step*100:.1f}% is large for {initial_face_count:,} faces. "
                f"Consider using 'Iterative Optimize' with smaller steps (1-5%) for better control."
            )
        
        # Determine effective algorithm
        # For small reductions (<10%), always use QEM for better control
        # Centroid clustering is too unpredictable for small steps
        algo = self.algorithm
        if algo == 'AUTO':
            if step < 0.10:  # Less than 10% reduction
                algo = 'QEM'  # Use QEM for precise control
            elif initial_face_count > 200_000:
                algo = 'CENTROID'  # Use centroid for large meshes with larger reductions
            else:
                algo = 'QEM'  # Default to QEM for better control
        
        try:
            if algo == 'CENTROID':
                # Derive a gentle grid size based on object bounds and target reduction
                # For small reductions, use much smaller grid cells
                from mathutils import Vector
                bbox = [target_obj.matrix_world @ Vector(corner) for corner in target_obj.bound_box]
                size = max(
                    max(v.x for v in bbox) - min(v.x for v in bbox),
                    max(v.y for v in bbox) - min(v.y for v in bbox),
                    max(v.z for v in bbox) - min(v.z for v in bbox),
                )
                # Scale grid size based on reduction: smaller reduction = smaller grid cells
                # For 1% reduction, use 0.005 * size (very fine)
                # For 20% reduction, use 0.02 * size (moderate)
                reduction_factor = max(0.005, min(0.02, step * 0.1))  # Scale with step size
                grid_size = size * reduction_factor if size > 0 else 0.01
                
                removed = algorithms.centroid_cluster_decimate(
                    mesh,
                    grid_size,
                    step,
                    preserve_sharp_features=self.preserve_sharp_features,
                )
                algo_name = "Centroid Clustering"
            else:
                # For large meshes or small steps, use advanced QEM for better control
                if initial_face_count > 100000 or step < 0.10:
                    # Use advanced QEM with corner preservation for better results
                    settings = getattr(context.scene, "pet_advanced_optimizer_settings", None)
                    if settings:
                        base_corner_weight = getattr(settings, "corner_weight", 50.0)
                        preservation_strength = getattr(settings, "corner_preservation_strength", 1.0)
                        effective_corner_weight = base_corner_weight * preservation_strength
                        
                        removed = algorithms.qem_edge_collapse_advanced(
                            mesh,
                            step,
                            preserve_corners=True,
                            corner_threshold=getattr(settings, "corner_threshold", 2),
                            feature_angle=getattr(settings, "feature_angle", math.radians(30.0)),
                            corner_weight=effective_corner_weight,
                            feature_weight=getattr(settings, "feature_edge_weight", 10.0),
                            time_limit_per_chunk=2.0,  # More time for large meshes
                            max_queue_size=100000,
                            use_lazy_quadrics=True,
                            progress_callback=None
                        )
                        algo_name = "Advanced QEM"
                    else:
                        # Fallback to basic QEM
                        removed = algorithms.qem_edge_collapse(
                            mesh,
                            step,
                            preserve_sharp_features=self.preserve_sharp_features,
                        )
                        algo_name = "QEM Edge Collapse"
                else:
                    removed = algorithms.qem_edge_collapse(
                        mesh,
                        step,
                        preserve_sharp_features=self.preserve_sharp_features,
                    )
                    algo_name = "QEM Edge Collapse"
            
            final_face_count = len(mesh.polygons)
            step_reduction_pct = (removed / initial_face_count) * 100 if initial_face_count > 0 else 0.0
            
            # Update cumulative stats on the original object (even when working on duplicate)
            stats_obj = source_obj if self.mode == 'PREVIEW' else target_obj
            self._store_stats(stats_obj, initial_face_count, final_face_count)
            
            # Optional overall reduction percentage (from original)
            base_faces = int(stats_obj.get("pet_lowpoly_initial_faces", initial_face_count))
            total_pct = 0.0
            if base_faces > 0 and final_face_count > 0:
                total_pct = (1.0 - (final_face_count / base_faces)) * 100.0
            
            msg = (
                f"Low-Poly Prep ({algo_name}): "
                f"{initial_face_count:,} → {final_face_count:,} faces "
                f"({step_reduction_pct:.1f}% this step, {total_pct:.1f}% total). "
                "Use Undo to revert if needed."
            )
            self.report({'INFO'}, msg)
            
            return {'FINISHED'}
        
        except Exception as e:
            self.report({'ERROR'}, f"Low-Poly Prep failed: {str(e)}")
            return {'CANCELLED'}


class PET_OT_iterative_optimize(Operator):
    """Iterative optimization with progress tracking - optimized for large meshes"""
    bl_idname = "pet.iterative_optimize"
    bl_label = "Iterative Optimize"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Properties (loaded from scene settings in invoke())
    step_size: FloatProperty(
        name="Step Size",
        description="Reduction per step (0.005-0.20). Use 1-3% for large meshes (500K+), 5-10% for smaller meshes",
        default=0.05,
        min=0.005,
        max=0.20,
        subtype='PERCENTAGE',
        precision=3
    )
    
    max_iterations: IntProperty(
        name="Max Iterations",
        description="Maximum number of steps",
        default=20,
        min=1,
        max=100
    )
    
    adaptive_step_size: BoolProperty(
        name="Adaptive Step Size",
        description="Auto-adjust step size based on vertex count",
        default=True
    )
    
    def _apply_preset(self, preset_name, settings):
        """Apply preset values to settings"""
        if preset_name == 'CONSERVATIVE':
            settings.feature_angle = math.radians(25.0)  # Convert degrees to radians
            settings.corner_threshold = 2
            settings.corner_preservation_strength = 1.0
            settings.corner_weight = 100.0
            settings.feature_edge_weight = 20.0
            settings.detail_reduction_ratio = 0.3
        elif preset_name == 'BALANCED':
            settings.feature_angle = math.radians(30.0)  # Convert degrees to radians
            settings.corner_threshold = 2
            settings.corner_preservation_strength = 0.8
            settings.corner_weight = 50.0
            settings.feature_edge_weight = 10.0
            settings.detail_reduction_ratio = 0.6
        elif preset_name == 'AGGRESSIVE':
            settings.feature_angle = math.radians(45.0)  # Convert degrees to radians
            settings.corner_threshold = 3
            settings.corner_preservation_strength = 0.5
            settings.corner_weight = 25.0
            settings.feature_edge_weight = 5.0
            settings.detail_reduction_ratio = 0.9
        # CUSTOM: Don't change anything
    
    def invoke(self, context, event):
        """Load settings from scene and auto-adjust for large meshes"""
        # Load from scene settings
        settings = getattr(context.scene, "pet_advanced_optimizer_settings", None)
        
        # Apply preset if not custom
        if settings and settings.preset != 'CUSTOM':
            self._apply_preset(settings.preset, settings)
        
        # Auto-adjust step size based on vertex count (more conservative for large meshes)
        obj = context.active_object
        if obj and obj.type == 'MESH' and self.adaptive_step_size:
            vert_count = len(obj.data.vertices)
            if vert_count > 500000:
                self.step_size = 0.01  # 1% for 500K+ (very conservative)
            elif vert_count > 300000:
                self.step_size = 0.02  # 2% for 300K-500K
            elif vert_count > 100000:
                self.step_size = 0.03  # 3% for 100K-300K
            else:
                self.step_size = 0.05  # 5% for <100K
        
        return self.execute(context)
    
    def execute(self, context):
        """Execute one iteration of optimization"""
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if not obj.data.polygons:
            self.report({'ERROR'}, "Mesh has no faces")
            return {'CANCELLED'}
        
        # Ensure object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        mesh = obj.data
        initial_face_count = len(mesh.polygons)
        
        # Store initial count (only once)
        if "pet_advanced_initial_faces" not in obj:
            obj["pet_advanced_initial_faces"] = initial_face_count
            obj["pet_advanced_iteration_count"] = 0
        
        # Get current iteration
        iteration = obj.get("pet_advanced_iteration_count", 0)
        if iteration >= self.max_iterations:
            self.report({'WARNING'}, f"Reached max iterations ({self.max_iterations})")
            return {'CANCELLED'}
        
        # Setup progress reporting
        wm = context.window_manager
        wm.progress_begin(0, 100)
        
        try:
            # Progress callback
            def progress_callback(progress):
                wm.progress_update(int(progress * 100))
            
            # Select algorithm based on current face count
            settings = getattr(context.scene, "pet_advanced_optimizer_settings", None)
            
            # Determine if we should use centroid or QEM
            # For small steps (<5%), always use QEM for precise control
            # Centroid clustering is too unpredictable for small reductions
            if self.step_size < 0.05:
                # Small steps: Always use QEM for better control
                algo = 'QEM'
            elif initial_face_count > 200000 and self.step_size >= 0.10:
                # Stage 1: Use centroid only for large meshes with larger steps (10%+)
                algo = 'CENTROID'
            else:
                # Stage 2/3: Use optimized QEM for better control
                algo = 'QEM'
            
            # Apply optimization
            if algo == 'CENTROID':
                # Calculate grid size from bounds
                from mathutils import Vector
                bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
                size = max(
                    max(v.x for v in bbox) - min(v.x for v in bbox),
                    max(v.y for v in bbox) - min(v.y for v in bbox),
                    max(v.z for v in bbox) - min(v.z for v in bbox)
                )
                # Scale grid size based on step size for better control
                # Smaller steps need smaller grid cells to avoid over-aggressive clustering
                reduction_factor = max(0.005, min(0.02, self.step_size * 0.1))
                grid_size = size * reduction_factor
                
                removed = algorithms.centroid_cluster_decimate(
                    mesh,
                    grid_size,
                    self.step_size,
                    preserve_sharp_features=True
                )
                algo_name = "Centroid Clustering"
            else:
                # Use advanced QEM
                if settings:
                    # Apply corner_preservation_strength to corner_weight
                    base_corner_weight = getattr(settings, "corner_weight", 50.0)
                    preservation_strength = getattr(settings, "corner_preservation_strength", 1.0)
                    effective_corner_weight = base_corner_weight * preservation_strength
                    
                    removed = algorithms.qem_edge_collapse_advanced(
                        mesh,
                        self.step_size,
                        preserve_corners=True,
                        corner_threshold=getattr(settings, "corner_threshold", 2),
                        # feature_angle is stored in radians (Blender ANGLE property requirement)
                        # No conversion needed - it's already in radians
                        feature_angle=getattr(settings, "feature_angle", math.radians(30.0)),
                        corner_weight=effective_corner_weight,
                        feature_weight=getattr(settings, "feature_edge_weight", 10.0),
                        time_limit_per_chunk=getattr(settings, "time_limit_per_chunk", 1.0),
                        max_queue_size=getattr(settings, "batch_size", 50000) * 2,
                        use_lazy_quadrics=True,
                        progress_callback=progress_callback
                    )
                else:
                    # Fallback to basic QEM if settings not available
                    removed = algorithms.qem_edge_collapse(
                        mesh,
                        self.step_size,
                        preserve_sharp_features=True
                    )
                algo_name = "Advanced QEM"
            
            # Update stats
            final_face_count = len(mesh.polygons)
            obj["pet_advanced_iteration_count"] = iteration + 1
            obj["pet_advanced_last_faces"] = final_face_count
            
            # Calculate total reduction from original
            original_faces = obj.get("pet_advanced_initial_faces", initial_face_count)
            total_reduction = (1.0 - (final_face_count / original_faces)) * 100.0 if original_faces > 0 else 0.0
            step_reduction = (removed / initial_face_count) * 100.0 if initial_face_count > 0 else 0.0
            
            self.report(
                {'INFO'},
                f"Iteration {iteration + 1}: {initial_face_count:,} → {final_face_count:,} faces "
                f"({step_reduction:.1f}% this step, {total_reduction:.1f}% total)"
            )
            
            return {'FINISHED'}
        
        except Exception as e:
            self.report({'ERROR'}, f"Optimization failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}
        
        finally:
            wm.progress_end()


classes = [
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
