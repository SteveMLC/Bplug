"""
Rigging operators
Creates armatures from vertex groups with bone hierarchy setup
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty
from mathutils import Vector
from ..config import standards


def get_vertex_group_center(obj, vertex_group_name):
    """Calculate center of vertices in a vertex group"""
    mesh = obj.data
    vg_index = obj.vertex_groups.find(vertex_group_name)
    
    if vg_index == -1:
        return None
    
    center = Vector((0, 0, 0))
    count = 0
    
    for vertex in mesh.vertices:
        for group in vertex.groups:
            if group.group == vg_index:
                world_pos = obj.matrix_world @ vertex.co
                center += world_pos
                count += 1
                break
    
    if count == 0:
        return None
    
    return center / count


def create_bone_at_location(armature, bone_name, location, parent=None):
    """Create a bone at a specific location"""
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Create bone
    bone = armature.data.edit_bones.new(bone_name)
    bone.head = location
    bone.tail = location + Vector((0, 0.1, 0))  # Default length, will be adjusted
    
    if parent:
        bone.parent = armature.data.edit_bones.get(parent)
    
    bpy.ops.object.mode_set(mode='OBJECT')
    return bone


class PET_OT_create_armature(Operator):
    """Create armature from vertex groups"""
    bl_idname = "pet.create_armature"
    bl_label = "Create Armature"
    bl_options = {'REGISTER', 'UNDO'}
    
    bone_prefix: StringProperty(
        name="Bone Prefix",
        description="Prefix for bone names",
        default=""
    )
    
    auto_weights: BoolProperty(
        name="Auto Assign Weights",
        description="Automatically assign vertex weights from vertex groups",
        default=True
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if not obj.vertex_groups:
            self.report({'ERROR'}, "No vertex groups found. Please segment the model first.")
            return {'CANCELLED'}
        
        # Ensure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Create armature
        armature_data = bpy.data.armatures.new(name=f"{obj.name}_Armature")
        armature = bpy.data.objects.new(f"{obj.name}_Armature", armature_data)
        armature.location = obj.location
        context.collection.objects.link(armature)
        
        # Set as active
        context.view_layer.objects.active = armature
        
        # Create bones from vertex groups
        bones_created = []
        
        # First, find root bone (usually "body" or largest group)
        root_group = None
        max_vertices = 0
        
        mesh = obj.data
        for vg in obj.vertex_groups:
            count = sum(1 for v in mesh.vertices 
                       for g in v.groups if g.group == vg.index)
            if count > max_vertices and vg.name.lower() in ['body', 'torso', 'core']:
                root_group = vg.name
                max_vertices = count
        
        # If no body group, use first group
        if not root_group:
            root_group = obj.vertex_groups[0].name
        
        # Create root bone
        root_location = get_vertex_group_center(obj, root_group)
        if root_location:
            bpy.ops.object.mode_set(mode='EDIT')
            root_bone = armature.data.edit_bones.new(
                f"{self.bone_prefix}{standards.BONE_ROOT}".strip('_')
            )
            root_bone.head = root_location
            root_bone.tail = root_location + Vector((0, 0.1, 0))
            bones_created.append(root_group)
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Create bones for other vertex groups
        bpy.ops.object.mode_set(mode='EDIT')
        for vg in obj.vertex_groups:
            if vg.name == root_group:
                continue
            
            location = get_vertex_group_center(obj, vg.name)
            if location:
                bone_name = f"{self.bone_prefix}{vg.name}".strip('_')
                bone = armature.data.edit_bones.new(bone_name)
                bone.head = location
                bone.tail = location + Vector((0, 0.1, 0))
                
                # Parent to root
                root_bone_edit = armature.data.edit_bones.get(
                    f"{self.bone_prefix}{standards.BONE_ROOT}".strip('_')
                )
                if root_bone_edit:
                    bone.parent = root_bone_edit
                
                bones_created.append(vg.name)
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Select original mesh again
        context.view_layer.objects.active = obj
        
        # Auto-assign weights if requested
        if self.auto_weights:
            # Modifier will be added in setup_rig operator
            pass
        
        self.report({'INFO'}, f"Created armature with {len(bones_created)} bones")
        return {'FINISHED'}


class PET_OT_setup_rig(Operator):
    """Setup rig with bone hierarchy and weights"""
    bl_idname = "pet.setup_rig"
    bl_label = "Setup Rig"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        # Find armature in scene
        armature = None
        for o in context.scene.objects:
            if o.type == 'ARMATURE' and o.name.startswith(obj.name):
                armature = o
                break
        
        if not armature:
            self.report({'ERROR'}, "No armature found. Please create armature first.")
            return {'CANCELLED'}
        
        # Ensure we're in object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Add armature modifier if not present
        modifier = None
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE':
                modifier = mod
                break
        
        if not modifier:
            modifier = obj.modifiers.new(name="Armature", type='ARMATURE')
        
        modifier.object = armature
        modifier.use_vertex_groups = True
        
        # Assign vertex group weights to bones
        # This maps vertex groups to bones and assigns weights
        if obj.vertex_groups and armature.data.bones:
            # The weights should already be set from vertex groups
            # We just need to ensure the modifier is configured correctly
            pass
        
        self.report({'INFO'}, "Rig setup complete")
        return {'FINISHED'}


classes = [
    PET_OT_create_armature,
    PET_OT_setup_rig,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
