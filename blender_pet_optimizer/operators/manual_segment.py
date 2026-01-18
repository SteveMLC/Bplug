import bpy
from bpy.types import Operator
from bpy.props import StringProperty, FloatProperty, IntProperty, BoolProperty, EnumProperty
import bmesh


class PET_OT_assign_selection_to_segment(Operator):
    """Assign current vertex/face selection to a named segment"""
    bl_idname = "pet.assign_selection_to_segment"
    bl_label = "Assign to Segment"
    bl_options = {'REGISTER', 'UNDO'}
    
    segment_name: StringProperty(
        name="Segment Name",
        description="Name for this segment (e.g., Head, Leg_Front_L)",
        default="Head"
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode with vertices selected")
            return {'CANCELLED'}
        
        bm = bmesh.from_edit_mesh(obj.data)
        selected_verts = [v for v in bm.verts if v.select]
        
        if not selected_verts:
            self.report({'ERROR'}, "No vertices selected")
            return {'CANCELLED'}
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        group_name = f"Segment_{self.segment_name}"
        if group_name in obj.vertex_groups:
            vg = obj.vertex_groups[group_name]
        else:
            vg = obj.vertex_groups.new(name=group_name)
        
        vert_indices = [v.index for v in selected_verts]
        vg.add(vert_indices, 1.0, 'REPLACE')
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        self.report({'INFO'}, f"Assigned {len(vert_indices)} vertices to '{self.segment_name}'")
        return {'FINISHED'}


class PET_OT_select_segment(Operator):
    """Select vertices belonging to a segment"""
    bl_idname = "pet.select_segment"
    bl_label = "Select Segment"
    bl_options = {'REGISTER', 'UNDO'}
    
    segment_name: StringProperty(
        name="Segment",
        description="Segment to select"
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        group_name = f"Segment_{self.segment_name}"
        if group_name not in obj.vertex_groups:
            self.report({'ERROR'}, f"Segment '{self.segment_name}' not found")
            return {'CANCELLED'}
        
        was_edit = obj.mode == 'EDIT'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        
        vg_index = obj.vertex_groups[group_name].index
        
        for v in obj.data.vertices:
            v.select = False
            for g in v.groups:
                if g.group == vg_index and g.weight > 0.5:
                    v.select = True
                    break
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        return {'FINISHED'}


class PET_OT_grow_selection(Operator):
    """Grow selection by specified number of rings"""
    bl_idname = "pet.grow_selection"
    bl_label = "Grow Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    iterations: IntProperty(
        name="Rings",
        description="Number of edge rings to grow",
        default=1,
        min=1,
        max=50
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode on a mesh")
            return {'CANCELLED'}
        
        for _ in range(self.iterations):
            bpy.ops.mesh.select_more()
        
        return {'FINISHED'}


class PET_OT_shrink_selection(Operator):
    """Shrink selection by specified number of rings"""
    bl_idname = "pet.shrink_selection"
    bl_label = "Shrink Selection"
    bl_options = {'REGISTER', 'UNDO'}
    
    iterations: IntProperty(
        name="Rings",
        description="Number of edge rings to shrink",
        default=1,
        min=1,
        max=50
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode on a mesh")
            return {'CANCELLED'}
        
        for _ in range(self.iterations):
            bpy.ops.mesh.select_less()
        
        return {'FINISHED'}


class PET_OT_smooth_selection_boundary(Operator):
    """Smooth the boundary of current selection for cleaner cuts"""
    bl_idname = "pet.smooth_selection_boundary"
    bl_label = "Smooth Boundary"
    bl_options = {'REGISTER', 'UNDO'}
    
    iterations: IntProperty(
        name="Iterations",
        description="Smoothing iterations",
        default=2,
        min=1,
        max=10
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode on a mesh")
            return {'CANCELLED'}
        
        for _ in range(self.iterations):
            bpy.ops.mesh.select_less()
            bpy.ops.mesh.select_more()
        
        self.report({'INFO'}, "Smoothed selection boundary")
        return {'FINISHED'}


class PET_OT_select_linked_flat(Operator):
    """Select linked flat faces from current selection - good for organic surfaces"""
    bl_idname = "pet.select_linked_flat"
    bl_label = "Select Linked Flat"
    bl_options = {'REGISTER', 'UNDO'}
    
    angle_threshold: FloatProperty(
        name="Angle Threshold",
        description="Maximum angle between faces to consider linked",
        default=15.0,
        min=0.0,
        max=180.0,
        subtype='ANGLE'
    )
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH' or obj.mode != 'EDIT':
            self.report({'ERROR'}, "Must be in Edit mode on a mesh")
            return {'CANCELLED'}
        
        import math
        bpy.ops.mesh.select_linked(delimit={'NORMAL'})
        
        return {'FINISHED'}


class PET_OT_invert_and_assign_body(Operator):
    """Invert selection and assign remaining to Body segment"""
    bl_idname = "pet.invert_assign_body"
    bl_label = "Assign Remaining as Body"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        bpy.ops.mesh.select_all(action='SELECT')
        
        bpy.ops.object.mode_set(mode='OBJECT')
        
        segment_groups = [vg for vg in obj.vertex_groups if vg.name.startswith("Segment_")]
        
        assigned_verts = set()
        for vg in segment_groups:
            if vg.name == "Segment_Body":
                continue
            vg_index = vg.index
            for v in obj.data.vertices:
                for g in v.groups:
                    if g.group == vg_index and g.weight > 0.5:
                        assigned_verts.add(v.index)
        
        body_verts = [v.index for v in obj.data.vertices if v.index not in assigned_verts]
        
        if "Segment_Body" in obj.vertex_groups:
            body_group = obj.vertex_groups["Segment_Body"]
        else:
            body_group = obj.vertex_groups.new(name="Segment_Body")
        
        body_group.add(body_verts, 1.0, 'REPLACE')
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        self.report({'INFO'}, f"Assigned {len(body_verts)} vertices to Body ({len(assigned_verts)} in other segments)")
        return {'FINISHED'}


class PET_OT_quick_decimate(Operator):
    """Quickly reduce mesh complexity for easier selection"""
    bl_idname = "pet.quick_decimate"
    bl_label = "Quick Decimate"
    bl_options = {'REGISTER', 'UNDO'}
    
    ratio: FloatProperty(
        name="Ratio",
        description="Target polygon ratio (0.1 = 10% of original)",
        default=0.1,
        min=0.01,
        max=1.0
    )
    
    keep_original: BoolProperty(
        name="Keep Original",
        description="Create decimated copy, keep original mesh",
        default=True
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        original_faces = len(obj.data.polygons)
        
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        if self.keep_original:
            bpy.ops.object.duplicate()
            obj = context.active_object
            obj.name = obj.name.replace(".001", "_lowpoly")
        
        mod = obj.modifiers.new(name="QuickDecimate", type='DECIMATE')
        mod.ratio = self.ratio
        bpy.ops.object.modifier_apply(modifier=mod.name)
        
        new_faces = len(obj.data.polygons)
        reduction = (1 - new_faces / original_faces) * 100
        
        self.report({'INFO'}, f"Reduced from {original_faces:,} to {new_faces:,} faces ({reduction:.1f}% reduction)")
        return {'FINISHED'}


class PET_OT_preview_segments(Operator):
    """Preview all assigned segments with colors"""
    bl_idname = "pet.preview_segments"
    bl_label = "Preview Segments"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        if not obj.data.vertex_colors:
            obj.data.vertex_colors.new(name="SegmentPreview")
        
        color_layer = obj.data.vertex_colors.active
        
        segment_colors = {
            'Head': (1.0, 0.3, 0.3, 1.0),
            'Body': (0.3, 1.0, 0.3, 1.0),
            'Leg_Front_L': (0.3, 0.3, 1.0, 1.0),
            'Leg_Front_R': (0.3, 0.6, 1.0, 1.0),
            'Leg_Back_L': (1.0, 0.6, 0.3, 1.0),
            'Leg_Back_R': (1.0, 0.8, 0.3, 1.0),
            'Tail': (0.8, 0.3, 0.8, 1.0),
            'Wing_L': (0.3, 0.8, 0.8, 1.0),
            'Wing_R': (0.5, 0.9, 0.9, 1.0),
        }
        
        vert_segment = {}
        for vg in obj.vertex_groups:
            if vg.name.startswith("Segment_"):
                segment_name = vg.name[8:]
                vg_index = vg.index
                for v in obj.data.vertices:
                    for g in v.groups:
                        if g.group == vg_index and g.weight > 0.5:
                            vert_segment[v.index] = segment_name
        
        for poly in obj.data.polygons:
            for loop_index in poly.loop_indices:
                vert_index = obj.data.loops[loop_index].vertex_index
                segment = vert_segment.get(vert_index, None)
                if segment and segment in segment_colors:
                    color_layer.data[loop_index].color = segment_colors[segment]
                else:
                    color_layer.data[loop_index].color = (0.5, 0.5, 0.5, 1.0)
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'SOLID'
                        space.shading.color_type = 'VERTEX'
        
        self.report({'INFO'}, f"Previewing {len(vert_segment)} vertices across segments")
        return {'FINISHED'}


class PET_OT_clear_segment(Operator):
    """Remove a segment vertex group"""
    bl_idname = "pet.clear_segment"
    bl_label = "Clear Segment"
    bl_options = {'REGISTER', 'UNDO'}
    
    segment_name: StringProperty(name="Segment")
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        
        group_name = f"Segment_{self.segment_name}"
        if group_name in obj.vertex_groups:
            obj.vertex_groups.remove(obj.vertex_groups[group_name])
            self.report({'INFO'}, f"Cleared segment '{self.segment_name}'")
        
        return {'FINISHED'}


class PET_OT_split_by_segments(Operator):
    """Split mesh into separate objects based on assigned segments"""
    bl_idname = "pet.split_by_segments"
    bl_label = "Split by Segments"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        segment_groups = [vg for vg in obj.vertex_groups if vg.name.startswith("Segment_")]
        
        if not segment_groups:
            self.report({'ERROR'}, "No segments defined. Assign vertices to segments first.")
            return {'CANCELLED'}
        
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        base_name = obj.name
        created_objects = []
        
        for vg in segment_groups:
            segment_name = vg.name[8:]
            
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.duplicate()
            new_obj = context.active_object
            new_obj.name = f"{base_name}_{segment_name}"
            
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode='OBJECT')
            
            vg_index = new_obj.vertex_groups[vg.name].index
            for v in new_obj.data.vertices:
                in_group = False
                for g in v.groups:
                    if g.group == vg_index and g.weight > 0.5:
                        in_group = True
                        break
                v.select = not in_group
            
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.delete(type='VERT')
            bpy.ops.object.mode_set(mode='OBJECT')
            
            for old_vg in list(new_obj.vertex_groups):
                new_obj.vertex_groups.remove(old_vg)
            
            created_objects.append(new_obj.name)
        
        bpy.data.objects.remove(obj, do_unlink=True)
        
        self.report({'INFO'}, f"Created {len(created_objects)} segment objects: {', '.join(created_objects)}")
        return {'FINISHED'}


classes = [
    PET_OT_assign_selection_to_segment,
    PET_OT_select_segment,
    PET_OT_grow_selection,
    PET_OT_shrink_selection,
    PET_OT_smooth_selection_boundary,
    PET_OT_select_linked_flat,
    PET_OT_invert_assign_body,
    PET_OT_quick_decimate,
    PET_OT_preview_segments,
    PET_OT_clear_segment,
    PET_OT_split_by_segments,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
