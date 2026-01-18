"""
Symmetry detection and mirror selection tools for pet models
Detects model symmetry axis and allows mirroring vertex selections
"""

import bpy
import bmesh
from bpy.types import Operator
from bpy.props import EnumProperty, FloatProperty, BoolProperty
from mathutils import Vector, kdtree
import time


SYMMETRY_THRESHOLD = 0.01
MAX_VERTS_DIRECT = 100000


class PET_OT_detect_symmetry(Operator):
    """Detect the symmetry axis of the model"""
    bl_idname = "pet.detect_symmetry"
    bl_label = "Detect Symmetry Axis"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        mesh = obj.data
        verts = [v.co.copy() for v in mesh.vertices]
        
        if not verts:
            self.report({'ERROR'}, "Mesh has no vertices")
            return {'CANCELLED'}
        
        center = sum(verts, Vector()) / len(verts)
        
        kd = kdtree.KDTree(len(verts))
        for i, v in enumerate(verts):
            kd.insert(v, i)
        kd.balance()
        
        scores = {'X': 0, 'Y': 0, 'Z': 0}
        
        for axis_name, axis_idx in [('X', 0), ('Y', 1), ('Z', 2)]:
            matches = 0
            for v in verts:
                mirrored = v.copy()
                mirrored[axis_idx] = 2 * center[axis_idx] - v[axis_idx]
                
                co, index, dist = kd.find(mirrored)
                if dist < SYMMETRY_THRESHOLD:
                    matches += 1
            
            scores[axis_name] = matches / len(verts) if verts else 0
        
        best_axis = max(scores, key=scores.get)
        best_score = scores[best_axis]
        
        obj["pet_symmetry_axis"] = best_axis
        obj["pet_symmetry_score"] = best_score
        obj["pet_symmetry_center"] = list(center)
        
        if best_score > 0.8:
            confidence = "high"
        elif best_score > 0.5:
            confidence = "medium"
        else:
            confidence = "low"
        
        self.report({'INFO'}, f"Detected {best_axis}-axis symmetry ({confidence} confidence: {best_score:.1%})")
        return {'FINISHED'}


class PET_OT_mirror_selection(Operator):
    """Mirror current vertex selection across symmetry axis"""
    bl_idname = "pet.mirror_selection"
    bl_label = "Mirror Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    axis: EnumProperty(
        name="Axis",
        description="Axis to mirror across",
        items=[
            ('AUTO', "Auto-Detect", "Use detected symmetry axis"),
            ('X', "X Axis", "Mirror across X axis"),
            ('Y', "Y Axis", "Mirror across Y axis"),
            ('Z', "Z Axis", "Mirror across Z axis"),
        ],
        default='AUTO'
    )
    
    threshold: FloatProperty(
        name="Threshold",
        description="Distance threshold for matching mirrored vertices",
        default=0.05,
        min=0.001,
        max=1.0
    )
    
    extend_selection: BoolProperty(
        name="Extend Selection",
        description="Add mirrored vertices to current selection instead of replacing",
        default=True
    )
    
    def execute(self, context):
        start_time = time.time()
        
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode with vertices selected")
            return {'CANCELLED'}
        
        if self.axis == 'AUTO':
            axis = obj.get("pet_symmetry_axis", "X")
            if "pet_symmetry_axis" not in obj:
                bpy.ops.pet.detect_symmetry()
                axis = obj.get("pet_symmetry_axis", "X")
        else:
            axis = self.axis
        
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[axis]
        
        center = Vector(obj.get("pet_symmetry_center", [0, 0, 0]))
        
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        
        selected_verts = [v for v in bm.verts if v.select]
        
        if not selected_verts:
            self.report({'ERROR'}, "No vertices selected")
            return {'CANCELLED'}
        
        total_verts = len(bm.verts)
        use_progress = total_verts > MAX_VERTS_DIRECT
        
        if use_progress:
            context.window_manager.progress_begin(0, 100)
        
        kd = kdtree.KDTree(len(bm.verts))
        for i, v in enumerate(bm.verts):
            kd.insert(v.co, i)
        kd.balance()
        
        if use_progress:
            context.window_manager.progress_update(30)
        
        mirrored_count = 0
        
        for i, v in enumerate(selected_verts):
            mirrored_co = v.co.copy()
            mirrored_co[axis_idx] = 2 * center[axis_idx] - v.co[axis_idx]
            
            co, index, dist = kd.find(mirrored_co)
            
            if dist < self.threshold:
                bm.verts[index].select = True
                mirrored_count += 1
            
            if use_progress and i % 1000 == 0:
                context.window_manager.progress_update(30 + (i / len(selected_verts)) * 70)
        
        if not self.extend_selection:
            for v in selected_verts:
                v.select = False
        
        if use_progress:
            context.window_manager.progress_end()
        
        bmesh.update_edit_mesh(obj.data)
        
        elapsed = time.time() - start_time
        self.report({'INFO'}, f"Mirrored {mirrored_count} vertices across {axis} axis ({elapsed:.2f}s)")
        return {'FINISHED'}


