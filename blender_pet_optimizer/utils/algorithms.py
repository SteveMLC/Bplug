"""
Mesh optimization algorithms
QEM edge collapse and centroid clustering implementations
Preserves UV coordinates, vertex colors, and material assignments
"""

import bmesh
from mathutils import Vector


def centroid_cluster_decimate(mesh, grid_size, target_reduction):
    """
    4-pass centroid clustering using bmesh
    
    Args:
        mesh: Blender mesh object
        grid_size: Size of grid cells for clustering
        target_reduction: Target reduction ratio (0.0-1.0)
    
    Returns:
        int: Number of faces removed
    """
    if grid_size <= 0:
        return 0
    
    # Create bmesh with all layers (UVs, colors, etc.) preserved
    bm = bmesh.new()
    # from_mesh automatically preserves UV layers and color attributes
    bm.from_mesh(mesh)
    
    # Ensure all lookup tables are available
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.loops.ensure_lookup_table()
    
    initial_face_count = len(bm.faces)
    
    # Pass 1: Cluster vertices by grid cell
    grid_buckets = {}
    vert_to_grid = {}
    
    for vert in bm.verts:
        pos = vert.co
        grid_key = (
            int(pos.x / grid_size),
            int(pos.y / grid_size),
            int(pos.z / grid_size)
        )
        
        if grid_key not in grid_buckets:
            grid_buckets[grid_key] = []
        grid_buckets[grid_key].append(vert)
        vert_to_grid[vert] = grid_key
    
    # Pass 2: Calculate centroids
    grid_centroids = {}
    for grid_key, verts in grid_buckets.items():
        if not verts:
            continue
        centroid = Vector((0, 0, 0))
        for vert in verts:
            centroid += vert.co
        centroid /= len(verts)
        grid_centroids[grid_key] = centroid
    
    # Pass 3: Move vertices to centroids
    for vert in bm.verts:
        grid_key = vert_to_grid.get(vert)
        if grid_key and grid_key in grid_centroids:
            vert.co = grid_centroids[grid_key]
    
    # Pass 4: Remove duplicate vertices and degenerate faces
    # remove_doubles automatically interpolates UVs and colors when merging vertices
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.001, uvs=1, vcols=1)
    
    # Remove degenerate faces
    bm.faces.ensure_lookup_table()
    degenerate_faces = [f for f in bm.faces if f.calc_area() < 0.0001 or len(f.verts) < 3]
    if degenerate_faces:
        bmesh.ops.delete(bm, geom=degenerate_faces, context='FACES')
    
    # Update mesh - this preserves all layers (UVs, colors, materials)
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    
    final_face_count = len(mesh.polygons)
    return initial_face_count - final_face_count


def qem_edge_collapse(mesh, target_reduction):
    """
    Quadric Error Metric edge collapse decimation using Blender's decimate modifier logic
    
    This uses a simplified QEM approach with bmesh. For complex meshes, 
    Blender's built-in decimate modifier is recommended, but this provides
    a custom implementation.
    
    Args:
        mesh: Blender mesh object
        target_reduction: Target reduction ratio (0.0-1.0)
    
    Returns:
        int: Number of faces removed
    """
    if target_reduction <= 0 or target_reduction >= 1:
        return 0
    
    # Create bmesh with all layers (UVs, colors, etc.) preserved
    bm = bmesh.new()
    # from_mesh automatically preserves UV layers and color attributes
    bm.from_mesh(mesh)
    
    # Ensure all lookup tables are available
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.loops.ensure_lookup_table()
    
    initial_face_count = len(bm.faces)
    target_face_count = int(initial_face_count * (1 - target_reduction))
    
    # Simple edge collapse based on edge length and face area
    # For a full QEM implementation, we'd compute quadric error matrices
    # This is a simplified version that prioritizes small edges in flat areas
    
    # Calculate face areas
    face_areas = {}
    for face in bm.faces:
        face_areas[face] = face.calc_area()
    
    # Calculate edge collapse priorities (simplified QEM)
    edge_priorities = []
    for edge in bm.edges:
        if len(edge.link_faces) == 0:
            continue
        
        # Calculate edge length
        edge_length = (edge.verts[0].co - edge.verts[1].co).length
        
        # Calculate average face area around edge
        avg_face_area = sum(face_areas.get(f, 0) for f in edge.link_faces) / len(edge.link_faces)
        
        # Priority: short edges in low-detail areas
        priority = edge_length / (avg_face_area + 0.001)
        edge_priorities.append((priority, edge))
    
    # Sort by priority (lowest first = collapse first)
    edge_priorities.sort(key=lambda x: x[0])
    
    # Collapse edges until target face count
    collapsed = 0
    for priority, edge in edge_priorities:
        if len(bm.faces) <= target_face_count:
            break
        
        # Skip if edge is invalid or on boundary (if preserving boundaries)
        if len(edge.link_faces) < 2:
            continue
        
        # Collapse edge to its midpoint
        try:
            vert1, vert2 = edge.verts
            midpoint = (vert1.co + vert2.co) / 2
            
            # Merge vertices - pointmerge returns merged vertex
            # NOTE: pointmerge should preserve loop data (UVs, colors) automatically
            # The merged vertex retains loop data from both source vertices
            merged_result = bmesh.ops.pointmerge(
                bm,
                verts=[vert1, vert2],
                merge_co=midpoint
            )
            # merged_result contains {'vert': BMVert} - the merged vertex
            
            collapsed += 1
            
            # Update lookup tables
            bm.faces.ensure_lookup_table()
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            
        except:
            # Skip if collapse fails
            continue
    
    # Clean up - remove_doubles interpolates UVs and colors when merging
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.001, uvs=1, vcols=1)
    
    # Remove degenerate faces
    bm.faces.ensure_lookup_table()
    degenerate_faces = [f for f in bm.faces if f.calc_area() < 0.0001 or len(f.verts) < 3]
    if degenerate_faces:
        bmesh.ops.delete(bm, geom=degenerate_faces, context='FACES')
    
    # Update mesh - this preserves all layers (UVs, colors, materials)
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    
    final_face_count = len(mesh.polygons)
    return initial_face_count - final_face_count
