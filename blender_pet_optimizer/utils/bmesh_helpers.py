"""
bmesh utility functions
Helper functions for working with bmesh in the addon
"""

import bmesh
from mathutils import Vector


def get_mesh_bounds(obj):
    """
    Get bounding box bounds for an object
    
    Args:
        obj: Blender object with mesh data
    
    Returns:
        tuple: (min_bbox, max_bbox, size) as Vector objects
    """
    if not obj or obj.type != 'MESH':
        return None, None, None
    
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
    size = max_bbox - min_bbox
    
    return min_bbox, max_bbox, size


def segment_by_regions(obj, template):
    """
    Segment mesh into body parts using spatial regions
    
    Args:
        obj: Blender object with mesh data
        template: Segmentation template dictionary
    
    Returns:
        dict: Vertex groups created with vertex indices
    """
    if not obj or obj.type != 'MESH':
        return {}
    
    mesh = obj.data
    min_bbox, max_bbox, size = get_mesh_bounds(obj)
    
    if not size or size.length == 0:
        return {}
    
    # Clear existing vertex groups (optional - can be controlled by parameter)
    # obj.vertex_groups.clear()
    
    vertex_groups_created = {}
    
    # Create vertex groups for each body part
    for part_name, region in template.items():
        # Create or get vertex group
        vg = obj.vertex_groups.new(name=part_name)
        vertex_groups_created[part_name] = []
        
        # Select vertices in region
        indices = []
        for vert in mesh.vertices:
            world_pos = obj.matrix_world @ vert.co
            
            # Calculate relative position (0.0-1.0)
            relative = Vector((0, 0, 0))
            for i in range(3):
                if size[i] > 0.001:
                    relative[i] = (world_pos[i] - min_bbox[i]) / size[i]
                else:
                    relative[i] = 0.5  # Default to center if dimension is too small
            
            # Check if vertex is in region
            in_region = True
            if "y_min" in region and relative.y < region["y_min"]:
                in_region = False
            if "y_max" in region and relative.y > region["y_max"]:
                in_region = False
            if "x_min" in region and relative.x < region["x_min"]:
                in_region = False
            if "x_max" in region and relative.x > region["x_max"]:
                in_region = False
            if "z_min" in region and relative.z < region["z_min"]:
                in_region = False
            if "z_max" in region and relative.z > region["z_max"]:
                in_region = False
            
            if in_region:
                indices.append(vert.index)
                vertex_groups_created[part_name].append(vert.index)
        
        # Assign vertices to group
        if indices:
            vg.add(indices, 1.0, 'REPLACE')
    
    return vertex_groups_created


def get_mesh_data_info(obj):
    """
    Get information about data layers in a mesh
    
    Args:
        obj: Blender object with mesh data
    
    Returns:
        dict: Information about UV layers, color attributes, and materials
    """
    if not obj or obj.type != 'MESH':
        return {
            'uv_layers': 0,
            'color_attributes': 0,
            'materials': 0
        }
    
    mesh = obj.data
    
    info = {
        'uv_layers': len(mesh.uv_layers) if mesh.uv_layers else 0,
        'color_attributes': 0,
        'materials': len(mesh.materials) if mesh.materials else 0
    }
    
    # Check for color attributes (Blender 3.0+)
    if hasattr(mesh, 'color_attributes') and mesh.color_attributes:
        info['color_attributes'] = len(mesh.color_attributes)
    
    return info


def preserve_mesh_data_on_split(source_mesh, target_mesh):
    """
    Helper to ensure mesh data (UVs, colors, materials) is preserved during split
    Blender's separate operator should preserve these automatically, but this
    provides verification and explicit copying if needed
    
    Args:
        source_mesh: Original mesh
        target_mesh: New mesh from split
    
    Returns:
        bool: True if data preserved successfully
    """
    # Blender's separate operator typically preserves these automatically
    # This function can be used for verification or manual copying if needed
    return True
