"""
Edge cleanup operators for post-split workflow
Smooths cut edges and prepares boundaries for filling
"""

import bpy
import bmesh
from bpy.types import Operator
from bpy.props import IntProperty, BoolProperty
from mathutils import Vector


def identify_separation_boundary_edges(bm, obj, tolerance=0.0001):
    """
    Identify edges that are actual separation boundaries (created during split operation).
    Only returns edges that match stored separation boundary info.
    
    Args:
        bm: bmesh object
        obj: Blender object (to check for stored boundary info)
        tolerance: Distance tolerance for matching vertex coordinates
    
    Returns:
        set: Set of bmesh edges that are separation boundaries
    """
    separation_edges = set()
    
    # Check if object has stored separation boundary info
    if "pet_separation_boundary_edges" not in obj:
        # No stored info - return empty set (fallback will be used)
        return separation_edges
    
    stored_boundaries = obj.get("pet_separation_boundary_edges", [])
    if not stored_boundaries:
        return separation_edges
    
    # Convert stored boundary coordinates back to Vectors for comparison
    stored_edges = []
    for boundary_pair in stored_boundaries:
        if len(boundary_pair) == 2:
            v1_co = Vector(boundary_pair[0])
            v2_co = Vector(boundary_pair[1])
            stored_edges.append((v1_co, v2_co))
    
    if not stored_edges:
        return separation_edges
    
    # Match edges in bmesh to stored boundary edges
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    
    for edge in bm.edges:
        v1_co = edge.verts[0].co
        v2_co = edge.verts[1].co
        
        # Check if this edge matches any stored boundary edge
        # Need to check both directions (v1-v2 and v2-v1)
        for stored_v1, stored_v2 in stored_edges:
            # Check forward direction
            dist1_forward = (v1_co - stored_v1).length
            dist2_forward = (v2_co - stored_v2).length
            
            # Check reverse direction
            dist1_reverse = (v1_co - stored_v2).length
            dist2_reverse = (v2_co - stored_v1).length
            
            # Match if both vertices are within tolerance (in either direction)
            if (dist1_forward < tolerance and dist2_forward < tolerance) or \
               (dist1_reverse < tolerance and dist2_reverse < tolerance):
                separation_edges.add(edge)
                break
    
    return separation_edges


def identify_separation_boundary_edges_fallback(bm, obj):
    """
    Fallback method: Identify edges that are likely separation boundaries.
    Used when stored boundary info is not available (backwards compatibility).
    
    Strategy:
    - Select boundary edges (edges with only one face)
    - Filter to edges that are at the "cut surface" (not internal holes)
    - This is less accurate but works for objects without stored info
    
    Args:
        bm: bmesh object
        obj: Blender object
    
    Returns:
        set: Set of bmesh edges that are likely separation boundaries
    """
    boundary_edges = set()
    
    # Get all boundary edges (edges with only one face)
    for edge in bm.edges:
        if len(edge.link_faces) == 1:
            boundary_edges.add(edge)
    
    # TODO: Could add additional filtering here if needed
    # For now, return all boundary edges as fallback
    # This matches the original behavior but may include false positives
    
    return boundary_edges


