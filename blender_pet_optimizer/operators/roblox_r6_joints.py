"""
Roblox R6 Joint System
Creates Motor6D-compatible pivot points with proper naming and orientations
for seamless Roblox import
"""

import bpy
import bmesh
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty, FloatProperty
from mathutils import Vector, Matrix, Euler
import math


R6_JOINT_CONFIG = {
    'head': {
        'parent': 'body',
        'joint_name': 'Neck',
        'attachment_name': 'NeckAttachment',
        'c0_offset': Vector((0, 0, 0.5)),
        'c1_offset': Vector((0, 0, -0.5)),
        'orientation': Euler((0, 0, 0)),
    },
    'leg_front_l': {
        'parent': 'body',
        'joint_name': 'LeftFrontHip',
        'attachment_name': 'LeftFrontHipAttachment',
        'c0_offset': Vector((0.3, 0.3, -0.3)),
        'c1_offset': Vector((0, 0, 0.5)),
        'orientation': Euler((0, 0, 0)),
    },
    'leg_front_r': {
        'parent': 'body',
        'joint_name': 'RightFrontHip',
        'attachment_name': 'RightFrontHipAttachment',
        'c0_offset': Vector((-0.3, 0.3, -0.3)),
        'c1_offset': Vector((0, 0, 0.5)),
        'orientation': Euler((0, 0, 0)),
    },
    'leg_back_l': {
        'parent': 'body',
        'joint_name': 'LeftBackHip',
        'attachment_name': 'LeftBackHipAttachment',
        'c0_offset': Vector((0.3, -0.3, -0.3)),
        'c1_offset': Vector((0, 0, 0.5)),
        'orientation': Euler((0, 0, 0)),
    },
    'leg_back_r': {
        'parent': 'body',
        'joint_name': 'RightBackHip',
        'attachment_name': 'RightBackHipAttachment',
        'c0_offset': Vector((-0.3, -0.3, -0.3)),
        'c1_offset': Vector((0, 0, 0.5)),
        'orientation': Euler((0, 0, 0)),
    },
    'tail': {
        'parent': 'body',
        'joint_name': 'TailMotor',
        'attachment_name': 'TailAttachment',
        'c0_offset': Vector((0, -0.5, 0)),
        'c1_offset': Vector((0, 0.3, 0)),
        'orientation': Euler((0, 0, 0)),
    },
    'wing_l': {
        'parent': 'body',
        'joint_name': 'LeftWingMotor',
        'attachment_name': 'LeftWingAttachment',
        'c0_offset': Vector((0.4, 0, 0.2)),
        'c1_offset': Vector((-0.2, 0, 0)),
        'orientation': Euler((0, 0, math.radians(90))),
    },
    'wing_r': {
        'parent': 'body',
        'joint_name': 'RightWingMotor',
        'attachment_name': 'RightWingAttachment',
        'c0_offset': Vector((-0.4, 0, 0.2)),
        'c1_offset': Vector((0.2, 0, 0)),
        'orientation': Euler((0, 0, math.radians(-90))),
    },
}


def get_segment_bounds(obj):
    """Get bounding box info for a mesh object"""
    if not obj or obj.type != 'MESH':
        return None
    
    mesh = obj.data
    if not mesh.vertices:
        return None
    
    min_co = Vector((float('inf'), float('inf'), float('inf')))
    max_co = Vector((float('-inf'), float('-inf'), float('-inf')))
    
    for vert in mesh.vertices:
        world_co = obj.matrix_world @ vert.co
        min_co.x = min(min_co.x, world_co.x)
        min_co.y = min(min_co.y, world_co.y)
        min_co.z = min(min_co.z, world_co.z)
        max_co.x = max(max_co.x, world_co.x)
        max_co.y = max(max_co.y, world_co.y)
        max_co.z = max(max_co.z, world_co.z)
    
    center = (min_co + max_co) / 2
    size = max_co - min_co
    
    return {
        'min': min_co,
        'max': max_co,
        'center': center,
        'size': size,
    }


