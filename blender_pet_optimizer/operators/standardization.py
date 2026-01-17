"""
Part standardization operators
Normalizes scales, orientations, and attachment points
"""

import bpy
from bpy.types import Operator
from bpy.props import BoolProperty, StringProperty
from mathutils import Vector
from ..config import standards


def get_part_bounds(obj):
    """Get bounding box for object"""
    if not obj or obj.type != 'MESH':
        return None, None
    
    bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_bbox = Vector((
        min(v.x for v in bbox),
        min(v.y for v in bbox),
        min(v.z for v in bbox)
    ))
    max_bbox = Vector((
        max(v.x for v in bbox),
        max(v.y for v in bbox),
        max(v.z for v in bbox)
    ))
    
    return min_bbox, max_bbox


class PET_OT_standardize_parts(Operator):
    """Standardize selected parts: normalize scale and orientation"""
    bl_idname = "pet.standardize_parts"
    bl_label = "Standardize Parts"
    bl_options = {'REGISTER', 'UNDO'}
    
    normalize_scale: BoolProperty(
        name="Normalize Scale",
        description="Normalize scale relative to reference part",
        default=True
    )
    
    standardize_orientation: BoolProperty(
        name="Standardize Orientation",
        description="Apply standard forward/up orientation",
        default=True
    )
    
    reference_part: StringProperty(
        name="Reference Part",
        description="Part to use as scale reference (body = 1.0)",
        default="Body"
    )
    
    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'ERROR'}, "Please select at least one mesh object")
            return {'CANCELLED'}
        
        # Ensure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Find reference part for scaling
        reference_obj = None
        reference_size = None
        
        if self.normalize_scale:
            for obj in selected_objects:
                if self.reference_part.lower() in obj.name.lower():
                    reference_obj = obj
                    min_bbox, max_bbox = get_part_bounds(obj)
                    if min_bbox and max_bbox:
                        size = max_bbox - min_bbox
                        reference_size = size.length
                    break
            
            # If no reference found, use first object
            if not reference_obj and selected_objects:
                reference_obj = selected_objects[0]
                min_bbox, max_bbox = get_part_bounds(reference_obj)
                if min_bbox and max_bbox:
                    size = max_bbox - min_bbox
                    reference_size = size.length
        
        standardized_count = 0
        
        for obj in selected_objects:
            try:
                # Normalize scale
                if self.normalize_scale and reference_size:
                    min_bbox, max_bbox = get_part_bounds(obj)
                    if min_bbox and max_bbox:
                        obj_size = (max_bbox - min_bbox).length
                        if obj_size > 0.001:
                            scale_factor = reference_size / obj_size
                            obj.scale = Vector((
                                obj.scale.x * scale_factor,
                                obj.scale.y * scale_factor,
                                obj.scale.z * scale_factor
                            ))
                
                # Standardize orientation
                if self.standardize_orientation:
                    # Reset rotation to match standard (forward = +Y, up = +Z)
                    # This assumes parts are already mostly aligned
                    # Full orientation detection would be more complex
                    obj.rotation_euler = (0, 0, 0)
                
                # Store metadata in custom properties
                if self.normalize_scale and reference_size:
                    obj["pet_scale_factor"] = scale_factor if 'scale_factor' in locals() else 1.0
                
                obj["pet_standardized"] = True
                standardized_count += 1
                
            except Exception as e:
                self.report({'WARNING'}, f"Failed to standardize {obj.name}: {str(e)}")
                continue
        
        self.report({'INFO'}, f"Standardized {standardized_count} parts")
        return {'FINISHED'}


class PET_OT_create_attachments(Operator):
    """Create attachment point markers at standard locations"""
    bl_idname = "pet.create_attachments"
    bl_label = "Create Attachments"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Ensure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Get object bounds
        min_bbox, max_bbox = get_part_bounds(obj)
        if not min_bbox or not max_bbox:
            self.report({'ERROR'}, "Could not determine object bounds")
            return {'CANCELLED'}
        
        center = (min_bbox + max_bbox) / 2
        size = max_bbox - min_bbox
        
        # Create attachment points
        attachments_created = []
        
        for att_name, att_id in standards.STANDARD_ATTACHMENTS.items():
            # Calculate attachment position based on part type
            # Simple implementation: place at top (neck), center (root), bottom (hip)
            location = center.copy()
            
            if "neck" in att_name.lower():
                location.z = max_bbox.z
            elif "hip" in att_name.lower():
                location.z = min_bbox.z
            else:  # root
                location = center
            
            # Create empty object as attachment marker
            bpy.ops.object.empty_add(type='ARROWS', location=location)
            empty = context.active_object
            empty.name = att_id
            empty.scale = (0.1, 0.1, 0.1)
            empty["pet_attachment"] = True
            empty["pet_attachment_type"] = att_name
            
            attachments_created.append(att_id)
        
        self.report({'INFO'}, f"Created {len(attachments_created)} attachment points")
        return {'FINISHED'}


classes = [
    PET_OT_standardize_parts,
    PET_OT_create_attachments,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