class PET_OT_smooth_cut_edges(Operator):
    """Smooth cut edges on selected split parts for cleaner boundaries"""
    bl_idname = "pet.smooth_cut_edges"
    bl_label = "Smooth Cut Edges"
    bl_options = {'REGISTER', 'UNDO'}
    
    iterations: IntProperty(
        name="Iterations",
        description="Number of smoothing iterations",
        default=2,
        min=1,
        max=10
    )
    
    smooth_factor: bpy.props.FloatProperty(
        name="Smooth Factor",
        description="How much to smooth (0.0 = no smoothing, 1.0 = full smoothing)",
        default=1.0,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )
    
    only_boundary: BoolProperty(
        name="Only Boundary Edges",
        description="Only smooth edges that are on boundaries (edges with only one face)",
        default=True
    )
    
    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'ERROR'}, "Please select mesh objects with cut edges to smooth")
            return {'CANCELLED'}
        
        total_edges_smoothed = 0
        processed_objects = 0
        
        for obj in selected_objects:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            # Select this object
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            # Enter edit mode
            bpy.ops.object.mode_set(mode='EDIT')
            
            # Identify actual separation boundary edges (created during split)
            bm = bmesh.from_edit_mesh(obj.data)
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            
            # Deselect all first
            for edge in bm.edges:
                edge.select = False
            
            # Get separation boundary edges (actual cuts from split operation)
            separation_edges = identify_separation_boundary_edges(bm, obj)
            
            # Fallback if no stored boundary info (backwards compatibility)
            if not separation_edges:
                separation_edges = identify_separation_boundary_edges_fallback(bm, obj)
            
            # Select separation edges
            boundary_edges = list(separation_edges)
            for edge in boundary_edges:
                edge.select = True
            
            # If not only_boundary, also select all other edges
            if not self.only_boundary:
                for edge in bm.edges:
                    if edge not in separation_edges:
                        edge.select = True
                        if edge not in boundary_edges:
                            boundary_edges.append(edge)
            
            if not boundary_edges:
                bmesh.update_edit_mesh(obj.data)
                bm.free()
                bpy.ops.object.mode_set(mode='OBJECT')
                continue
            
            total_edges_smoothed += len(boundary_edges)
            
            # Update edit mesh with selection
            bmesh.update_edit_mesh(obj.data)
            bm.free()
            
            # Apply smoothing iterations
            for i in range(self.iterations):
                # Use Blender's smooth operator
                # This smooths selected edges/vertices
                try:
                    bpy.ops.mesh.vertices_smooth(
                        factor=self.smooth_factor,
                        repeat=1
                    )
                except RuntimeError:
                    # If vertices_smooth fails, try alternative method
                    bpy.ops.mesh.select_mode(type='VERT')
                    bpy.ops.mesh.vertices_smooth(
                        factor=self.smooth_factor,
                        repeat=1
                    )
                    bpy.ops.mesh.select_mode(type='EDGE')
            
            # Return to object mode
            bpy.ops.object.mode_set(mode='OBJECT')
            processed_objects += 1
        
        # Restore selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_objects:
            obj.select_set(True)
        if selected_objects:
            context.view_layer.objects.active = selected_objects[0]
        
        if processed_objects > 0:
            self.report({'INFO'}, f"Smoothed {total_edges_smoothed} boundary edges on {processed_objects} object(s)")
        else:
            self.report({'WARNING'}, "No boundary edges found to smooth")
        
        return {'FINISHED'}


class PET_OT_select_cut_boundaries(Operator):
    """Select all boundary edges (cut surfaces) on selected objects"""
    bl_idname = "pet.select_cut_boundaries"
    bl_label = "Select Cut Boundaries"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'ERROR'}, "Please select mesh objects")
            return {'CANCELLED'}
        
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        total_edges = 0
        
        for obj in selected_objects:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            bpy.ops.object.mode_set(mode='EDIT')
            
            bm = bmesh.from_edit_mesh(obj.data)
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            
            # Deselect all first
            for edge in bm.edges:
                edge.select = False
            
            # Get actual separation boundary edges (cuts from split operation)
            separation_edges = identify_separation_boundary_edges(bm, obj)
            
            # Fallback if no stored boundary info (backwards compatibility)
            if not separation_edges:
                separation_edges = identify_separation_boundary_edges_fallback(bm, obj)
            
            # Select separation edges
            boundary_count = len(separation_edges)
            for edge in separation_edges:
                edge.select = True
            
            total_edges += boundary_count
            
            bmesh.update_edit_mesh(obj.data)
            bm.free()
            
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Restore selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected_objects:
            obj.select_set(True)
        if selected_objects:
            context.view_layer.objects.active = selected_objects[0]
            bpy.ops.object.mode_set(mode='EDIT')
        
        self.report({'INFO'}, f"Selected {total_edges} boundary edges on {len(selected_objects)} object(s)")
        return {'FINISHED'}


classes = [
    PET_OT_smooth_cut_edges,
    PET_OT_select_cut_boundaries,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
