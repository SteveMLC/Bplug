"""
Batch export system for multiple pet models
Exports all segmented models with consistent naming for Roblox import
Optimized for processing 100+ AI-generated models
"""

import bpy
import os
import json
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, EnumProperty
from pathlib import Path


def get_all_pet_models(context):
    """Find all pet models in the scene (objects with pet segments or split parts)"""
    models = {}
    
    for obj in context.scene.objects:
        if obj.type != 'MESH':
            continue
        
        name_lower = obj.name.lower()
        
        base_name = None
        part_type = None
        
        for part in ['_head', '_body', '_leg_front_l', '_leg_front_r', 
                     '_leg_back_l', '_leg_back_r', '_tail', '_wing_l', '_wing_r']:
            if part in name_lower:
                idx = obj.name.lower().rfind(part)
                base_name = obj.name[:idx]
                part_type = part[1:]
                break
        
        if base_name:
            if base_name not in models:
                models[base_name] = {'parts': {}, 'joints': []}
            models[base_name]['parts'][part_type] = obj
        elif obj.vertex_groups and any(vg.name.lower() in ['head', 'body', 'leg_front_l'] 
                                       for vg in obj.vertex_groups):
            if obj.name not in models:
                models[obj.name] = {'parts': {}, 'joints': [], 'unsplit': obj}
    
    for obj in context.scene.objects:
        if obj.type == 'EMPTY' and 'r6_joint_type' in obj:
            part0 = obj.get('r6_part0', '')
            for model_name in models:
                if model_name in part0:
                    models[model_name]['joints'].append(obj)
                    break
    
    return models


class PET_OT_batch_export_models(Operator):
    """Export all pet models in the scene with consistent naming"""
    bl_idname = "pet.batch_export_models"
    bl_label = "Batch Export Models"
    bl_options = {'REGISTER', 'UNDO'}
    
    directory: StringProperty(
        subtype='DIR_PATH',
        description="Directory to export models to"
    )
    
    format: EnumProperty(
        name="Format",
        items=[
            ('FBX', "FBX", "FBX format (recommended for Roblox)"),
            ('OBJ', "OBJ", "OBJ format"),
        ],
        default='FBX'
    )
    
    include_metadata: BoolProperty(
        name="Include Metadata",
        description="Export JSON metadata for each model",
        default=True
    )
    
    include_r6_joints: BoolProperty(
        name="Include R6 Joint Data",
        description="Export R6 joint configuration in metadata",
        default=True
    )
    
    create_manifest: BoolProperty(
        name="Create Manifest",
        description="Create a manifest file listing all exported models",
        default=True
    )
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        if not self.directory:
            self.report({'ERROR'}, "Please select a directory")
            return {'CANCELLED'}
        
        models = get_all_pet_models(context)
        
        if not models:
            self.report({'ERROR'}, "No pet models found in scene")
            return {'CANCELLED'}
        
        export_dir = Path(self.directory)
        export_dir.mkdir(parents=True, exist_ok=True)
        
        manifest = {
            'format': self.format,
            'model_count': len(models),
            'models': []
        }
        
        exported_count = 0
        
        for model_name, model_data in models.items():
            model_dir = export_dir / model_name
            model_dir.mkdir(exist_ok=True)
            
            model_manifest = {
                'name': model_name,
                'parts': [],
                'joints': []
            }
            
            original_selection = list(context.selected_objects)
            original_active = context.active_object
            
            try:
                bpy.ops.object.select_all(action='DESELECT')
                
                parts_to_export = model_data.get('parts', {})
                
                if not parts_to_export and 'unsplit' in model_data:
                    unsplit_obj = model_data['unsplit']
                    self.report({'WARNING'}, f"Model '{model_name}' is not split. Exporting as single mesh.")
                    parts_to_export = {'full_model': unsplit_obj}
                
                if not parts_to_export:
                    self.report({'WARNING'}, f"Model '{model_name}' has no parts to export, skipping.")
                    continue
                
                for part_name, part_obj in parts_to_export.items():
                    part_obj.select_set(True)
                    context.view_layer.objects.active = part_obj
                    
                    ext = '.fbx' if self.format == 'FBX' else '.obj'
                    filepath = str(model_dir / f"{part_name}{ext}")
                    
                    if self.format == 'FBX':
                        bpy.ops.export_scene.fbx(
                            filepath=filepath,
                            use_selection=True,
                            apply_scale_options='FBX_SCALE_NONE',
                        )
                    else:
                        bpy.ops.export_scene.obj(
                            filepath=filepath,
                            use_selection=True,
                        )
                    
                    model_manifest['parts'].append({
                        'name': part_name,
                        'file': f"{part_name}{ext}",
                        'vertices': len(part_obj.data.vertices),
                        'faces': len(part_obj.data.polygons),
                    })
                    
                    part_obj.select_set(False)
                
                if self.include_r6_joints:
                    for joint_obj in model_data.get('joints', []):
                        c0_matrix_str = joint_obj.get("r6_c0_matrix", "")
                        c1_matrix_str = joint_obj.get("r6_c1_matrix", "")
                        try:
                            import ast
                            c0_matrix = ast.literal_eval(c0_matrix_str) if c0_matrix_str else None
                            c1_matrix = ast.literal_eval(c1_matrix_str) if c1_matrix_str else None
                        except:
                            c0_matrix = None
                            c1_matrix = None
                        
                        model_manifest['joints'].append({
                            'name': joint_obj.name,
                            'type': joint_obj.get('r6_joint_type', 'Motor6D'),
                            'part0': joint_obj.get('r6_part0', ''),
                            'part1': joint_obj.get('r6_part1', ''),
                            'c0': {
                                'position': list(joint_obj.get('r6_c0_position', [0, 0, 0])),
                                'rotation': list(joint_obj.get('r6_c0_rotation', [0, 0, 0])),
                                'matrix': c0_matrix,
                            },
                            'c1': {
                                'position': list(joint_obj.get('r6_c1_position', [0, 0, 0])),
                                'rotation': list(joint_obj.get('r6_c1_rotation', [0, 0, 0])),
                                'matrix': c1_matrix,
                            },
                            'world_position': list(joint_obj.location),
                            'world_rotation': list(joint_obj.rotation_euler),
                        })
                
                if self.include_metadata:
                    metadata_path = model_dir / f"{model_name}_metadata.json"
                    with open(metadata_path, 'w') as f:
                        json.dump(model_manifest, f, indent=2)
                
                is_unsplit = 'unsplit' in model_data and not model_data.get('parts', {})
                manifest['models'].append({
                    'name': model_name,
                    'parts': len(parts_to_export),
                    'joints': len(model_data.get('joints', [])),
                    'directory': model_name,
                    'split': not is_unsplit,
                })
                
                exported_count += 1
                
            except Exception as e:
                self.report({'WARNING'}, f"Failed to export {model_name}: {str(e)}")
            
            finally:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in original_selection:
                    if obj.name in bpy.data.objects:
                        obj.select_set(True)
                if original_active and original_active.name in bpy.data.objects:
                    context.view_layer.objects.active = original_active
        
        if self.create_manifest:
            manifest_path = export_dir / "batch_manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
        
        self.report({'INFO'}, f"Exported {exported_count} models to {self.directory}")
        return {'FINISHED'}


