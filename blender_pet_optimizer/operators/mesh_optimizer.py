"""
Mesh optimization operators
Implements centroid clustering and QEM edge collapse decimation
"""

import bpy
from bpy.types import Operator
from bpy.props import EnumProperty, FloatProperty, StringProperty

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
                    self.reduction
                )
                algo_name = "Centroid Clustering"
            else:  # QEM
                removed = algorithms.qem_edge_collapse(
                    mesh,
                    self.reduction
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


classes = [
    PET_OT_optimize_mesh,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