class PET_OT_select_half(Operator):
    """Select all vertices on one side of the symmetry axis"""
    bl_idname = "pet.select_half"
    bl_label = "Select Half"
    bl_options = {'REGISTER', 'UNDO'}
    
    side: EnumProperty(
        name="Side",
        description="Which side to select",
        items=[
            ('POSITIVE', "Positive", "Select positive side (+X, +Y, or +Z)"),
            ('NEGATIVE', "Negative", "Select negative side (-X, -Y, or -Z)"),
        ],
        default='POSITIVE'
    )
    
    axis: EnumProperty(
        name="Axis",
        description="Axis to divide on",
        items=[
            ('AUTO', "Auto-Detect", "Use detected symmetry axis"),
            ('X', "X Axis", "Divide on X axis"),
            ('Y', "Y Axis", "Divide on Y axis"),
            ('Z', "Z Axis", "Divide on Z axis"),
        ],
        default='AUTO'
    )
    
    include_center: BoolProperty(
        name="Include Center",
        description="Include vertices on the center line",
        default=True
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        if self.axis == 'AUTO':
            axis = obj.get("pet_symmetry_axis", "X")
            if "pet_symmetry_axis" not in obj:
                bpy.ops.pet.detect_symmetry()
                axis = obj.get("pet_symmetry_axis", "X")
        else:
            axis = self.axis
        
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[axis]
        center = Vector(obj.get("pet_symmetry_center", [0, 0, 0]))
        center_val = center[axis_idx]
        
        bm = bmesh.from_edit_mesh(obj.data)
        
        bpy.ops.mesh.select_all(action='DESELECT')
        
        selected_count = 0
        center_threshold = 0.001
        
        for v in bm.verts:
            val = v.co[axis_idx]
            
            if abs(val - center_val) < center_threshold:
                if self.include_center:
                    v.select = True
                    selected_count += 1
            elif self.side == 'POSITIVE' and val > center_val:
                v.select = True
                selected_count += 1
            elif self.side == 'NEGATIVE' and val < center_val:
                v.select = True
                selected_count += 1
        
        bmesh.update_edit_mesh(obj.data)
        
        side_name = "+" if self.side == 'POSITIVE' else "-"
        self.report({'INFO'}, f"Selected {selected_count} vertices on {side_name}{axis} side")
        return {'FINISHED'}


class PET_OT_symmetrize_segments(Operator):
    """Copy segment assignments from one side to the other"""
    bl_idname = "pet.symmetrize_segments"
    bl_label = "Symmetrize Segments"
    bl_options = {'REGISTER', 'UNDO'}
    
    direction: EnumProperty(
        name="Direction",
        description="Which side to copy from",
        items=[
            ('LEFT_TO_RIGHT', "Left to Right", "Copy from left side to right side"),
            ('RIGHT_TO_LEFT', "Right to Left", "Copy from right side to left side"),
        ],
        default='LEFT_TO_RIGHT'
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        axis = obj.get("pet_symmetry_axis", "X")
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[axis]
        center = Vector(obj.get("pet_symmetry_center", [0, 0, 0]))
        
        segment_pairs = {
            'Segment_Leg_Front_L': 'Segment_Leg_Front_R',
            'Segment_Leg_Back_L': 'Segment_Leg_Back_R',
            'Segment_Wing_L': 'Segment_Wing_R',
        }
        
        if self.direction == 'RIGHT_TO_LEFT':
            segment_pairs = {v: k for k, v in segment_pairs.items()}
        
        mesh = obj.data
        kd = kdtree.KDTree(len(mesh.vertices))
        for i, v in enumerate(mesh.vertices):
            kd.insert(v.co, i)
        kd.balance()
        
        copied_count = 0
        
        for source_name, target_name in segment_pairs.items():
            if source_name not in obj.vertex_groups:
                continue
            
            source_vg = obj.vertex_groups[source_name]
            
            if target_name in obj.vertex_groups:
                target_vg = obj.vertex_groups[target_name]
            else:
                target_vg = obj.vertex_groups.new(name=target_name)
            
            source_verts = []
            for v in mesh.vertices:
                for g in v.groups:
                    if g.group == source_vg.index and g.weight > 0.5:
                        source_verts.append((v.index, v.co.copy(), g.weight))
                        break
            
            for idx, co, weight in source_verts:
                mirrored_co = co.copy()
                mirrored_co[axis_idx] = 2 * center[axis_idx] - co[axis_idx]
                
                found_co, found_idx, dist = kd.find(mirrored_co)
                
                if dist < 0.05:
                    target_vg.add([found_idx], weight, 'REPLACE')
                    copied_count += 1
        
        self.report({'INFO'}, f"Copied {copied_count} vertex assignments across symmetry")
        return {'FINISHED'}


classes = [
    PET_OT_detect_symmetry,
    PET_OT_mirror_selection,
    PET_OT_select_half,
    PET_OT_symmetrize_segments,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