class PET_OT_batch_process_scene(Operator):
    """Process all unsegmented models in the scene"""
    bl_idname = "pet.batch_process_scene"
    bl_label = "Batch Process Scene"
    bl_options = {'REGISTER', 'UNDO'}
    
    action: EnumProperty(
        name="Action",
        items=[
            ('SEGMENT', "Auto-Segment All", "Run auto-segmentation on all meshes"),
            ('SPLIT', "Split All Segmented", "Split all meshes that have vertex groups"),
            ('CREATE_JOINTS', "Create R6 Joints", "Create R6 joints for all split models"),
        ],
        default='SEGMENT'
    )
    
    def execute(self, context):
        meshes = [obj for obj in context.scene.objects if obj.type == 'MESH']
        
        if not meshes:
            self.report({'ERROR'}, "No mesh objects in scene")
            return {'CANCELLED'}
        
        processed = 0
        
        if self.action == 'SEGMENT':
            for obj in meshes:
                if not obj.vertex_groups:
                    context.view_layer.objects.active = obj
                    obj.select_set(True)
                    try:
                        bpy.ops.pet.segment_model()
                        processed += 1
                    except Exception as e:
                        self.report({'WARNING'}, f"Failed to segment {obj.name}: {str(e)}")
                    obj.select_set(False)
        
        elif self.action == 'SPLIT':
            for obj in meshes:
                if obj.vertex_groups and not any(
                    part in obj.name.lower() for part in ['_head', '_body', '_leg']
                ):
                    context.view_layer.objects.active = obj
                    obj.select_set(True)
                    try:
                        bpy.ops.pet.split_by_vertex_groups(
                            create_pivots=True,
                            keep_original=False
                        )
                        processed += 1
                    except Exception as e:
                        self.report({'WARNING'}, f"Failed to split {obj.name}: {str(e)}")
                    obj.select_set(False)
        
        elif self.action == 'CREATE_JOINTS':
            try:
                bpy.ops.pet.create_r6_joints()
                processed = 1
            except Exception as e:
                self.report({'ERROR'}, f"Failed to create joints: {str(e)}")
                return {'CANCELLED'}
        
        self.report({'INFO'}, f"Processed {processed} objects with action: {self.action}")
        return {'FINISHED'}


class PET_OT_list_models(Operator):
    """List all pet models detected in the scene"""
    bl_idname = "pet.list_models"
    bl_label = "List Models"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        models = get_all_pet_models(context)
        
        if not models:
            self.report({'INFO'}, "No pet models found in scene")
            return {'CANCELLED'}
        
        info = f"Found {len(models)} model(s): "
        for name, data in models.items():
            parts = len(data.get('parts', {}))
            joints = len(data.get('joints', []))
            info += f"{name} ({parts} parts, {joints} joints), "
        
        self.report({'INFO'}, info.rstrip(', '))
        return {'FINISHED'}


classes = [
    PET_OT_batch_export_models,
    PET_OT_batch_process_scene,
    PET_OT_list_models,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