def find_boundary_center(obj1, obj2):
    """Find the center point between two mesh objects at their boundary"""
    bounds1 = get_segment_bounds(obj1)
    bounds2 = get_segment_bounds(obj2)
    
    if not bounds1 or not bounds2:
        return None
    
    closest_point = (bounds1['center'] + bounds2['center']) / 2
    return closest_point


def compute_c0_c1_from_parts(joint_world_matrix, part0_obj, part1_obj):
    """
    Compute C0 and C1 transforms in part-local space for Motor6D.
    Returns full CFrame-compatible transforms (position + rotation).
    
    In Roblox Motor6D:
    - C0: Transform from Part0's center to the joint in Part0's local space
    - C1: Transform from Part1's center to the joint in Part1's local space
    """
    part0_world_inv = part0_obj.matrix_world.inverted()
    part1_world_inv = part1_obj.matrix_world.inverted()
    
    c0_matrix = part0_world_inv @ joint_world_matrix
    c1_matrix = part1_world_inv @ joint_world_matrix
    
    c0_position = list(c0_matrix.to_translation())
    c0_rotation = list(c0_matrix.to_euler())
    
    c1_position = list(c1_matrix.to_translation())
    c1_rotation = list(c1_matrix.to_euler())
    
    c0_data = {
        'position': c0_position,
        'rotation': c0_rotation,
        'matrix': [list(row) for row in c0_matrix]
    }
    
    c1_data = {
        'position': c1_position,
        'rotation': c1_rotation,
        'matrix': [list(row) for row in c1_matrix]
    }
    
    return c0_data, c1_data


