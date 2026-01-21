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
        description="Gentle face reduction for this step (0.0-0.5)",
        min=0.0,
        max=0.5,
        default=0.1,
        subtype='PERCENTAGE',
        precision=2,
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
        
        # Determine effective algorithm
        algo = self.algorithm
        if algo == 'AUTO':
            if initial_face_count > 100_000:
                algo = 'CENTROID'
            else:
                algo = 'QEM'
        
        try:
            if algo == 'CENTROID':
                # Derive a gentle grid size based on object bounds if possible
                from mathutils import Vector
                bbox = [target_obj.matrix_world @ Vector(corner) for corner in target_obj.bound_box]
                size = max(
                    max(v.x for v in bbox) - min(v.x for v in bbox),
                    max(v.y for v in bbox) - min(v.y for v in bbox),
                    max(v.z for v in bbox) - min(v.z for v in bbox),
                )
                grid_size = size * 0.03 if size > 0 else 0.1
                
                removed = algorithms.centroid_cluster_decimate(
                    mesh,
                    grid_size,
                    step,
                    preserve_sharp_features=self.preserve_sharp_features,
                )
                algo_name = "Centroid Clustering"
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


classes = [
    PET_OT_optimize_mesh,
    PET_OT_lowpoly_prep,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
