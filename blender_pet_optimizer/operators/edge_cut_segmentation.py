"""
Edge-loop based segment marking for efficient batch workflow
Select edge loops as cut boundaries, mark segments, remaining becomes body
Optimized for AI-generated 3D models (Huanyuan, etc.)
"""

import bpy
import bmesh
from bpy.types import Operator
from bpy.props import EnumProperty, BoolProperty, StringProperty
from mathutils import Vector


class PET_OT_mark_segment_cut(Operator):
    """Mark selected edges as a segment cut boundary"""
    bl_idname = "pet.mark_segment_cut"
    bl_label = "Mark Segment Cut"
    bl_options = {'REGISTER', 'UNDO'}
    
    segment_name: EnumProperty(
        name="Segment Name",
        description="Name of the segment being cut off",
        items=[
            ('head', "Head", "Mark as head segment"),
            ('leg_front_l', "Front Left Leg", "Mark as front left leg"),
            ('leg_front_r', "Front Right Leg", "Mark as front right leg"),
            ('leg_back_l', "Back Left Leg", "Mark as back left leg"),
            ('leg_back_r', "Back Right Leg", "Mark as back right leg"),
            ('tail', "Tail", "Mark as tail segment"),
            ('wing_l', "Left Wing", "Mark as left wing"),
            ('wing_r', "Right Wing", "Mark as right wing"),
        ],
        default='head'
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode != 'EDIT_MESH':
            self.report({'ERROR'}, "Please switch to Edit mode and select edges")
            return {'CANCELLED'}
        
        bm = bmesh.from_edit_mesh(obj.data)
        selected_edges = [e for e in bm.edges if e.select]
        
        if not selected_edges:
            self.report({'ERROR'}, "Please select edges to mark as cut boundary")
            return {'CANCELLED'}
        
        cut_layer = bm.edges.layers.int.get("pet_segment_cut")
        if not cut_layer:
            cut_layer = bm.edges.layers.int.new("pet_segment_cut")
        
        name_layer = bm.edges.layers.string.get("pet_segment_name")
        if not name_layer:
            name_layer = bm.edges.layers.string.new("pet_segment_name")
        
        segment_id = self._get_segment_id(self.segment_name)
        
        for edge in selected_edges:
            edge[cut_layer] = segment_id
            edge[name_layer] = self.segment_name.encode('utf-8')
        
        bmesh.update_edit_mesh(obj.data)
        
        if "pet_marked_segments" not in obj:
            obj["pet_marked_segments"] = []
        
        marked = list(obj.get("pet_marked_segments", []))
        if self.segment_name not in marked:
            marked.append(self.segment_name)
            obj["pet_marked_segments"] = marked
        
        self.report({'INFO'}, f"Marked {len(selected_edges)} edges as '{self.segment_name}' cut boundary")
        return {'FINISHED'}
    
    def _get_segment_id(self, name):
        segment_ids = {
            'head': 1,
            'leg_front_l': 2,
            'leg_front_r': 3,
            'leg_back_l': 4,
            'leg_back_r': 5,
            'tail': 6,
            'wing_l': 7,
            'wing_r': 8,
        }
        return segment_ids.get(name, 0)


class PET_OT_clear_segment_cuts(Operator):
    """Clear all segment cut markings"""
    bl_idname = "pet.clear_segment_cuts"
    bl_label = "Clear Segment Cuts"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        was_in_edit = context.mode == 'EDIT_MESH'
        if was_in_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        cut_layer = bm.edges.layers.int.get("pet_segment_cut")
        if cut_layer:
            bm.edges.layers.int.remove(cut_layer)
        
        name_layer = bm.edges.layers.string.get("pet_segment_name")
        if name_layer:
            bm.edges.layers.string.remove(name_layer)
        
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        
        if "pet_marked_segments" in obj:
            del obj["pet_marked_segments"]
        
        if was_in_edit:
            bpy.ops.object.mode_set(mode='EDIT')
        
        self.report({'INFO'}, "Cleared all segment cut markings")
        return {'FINISHED'}


class PET_OT_apply_segment_cuts(Operator):
    """Apply marked cuts to create vertex groups (remaining mesh becomes body)"""
    bl_idname = "pet.apply_segment_cuts"
    bl_label = "Apply Segment Cuts"
    bl_options = {'REGISTER', 'UNDO'}
    
    keep_markings: BoolProperty(
        name="Keep Markings",
        description="Keep edge markings after applying",
        default=False
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode == 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        mesh = obj.data
        
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        cut_layer = bm.edges.layers.int.get("pet_segment_cut")
        name_layer = bm.edges.layers.string.get("pet_segment_name")
        
        if not cut_layer:
            self.report({'ERROR'}, "No segment cuts marked. Please mark cuts first.")
            bm.free()
            return {'CANCELLED'}
        
        cut_edges = {}
        for edge in bm.edges:
            segment_id = edge[cut_layer]
            if segment_id > 0:
                segment_name = edge[name_layer].decode('utf-8') if name_layer else f"segment_{segment_id}"
                if segment_name not in cut_edges:
                    cut_edges[segment_name] = []
                cut_edges[segment_name].append(edge)
        
        if not cut_edges:
            self.report({'ERROR'}, "No segment cuts found")
            bm.free()
            return {'CANCELLED'}
        
        obj.vertex_groups.clear()
        
        all_verts = set(range(len(bm.verts)))
        segment_verts = {}
        
        for segment_name, edges in cut_edges.items():
            boundary_verts = set()
            for edge in edges:
                for vert in edge.verts:
                    boundary_verts.add(vert.index)
            
            segment_verts[segment_name] = self._flood_fill_segment(
                bm, boundary_verts, all_verts, segment_name
            )
        
        body_verts = all_verts.copy()
        for verts in segment_verts.values():
            body_verts -= verts
        
        for segment_name, verts in segment_verts.items():
            if verts:
                vg = obj.vertex_groups.new(name=segment_name)
                vg.add(list(verts), 1.0, 'REPLACE')
        
        if body_verts:
            body_vg = obj.vertex_groups.new(name="body")
            body_vg.add(list(body_verts), 1.0, 'REPLACE')
        
        if not self.keep_markings:
            if cut_layer:
                bm.edges.layers.int.remove(cut_layer)
            if name_layer:
                bm.edges.layers.string.remove(name_layer)
            if "pet_marked_segments" in obj:
                del obj["pet_marked_segments"]
        
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        
        total_segments = len(segment_verts) + (1 if body_verts else 0)
        self.report({'INFO'}, f"Created {total_segments} vertex groups from segment cuts")
        return {'FINISHED'}
    
    def _flood_fill_segment(self, bm, boundary_verts, all_verts, segment_name):
        """Flood fill from boundary to find segment vertices (away from body center)"""
        segment_name_lower = segment_name.lower()
        
        mesh_center = Vector((0, 0, 0))
        for vert in bm.verts:
            mesh_center += vert.co
        mesh_center /= len(bm.verts)
        
        min_z = min(v.co.z for v in bm.verts)
        max_z = max(v.co.z for v in bm.verts)
        min_y = min(v.co.y for v in bm.verts)
        max_y = max(v.co.y for v in bm.verts)
        
        seed_verts = set()
        for boundary_idx in boundary_verts:
            vert = bm.verts[boundary_idx]
            for edge in vert.link_edges:
                other_vert = edge.other_vert(vert)
                if other_vert.index not in boundary_verts:
                    is_appendage_side = False
                    
                    if 'head' in segment_name_lower:
                        is_appendage_side = other_vert.co.y > vert.co.y or other_vert.co.z > vert.co.z
                    elif 'leg' in segment_name_lower:
                        is_appendage_side = other_vert.co.z < vert.co.z
                    elif 'tail' in segment_name_lower:
                        is_appendage_side = other_vert.co.y < vert.co.y
                    elif 'wing' in segment_name_lower:
                        if '_l' in segment_name_lower:
                            is_appendage_side = other_vert.co.x > vert.co.x
                        else:
                            is_appendage_side = other_vert.co.x < vert.co.x
                    
                    if is_appendage_side:
                        seed_verts.add(other_vert.index)
        
        if not seed_verts:
            for boundary_idx in boundary_verts:
                vert = bm.verts[boundary_idx]
                for edge in vert.link_edges:
                    other_vert = edge.other_vert(vert)
                    if other_vert.index not in boundary_verts:
                        to_center = (mesh_center - other_vert.co).length
                        from_center = (mesh_center - vert.co).length
                        if to_center > from_center:
                            seed_verts.add(other_vert.index)
        
        if not seed_verts:
            return boundary_verts
        
        segment = boundary_verts.copy()
        to_visit = list(seed_verts)
        visited = set()
        
        while to_visit:
            vert_idx = to_visit.pop()
            if vert_idx in visited or vert_idx in boundary_verts:
                continue
            
            visited.add(vert_idx)
            segment.add(vert_idx)
            
            vert = bm.verts[vert_idx]
            for edge in vert.link_edges:
                other_vert = edge.other_vert(vert)
                if other_vert.index not in visited and other_vert.index not in boundary_verts:
                    to_visit.append(other_vert.index)
        
        return segment


class PET_OT_select_segment_edges(Operator):
    """Select edges marked for a specific segment"""
    bl_idname = "pet.select_segment_edges"
    bl_label = "Select Segment Edges"
    bl_options = {'REGISTER', 'UNDO'}
    
    segment_name: StringProperty(
        name="Segment Name",
        description="Name of segment to select edges for",
        default=""
    )
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')
        
        bm = bmesh.from_edit_mesh(obj.data)
        
        cut_layer = bm.edges.layers.int.get("pet_segment_cut")
        name_layer = bm.edges.layers.string.get("pet_segment_name")
        
        if not cut_layer or not name_layer:
            self.report({'WARNING'}, "No segment cuts marked")
            return {'CANCELLED'}
        
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type='EDGE')
        
        count = 0
        for edge in bm.edges:
            if edge[cut_layer] > 0:
                stored_name = edge[name_layer].decode('utf-8')
                if not self.segment_name or stored_name == self.segment_name:
                    edge.select = True
                    count += 1
        
        bmesh.update_edit_mesh(obj.data)
        
        self.report({'INFO'}, f"Selected {count} edges")
        return {'FINISHED'}


class PET_OT_preview_segment_cuts(Operator):
    """Preview how segments will be split based on current edge markings"""
    bl_idname = "pet.preview_segment_cuts"
    bl_label = "Preview Segment Cuts"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object")
            return {'CANCELLED'}
        
        if context.mode == 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        
        cut_layer = bm.edges.layers.int.get("pet_segment_cut")
        
        if not cut_layer:
            self.report({'WARNING'}, "No segment cuts marked. Mark edge loops first.")
            bm.free()
            return {'CANCELLED'}
        
        marked_segments = obj.get("pet_marked_segments", [])
        cut_count = sum(1 for e in bm.edges if e[cut_layer] > 0)
        
        bm.free()
        
        info = f"Marked segments: {', '.join(marked_segments) if marked_segments else 'None'}. "
        info += f"Cut edges: {cut_count}. Remaining mesh will become 'body'."
        
        self.report({'INFO'}, info)
        return {'FINISHED'}


classes = [
    PET_OT_mark_segment_cut,
    PET_OT_clear_segment_cuts,
    PET_OT_apply_segment_cuts,
    PET_OT_select_segment_edges,
    PET_OT_preview_segment_cuts,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
