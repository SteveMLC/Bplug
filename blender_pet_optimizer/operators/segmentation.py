"""
Body part segmentation operators
Segments meshes into labeled body parts using spatial region detection
"""

import bpy
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty

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
        description="Automatically split mesh into separate objects after segmentation",
        default=True
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if not obj.data.vertices:
            self.report({'ERROR'}, "Mesh has no vertices")
            return {'CANCELLED'}
        
        # Get template for pet type
        template = segmentation_templates.TEMPLATES.get(self.pet_type)
        if not template:
            self.report({'ERROR'}, f"Unknown pet type: {self.pet_type}")
            return {'CANCELLED'}
        
        # Clear existing vertex groups if requested
        if self.clear_existing:
            obj.vertex_groups.clear()
        
        # Ensure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Segment mesh
        try:
            vertex_groups = bmesh_helpers.segment_by_regions(obj, template)
            
            total_vertices = 0
            for part_name, indices in vertex_groups.items():
                total_vertices += len(indices)
            
            self.report(
                {'INFO'},
                f"Segmented into {len(vertex_groups)} parts: {', '.join(vertex_groups.keys())}"
            )
            
            # Update mesh
            obj.data.update()
            
            # Auto-split if requested
            if self.auto_split:
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


classes = [
    PET_OT_segment_model,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