class PET_OT_create_r6_joints(Operator):
    """Create Roblox R6-compatible joints from segmented mesh parts"""
    bl_idname = "pet.create_r6_joints"
    bl_label = "Create R6 Joints"
    bl_options = {'REGISTER', 'UNDO'}
    
    joint_scale: FloatProperty(
        name="Joint Scale",
        description="Scale factor for joint visualization",
        default=0.1,
        min=0.01,
        max=1.0,
    )
    
    use_custom_offsets: BoolProperty(
        name="Calculate Offsets from Mesh",
        description="Calculate C0/C1 offsets from actual mesh boundaries instead of using defaults",
        default=True
    )
    
    def execute(self, context):
        scene_objects = list(context.scene.objects)
        
        body_obj = None
        segment_objects = {}
        
        for obj in scene_objects:
            if obj.type != 'MESH':
                continue
            
            name_lower = obj.name.lower()
            
            if 'body' in name_lower or 'torso' in name_lower:
                body_obj = obj
            elif 'head' in name_lower:
                segment_objects['head'] = obj
            elif 'leg_front_l' in name_lower or 'frontleftleg' in name_lower:
                segment_objects['leg_front_l'] = obj
            elif 'leg_front_r' in name_lower or 'frontrightleg' in name_lower:
                segment_objects['leg_front_r'] = obj
            elif 'leg_back_l' in name_lower or 'backleftleg' in name_lower:
                segment_objects['leg_back_l'] = obj
            elif 'leg_back_r' in name_lower or 'backrightleg' in name_lower:
                segment_objects['leg_back_r'] = obj
            elif 'tail' in name_lower:
                segment_objects['tail'] = obj
            elif 'wing_l' in name_lower or 'leftwing' in name_lower:
                segment_objects['wing_l'] = obj
            elif 'wing_r' in name_lower or 'rightwing' in name_lower:
                segment_objects['wing_r'] = obj
        
        if not body_obj:
            self.report({'ERROR'}, "No body/torso mesh found. Please split the mesh first.")
            return {'CANCELLED'}
        
        if not segment_objects:
            self.report({'WARNING'}, "No segment meshes found. Only body exists.")
            return {'CANCELLED'}
        
        joints_collection_name = "R6_Joints"
        if joints_collection_name in bpy.data.collections:
            joints_collection = bpy.data.collections[joints_collection_name]
            for obj in list(joints_collection.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
        else:
            joints_collection = bpy.data.collections.new(joints_collection_name)
            context.scene.collection.children.link(joints_collection)
        
        joints_created = []
        
        for segment_name, segment_obj in segment_objects.items():
            if segment_name not in R6_JOINT_CONFIG:
                continue
            
            config = R6_JOINT_CONFIG[segment_name]
            
            joint_position = find_boundary_center(body_obj, segment_obj)
            
            if not joint_position:
                body_bounds = get_segment_bounds(body_obj)
                segment_bounds = get_segment_bounds(segment_obj)
                if body_bounds and segment_bounds:
                    joint_position = (body_bounds['center'] + segment_bounds['center']) / 2
                else:
                    continue
            
            segment_bounds = get_segment_bounds(segment_obj)
            body_bounds = get_segment_bounds(body_obj)
            
            if segment_bounds and body_bounds:
                direction = segment_bounds['center'] - body_bounds['center']
                if direction.length > 0.001:
                    direction.normalize()
                else:
                    direction = Vector((0, 1, 0))
                
                up = Vector((0, 0, 1))
                right = direction.cross(up)
                if right.length < 0.01:
                    right = Vector((1, 0, 0))
                right.normalize()
                up = right.cross(direction)
                
                rot_matrix = Matrix((right, direction, up)).transposed().to_4x4()
                joint_orientation = rot_matrix.to_euler()
            else:
                joint_orientation = config['orientation']
                rot_matrix = Euler(config['orientation']).to_matrix().to_4x4()
            
            joint_world_matrix = Matrix.Translation(joint_position) @ rot_matrix
            
            c0_data, c1_data = compute_c0_c1_from_parts(joint_world_matrix, body_obj, segment_obj)
            
            joint_empty = bpy.data.objects.new(config['joint_name'], None)
            joint_empty.empty_display_type = 'ARROWS'
            joint_empty.empty_display_size = self.joint_scale
            joint_empty.location = joint_position
            joint_empty.rotation_euler = joint_orientation
            
            joint_empty["r6_joint_type"] = "Motor6D"
            joint_empty["r6_part0"] = body_obj.name
            joint_empty["r6_part1"] = segment_obj.name
            joint_empty["r6_c0_position"] = c0_data['position']
            joint_empty["r6_c0_rotation"] = c0_data['rotation']
            joint_empty["r6_c0_matrix"] = str(c0_data['matrix'])
            joint_empty["r6_c1_position"] = c1_data['position']
            joint_empty["r6_c1_rotation"] = c1_data['rotation']
            joint_empty["r6_c1_matrix"] = str(c1_data['matrix'])
            joint_empty["r6_attachment_name"] = config['attachment_name']
            
            joints_collection.objects.link(joint_empty)
            joints_created.append(config['joint_name'])
            
            self._create_attachment_on_part(context, body_obj, config['attachment_name'] + "_Part0", 
                                           joint_position, joint_orientation, joints_collection)
            self._create_attachment_on_part(context, segment_obj, config['attachment_name'] + "_Part1",
                                           joint_position, joint_orientation, joints_collection)
        
        self.report({'INFO'}, f"Created {len(joints_created)} R6 joints: {', '.join(joints_created)}")
        return {'FINISHED'}
    
    def _create_attachment_on_part(self, context, part_obj, attachment_name, position, orientation, collection):
        """Create an attachment point on a part"""
        attachment = bpy.data.objects.new(attachment_name, None)
        attachment.empty_display_type = 'SPHERE'
        attachment.empty_display_size = 0.05
        attachment.location = position
        attachment.rotation_euler = orientation
        
        attachment["r6_attachment"] = True
        attachment["r6_parent_part"] = part_obj.name
        
        collection.objects.link(attachment)
        
        attachment.parent = part_obj
        attachment.matrix_parent_inverse = part_obj.matrix_world.inverted()


class PET_OT_export_r6_metadata(Operator):
    """Export R6 joint metadata as JSON for Roblox import scripts"""
    bl_idname = "pet.export_r6_metadata"
    bl_label = "Export R6 Metadata"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: bpy.props.StringProperty(
        subtype='FILE_PATH',
        default="r6_joints.json"
    )
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        import json
        
        joints_data = {
            "model_name": "",
            "joints": [],
            "parts": [],
        }
        
        for obj in context.scene.objects:
            if obj.type == 'EMPTY' and "r6_joint_type" in obj:
                c0_matrix_str = obj.get("r6_c0_matrix", "")
                c1_matrix_str = obj.get("r6_c1_matrix", "")
                try:
                    import ast
                    c0_matrix = ast.literal_eval(c0_matrix_str) if c0_matrix_str else None
                    c1_matrix = ast.literal_eval(c1_matrix_str) if c1_matrix_str else None
                except:
                    c0_matrix = None
                    c1_matrix = None
                
                joint_info = {
                    "name": obj.name,
                    "type": obj["r6_joint_type"],
                    "part0": obj.get("r6_part0", ""),
                    "part1": obj.get("r6_part1", ""),
                    "c0": {
                        "position": list(obj.get("r6_c0_position", [0, 0, 0])),
                        "rotation": list(obj.get("r6_c0_rotation", [0, 0, 0])),
                        "matrix": c0_matrix,
                    },
                    "c1": {
                        "position": list(obj.get("r6_c1_position", [0, 0, 0])),
                        "rotation": list(obj.get("r6_c1_rotation", [0, 0, 0])),
                        "matrix": c1_matrix,
                    },
                    "world_position": list(obj.location),
                    "world_rotation": list(obj.rotation_euler),
                }
                joints_data["joints"].append(joint_info)
            
            elif obj.type == 'MESH':
                bounds = get_segment_bounds(obj)
                if bounds:
                    part_info = {
                        "name": obj.name,
                        "position": list(obj.location),
                        "size": list(bounds['size']),
                        "center": list(bounds['center']),
                    }
                    joints_data["parts"].append(part_info)
        
        try:
            with open(self.filepath, 'w') as f:
                json.dump(joints_data, f, indent=2)
            self.report({'INFO'}, f"Exported R6 metadata to {self.filepath}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to export: {str(e)}")
            return {'CANCELLED'}


class PET_OT_visualize_r6_hierarchy(Operator):
    """Visualize the R6 joint hierarchy with connecting lines"""
    bl_idname = "pet.visualize_r6_hierarchy"
    bl_label = "Visualize R6 Hierarchy"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        curve_name = "R6_Hierarchy_Visualization"
        
        if curve_name in bpy.data.objects:
            old_obj = bpy.data.objects[curve_name]
            bpy.data.objects.remove(old_obj, do_unlink=True)
        
        curve_data = bpy.data.curves.new(curve_name, 'CURVE')
        curve_data.dimensions = '3D'
        
        for obj in context.scene.objects:
            if obj.type == 'EMPTY' and "r6_joint_type" in obj:
                part0_name = obj.get("r6_part0", "")
                part1_name = obj.get("r6_part1", "")
                
                part0 = bpy.data.objects.get(part0_name)
                part1 = bpy.data.objects.get(part1_name)
                
                if part0 and part1:
                    bounds0 = get_segment_bounds(part0)
                    bounds1 = get_segment_bounds(part1)
                    
                    if bounds0 and bounds1:
                        spline = curve_data.splines.new('POLY')
                        spline.points.add(1)
                        
                        spline.points[0].co = (*bounds0['center'], 1)
                        spline.points[1].co = (*bounds1['center'], 1)
        
        curve_obj = bpy.data.objects.new(curve_name, curve_data)
        curve_data.bevel_depth = 0.01
        context.scene.collection.objects.link(curve_obj)
        
        mat = bpy.data.materials.new("R6_Hierarchy_Material")
        mat.diffuse_color = (0.2, 0.8, 0.2, 1.0)
        curve_obj.data.materials.append(mat)
        
        self.report({'INFO'}, "Created R6 hierarchy visualization")
        return {'FINISHED'}


classes = [
    PET_OT_create_r6_joints,
    PET_OT_export_r6_metadata,
    PET_OT_visualize_r6_hierarchy,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
