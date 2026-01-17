"""
Export operators
Prepares models for Roblox import with proper naming and structure
"""

import bpy
import json
import os
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper
from pathlib import Path
from ..utils import roblox_export


class PET_OT_export_model(Operator, ExportHelper):
    """Export model for Roblox with metadata"""
    bl_idname = "pet.export_model"
    bl_label = "Export Model"
    bl_options = {'REGISTER', 'UNDO'}
    
    filename_ext = ".fbx"
    
    filter_glob: StringProperty(
        default="*.fbx;*.obj",
        options={'HIDDEN'},
        maxlen=255,
    )
    
    format: EnumProperty(
        name="Format",
        description="Export file format",
        items=[
            ('FBX', "FBX", "FBX format (recommended for Roblox)"),
            ('OBJ', "OBJ", "OBJ format"),
        ],
        default='FBX'
    )
    
    include_metadata: BoolProperty(
        name="Include Metadata",
        description="Export JSON metadata file with model information",
        default=True
    )
    
    def execute(self, context):
        # Set file extension based on format
        if self.format == 'FBX':
            if not self.filepath.endswith('.fbx'):
                self.filepath = os.path.splitext(self.filepath)[0] + '.fbx'
        else:  # OBJ
            if not self.filepath.endswith('.obj'):
                self.filepath = os.path.splitext(self.filepath)[0] + '.obj'
        
        # Get objects to export
        objects_to_export = [obj for obj in context.selected_objects if obj.type in ['MESH', 'ARMATURE']]
        
        if not objects_to_export:
            # Export active object or all scene objects
            if context.active_object:
                objects_to_export = [context.active_object]
            else:
                objects_to_export = [obj for obj in context.scene.objects if obj.type in ['MESH', 'ARMATURE']]
        
        if not objects_to_export:
            self.report({'ERROR'}, "No objects to export")
            return {'CANCELLED'}
        
        # Store original selection
        original_selection = list(context.selected_objects)
        original_active = context.active_object
        
        try:
            # Select objects to export
            bpy.ops.object.select_all(action='DESELECT')
            for obj in objects_to_export:
                obj.select_set(True)
            context.view_layer.objects.active = objects_to_export[0]
            
            # Export based on format
            if self.format == 'FBX':
                bpy.ops.export_scene.fbx(
                    filepath=self.filepath,
                    use_selection=True,
                    apply_scale_options='FBX_SCALE_NONE',
                    bake_space_transform=False,
                )
            else:  # OBJ
                bpy.ops.export_scene.obj(
                    filepath=self.filepath,
                    use_selection=True,
                )
            
            # Export metadata if requested
            if self.include_metadata:
                metadata_path = os.path.splitext(self.filepath)[0] + '_metadata.json'
                
                metadata = {
                    "format": self.format,
                    "objects": [],
                    "vertex_groups": [],
                    "attachments": [],
                }
                
                for obj in objects_to_export:
                    obj_data = {
                        "name": obj.name,
                        "type": obj.type,
                        "location": list(obj.location),
                        "scale": list(obj.scale),
                        "rotation": list(obj.rotation_euler),
                    }
                    
                    if obj.type == 'MESH' and obj.vertex_groups:
                        obj_data["vertex_groups"] = [vg.name for vg in obj.vertex_groups]
                        metadata["vertex_groups"].extend([vg.name for vg in obj.vertex_groups])
                    
                    # Check for custom properties
                    if "pet_scale_factor" in obj:
                        obj_data["scale_factor"] = obj["pet_scale_factor"]
                    if "pet_standardized" in obj:
                        obj_data["standardized"] = obj["pet_standardized"]
                    
                    metadata["objects"].append(obj_data)
                    
                    # Check for attachment points (Empty objects)
                    if obj.type == 'EMPTY' and "pet_attachment" in obj:
                        metadata["attachments"].append({
                            "name": obj.name,
                            "location": list(obj.location),
                            "type": obj.get("pet_attachment_type", "unknown"),
                        })
                
                # Save metadata
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
            
            self.report({'INFO'}, f"Exported {len(objects_to_export)} objects to {self.filepath}")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            return {'CANCELLED'}
        
        finally:
            # Restore selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                obj.select_set(True)
            context.view_layer.objects.active = original_active


class PET_OT_export_part_library(Operator):
    """Export part library with standardized naming"""
    bl_idname = "pet.export_part_library"
    bl_label = "Export Part Library"
    bl_options = {'REGISTER', 'UNDO'}
    
    directory: StringProperty(
        subtype='DIR_PATH',
    )
    
    format: EnumProperty(
        name="Format",
        description="Export file format",
        items=[
            ('FBX', "FBX", "FBX format"),
            ('OBJ', "OBJ", "OBJ format"),
        ],
        default='OBJ'
    )
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        if not self.directory:
            self.report({'ERROR'}, "Please select a directory")
            return {'CANCELLED'}
        
        # Get selected objects or all mesh objects
        objects_to_export = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not objects_to_export:
            objects_to_export = [obj for obj in context.scene.objects if obj.type == 'MESH']
        
        if not objects_to_export:
            self.report({'ERROR'}, "No mesh objects to export")
            return {'CANCELLED'}
        
        # Create library structure
        lib_path = roblox_export.create_part_library_structure(self.directory)
        
        exported_count = 0
        
        # Export each object as a separate file
        original_selection = list(context.selected_objects)
        original_active = context.active_object
        
        try:
            for obj in objects_to_export:
                # Determine part category
                category = "parts"
                obj_name_lower = obj.name.lower()
                
                if "head" in obj_name_lower:
                    category = "heads"
                elif "body" in obj_name_lower or "torso" in obj_name_lower:
                    category = "bodies"
                elif "leg" in obj_name_lower or "foot" in obj_name_lower:
                    category = "legs"
                elif "tail" in obj_name_lower:
                    category = "tails"
                elif "wing" in obj_name_lower:
                    category = "wings"
                
                # Create filepath
                ext = '.fbx' if self.format == 'FBX' else '.obj'
                filename = f"{obj.name}{ext}"
                filepath = os.path.join(str(lib_path), category, filename)
                
                # Select only this object
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                
                # Export
                try:
                    if self.format == 'FBX':
                        bpy.ops.export_scene.fbx(
                            filepath=filepath,
                            use_selection=True,
                            apply_scale_options='FBX_SCALE_NONE',
                        )
                    else:  # OBJ
                        bpy.ops.export_scene.obj(
                            filepath=filepath,
                            use_selection=True,
                        )
                    
                    # Export metadata for this part
                    metadata_path = os.path.splitext(filepath)[0] + '_metadata.json'
                    metadata = {
                        "name": obj.name,
                        "category": category,
                        "format": self.format,
                        "scale_factor": obj.get("pet_scale_factor", 1.0) if "pet_scale_factor" in obj else 1.0,
                        "standardized": obj.get("pet_standardized", False) if "pet_standardized" in obj else False,
                    }
                    
                    if obj.vertex_groups:
                        metadata["vertex_groups"] = [vg.name for vg in obj.vertex_groups]
                    
                    with open(metadata_path, 'w') as f:
                        json.dump(metadata, f, indent=2)
                    
                    exported_count += 1
                    
                except Exception as e:
                    self.report({'WARNING'}, f"Failed to export {obj.name}: {str(e)}")
                    continue
            
            # Restore selection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                obj.select_set(True)
            context.view_layer.objects.active = original_active
            
            self.report({'INFO'}, f"Exported {exported_count} parts to {lib_path}")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            return {'CANCELLED'}


classes = [
    PET_OT_export_model,
    PET_OT_export_part_library,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
