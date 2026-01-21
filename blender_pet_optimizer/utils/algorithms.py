"""
Mesh optimization algorithms
QEM edge collapse and centroid clustering implementations
Preserves UV coordinates, vertex colors, and material assignments
"""

import bmesh
from mathutils import Vector
import math
import time


def centroid_cluster_decimate(mesh, grid_size, target_reduction, preserve_sharp_features=False):
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
    
    # Ensure core lookup tables are available
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    initial_face_count = len(bm.faces)
    
    # Pass 1: Cluster vertices by grid cell
    # Make effective grid size depend on requested reduction so that
    # smaller reductions keep cells tighter (less aggressive) and
    # larger reductions cluster more aggressively.
    tr = max(0.0, min(1.0, float(target_reduction)))
    # Map 0..1 -> 0.25..1.0 scaling factor
    #  - very small reduction ≈ 0.25 * grid_size (gentle)
    #  - large reduction ≈ 1.0 * grid_size (full strength)
    scale = 0.25 + 0.75 * tr
    effective_grid_size = grid_size * scale
    grid_buckets = {}
    vert_to_grid = {}
    
    for vert in bm.verts:
        pos = vert.co
        grid_key = (
            int(pos.x / effective_grid_size),
            int(pos.y / effective_grid_size),
            int(pos.z / effective_grid_size),
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
    # remove_doubles automatically interpolates data when merging vertices
    # Note: modern Blender no longer accepts uvs/vcols flags here.
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.001)
    
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


def qem_edge_collapse(mesh, target_reduction, preserve_sharp_features=False):
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
    
    # Ensure core lookup tables are available
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    initial_face_count = len(bm.faces)
    target_face_count = int(initial_face_count * (1 - target_reduction))
    
    # Simple edge collapse based on edge length, face area, and local curvature.
    # For a full QEM implementation, we'd compute quadric error matrices.
    # This version prioritizes small edges in flat, low-detail regions and
    # can optionally preserve sharp creases, seams, and boundaries.
    
    # Time-bounded processing to avoid freezing on very dense meshes
    start_time = time.time()
    TIME_LIMIT_SECONDS = 3.0
    
    # Calculate face areas
    face_areas = {}
    for face in bm.faces:
        face_areas[face] = face.calc_area()
    
    # Calculate edge collapse priorities (simplified QEM with curvature awareness)
    edge_priorities = []
    for edge in bm.edges:
        if time.time() - start_time > TIME_LIMIT_SECONDS:
            # Stop building priorities if we've spent too long; we'll still
            # collapse using the edges we've gathered so far.
            break
        if len(edge.link_faces) == 0:
            continue
        
        # Protect obvious seams and outer boundaries when requested
        if preserve_sharp_features:
            if getattr(edge, "seam", False):
                # UV / topology seam: strongly prefer to keep
                continue
            if len(edge.link_faces) < 2:
                # Boundary edge: keep to preserve silhouette
                continue
        
        # Calculate edge length
        edge_length = (edge.verts[0].co - edge.verts[1].co).length
        
        # Calculate average face area around edge
        avg_face_area = sum(face_areas.get(f, 0) for f in edge.link_faces) / len(edge.link_faces)
        
        # Base priority: short edges in low-detail areas
        priority = edge_length / (avg_face_area + 0.001)
        
        # Adjust priority using dihedral angle between adjacent faces.
        # Small angles (smooth areas) get LOWER priority (collapsed earlier),
        # large angles (sharp creases) get HIGHER priority (collapsed later).
        if len(edge.link_faces) == 2:
            f1, f2 = edge.link_faces
            try:
                angle = f1.normal.angle(f2.normal)
            except ValueError:
                angle = 0.0
            
            # Normalize angle to [0, 1] over [0, pi]
            normalized = max(0.0, min(1.0, angle / math.pi))
            
            # When preserving sharp features, exaggerate the effect
            if preserve_sharp_features:
                # Strongly increase priority on creases, decrease on flats
                crease_factor = 1.0 + 4.0 * normalized     # up to 5x on sharp bends
                flat_factor = 1.0 - 0.5 * (1.0 - normalized)  # down to 0.5x on flats
                priority *= crease_factor * flat_factor
            else:
                # Mild protection of creases even in normal mode
                crease_factor = 1.0 + 2.0 * normalized
                priority *= crease_factor
        
        edge_priorities.append((priority, edge))
    
    # Sort by priority (lowest first = collapse first)
    edge_priorities.sort(key=lambda x: x[0])
    
    # Collapse edges until target face count
    for priority, edge in edge_priorities:
        if time.time() - start_time > TIME_LIMIT_SECONDS:
            break
        if len(bm.faces) <= target_face_count:
            break
        
        # Skip if edge is invalid or on boundary (if preserving boundaries)
        if not edge.is_valid:
            continue
        if preserve_sharp_features and len(edge.link_faces) < 2:
            continue
        
        # Collapse edge to its midpoint
        try:
            vert1, vert2 = edge.verts
            midpoint = (vert1.co + vert2.co) / 2
            
            # Merge vertices - pointmerge returns merged vertex
            # NOTE: pointmerge should preserve loop data (UVs, colors) automatically
            # The merged vertex retains loop data from both source vertices
            bmesh.ops.pointmerge(
                bm,
                verts=[vert1, vert2],
                merge_co=midpoint
            )
            
            # Update lookup tables
            bm.faces.ensure_lookup_table()
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
        
        except Exception:
            # Skip if collapse fails
            continue
    
    # Clean up - remove_doubles interpolates data when merging
    # Note: modern Blender no longer accepts uvs/vcols flags here.
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.001)
    
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
