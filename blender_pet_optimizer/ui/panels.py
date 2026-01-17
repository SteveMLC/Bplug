"""
UI panels for Pet Model Optimizer
N-panel interface for all addon operations
"""

import bpy
from bpy.types import Panel
from ..utils import bmesh_helpers


class PET_PT_main_panel(Panel):
    """Main panel for Pet Model Optimizer"""
    bl_label = "Pet Model Optimizer"
    bl_idname = "PET_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="Workflow: Segment → Optimize → Rig → Export")


class PET_PT_mesh_optimization(Panel):
    """Mesh optimization panel"""
    bl_label = "Mesh Optimization"
    bl_idname = "PET_PT_mesh_optimization"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Object selector
        row = layout.row()
        row.label(text="Object:")
        row.prop(context, "active_object", text="")
        
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return
        
        # Face count info
        face_count = len(obj.data.polygons) if obj.data.polygons else 0
        layout.label(text=f"Faces: {face_count:,}", icon='MESH_DATA')
        
        # Algorithm selection
        op = layout.operator("pet.optimize_mesh", text="Optimize Mesh")
        
        col = layout.column()
        col.prop(op, "algorithm", expand=True)
        
        # Reduction slider
        layout.prop(op, "reduction", slider=True)
        
        # Grid size (only for centroid clustering)
        if op.algorithm in ['AUTO', 'CENTROID']:
            layout.prop(op, "grid_size")


class PET_PT_segmentation(Panel):
    """Segmentation panel"""
    bl_label = "Segmentation"
    bl_idname = "PET_PT_segmentation"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return
        
        # Data preservation info
        data_info = bmesh_helpers.get_mesh_data_info(obj)
        if data_info['uv_layers'] > 0 or data_info['color_attributes'] > 0 or data_info['materials'] > 0:
            layout.separator()
            box = layout.box()
            box.label(text="Data to Preserve:", icon='INFO')
            if data_info['uv_layers'] > 0:
                box.label(text=f"  UV Layers: {data_info['uv_layers']}", icon='UV')
            if data_info['color_attributes'] > 0:
                box.label(text=f"  Vertex Colors: {data_info['color_attributes']}", icon='GROUP_VCOL')
            if data_info['materials'] > 0:
                box.label(text=f"  Materials: {data_info['materials']}", icon='MATERIAL')
        
        layout.separator()
        
        # Pet type selector
        op = layout.operator("pet.segment_model", text="Segment Model")
        layout.prop(op, "pet_type", expand=True)
        layout.prop(op, "clear_existing")
        layout.prop(op, "auto_split")
        
        # Split options (if vertex groups exist)
        if obj.vertex_groups and op.auto_split:
            layout.separator()
            split_op = layout.operator("pet.split_by_vertex_groups", text="Split Manually")
            split_op.create_pivots = True
            split_op.keep_original = True
            split_op.verify_data = True
            layout.prop(split_op, "keep_original")
            layout.prop(split_op, "verify_data")
            layout.prop(split_op, "create_pivots")
        
        if op.auto_split:
            layout.label(text="Will split into separate objects", icon='OUTLINER_OB_MESH')
        
        # Show existing vertex groups
        if obj.vertex_groups:
            layout.separator()
            layout.label(text=f"Vertex Groups: {len(obj.vertex_groups)}", icon='GROUP_VERTEX')
            box = layout.box()
            for vg in obj.vertex_groups:
                box.label(text=f"  • {vg.name}")
        
        # Pivot points info
        pivot_collection = None
        pivot_collection_name = f"{obj.name}_Pivots"
        for collection in bpy.data.collections:
            if collection.name == pivot_collection_name:
                pivot_collection = collection
                break
        
        if pivot_collection and len(pivot_collection.objects) > 0:
            layout.separator()
            layout.label(text=f"Pivot Points: {len(pivot_collection.objects)}", icon='EMPTY_ARROWS')
            box = layout.box()
            for pivot in pivot_collection.objects:
                if pivot.type == 'EMPTY' and 'pet_pivot_type' in pivot:
                    source = pivot.get("pet_source_part", "?")
                    target = pivot.get("pet_target_part", "?")
                    box.label(text=f"  {source} ↔ {target}")


class PET_PT_rigging(Panel):
    """Rigging panel"""
    bl_label = "Rigging"
    bl_idname = "PET_PT_rigging"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return
        
        if not obj.vertex_groups:
            layout.label(text="Segment model first", icon='INFO')
            return
        
        # Create armature operator
        op_create = layout.operator("pet.create_armature", text="Create Armature")
        layout.prop(op_create, "bone_prefix")
        layout.prop(op_create, "auto_weights")
        
        layout.separator()
        
        # Setup rig operator
        op_setup = layout.operator("pet.setup_rig", text="Setup Rig")
        
        # Check for existing armature
        has_armature = any(o.type == 'ARMATURE' and o.name.startswith(obj.name) 
                          for o in context.scene.objects)
        if has_armature:
            layout.label(text="Armature found", icon='CHECKMARK')


class PET_PT_standardization(Panel):
    """Standardization panel"""
    bl_label = "Standardization"
    bl_idname = "PET_PT_standardization"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected:
            layout.label(text="Select mesh objects", icon='INFO')
            return
        
        layout.label(text=f"{len(selected)} object(s) selected")
        
        # Standardize parts operator
        op = layout.operator("pet.standardize_parts", text="Standardize Selected Parts")
        layout.prop(op, "normalize_scale")
        layout.prop(op, "standardize_orientation")
        
        if op.normalize_scale:
            layout.prop(op, "reference_part")
        
        layout.separator()
        
        # Create attachments operator
        op_att = layout.operator("pet.create_attachments", text="Create Attachment Points")


class PET_PT_export(Panel):
    """Export panel"""
    bl_label = "Export"
    bl_idname = "PET_PT_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pet Optimizer"
    bl_parent_id = "PET_PT_main_panel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        # Export model operator
        op_export = layout.operator("pet.export_model", text="Export Model")
        layout.prop(op_export, "format", expand=True)
        layout.prop(op_export, "include_metadata")
        
        layout.separator()
        
        # Export part library operator
        op_lib = layout.operator("pet.export_part_library", text="Export Part Library")
        layout.prop(op_lib, "format", expand=True)


classes = [
    PET_PT_main_panel,
    PET_PT_mesh_optimization,
    PET_PT_segmentation,
    PET_PT_rigging,
    PET_PT_standardization,
    PET_PT_export,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
