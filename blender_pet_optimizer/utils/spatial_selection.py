"""
Spatial Selection Algorithms for Manual Part Selection

Provides intelligent vertex selection based on part type (head, leg, tail, wing).
Uses BFS expansion with shape detection and connection analysis to auto-select
vertices belonging to specific body parts.
"""

import bmesh
from mathutils import Vector
from collections import deque
import math


def calculate_local_curvature(bm, vert_idx, radius=2):
    """
    Calculate local curvature around a vertex by analyzing neighbor normals.
    Higher curvature indicates edges/protrusions, lower indicates flat surfaces.
    
    Args:
        bm: bmesh object
        vert_idx: Index of vertex to analyze
        radius: Number of edge hops to consider
        
    Returns:
        float: Curvature value (0.0 = flat, 1.0 = high curvature)
    """
    if vert_idx >= len(bm.verts):
        return 0.0
    
    vert = bm.verts[vert_idx]
    
    # Get neighbors within radius
    neighbors = set()
    current_level = {vert}
    
    for _ in range(radius):
        next_level = set()
        for v in current_level:
            for edge in v.link_edges:
                other = edge.other_vert(v)
                if other.index not in neighbors:
                    neighbors.add(other.index)
                    next_level.add(other)
        current_level = next_level
    
    if not neighbors:
        return 0.0
    
    # Calculate average normal deviation
    center_normal = vert.normal
    total_deviation = 0.0
    
    for neighbor_idx in neighbors:
        if neighbor_idx < len(bm.verts):
            neighbor_normal = bm.verts[neighbor_idx].normal
            # Dot product: 1.0 = same direction, 0.0 = perpendicular, -1.0 = opposite
            dot = center_normal.dot(neighbor_normal)
            deviation = 1.0 - max(0.0, dot)  # 0.0 = same direction, 1.0 = perpendicular
            total_deviation += deviation
    
    return total_deviation / len(neighbors)


def calculate_connection_ratio(bm, vertex_set, all_verts_set):
    """
    Calculate the connection ratio of a vertex set to the rest of the mesh.
    Lower ratio = more protrusion-like (narrow connection).
    
    Args:
        bm: bmesh object
        vertex_set: Set of vertex indices in the region
        all_verts_set: Set of all vertex indices in mesh
        
    Returns:
        float: Connection ratio (0.0 = isolated, 1.0 = fully connected)
    """
    if not vertex_set:
        return 1.0
    
    boundary_count = 0
    
    for vert_idx in vertex_set:
        if vert_idx >= len(bm.verts):
            continue
        vert = bm.verts[vert_idx]
        
        for edge in vert.link_edges:
            other = edge.other_vert(vert)
            if other.index not in vertex_set and other.index in all_verts_set:
                boundary_count += 1
                break
    
    return boundary_count / len(vertex_set) if vertex_set else 1.0


def detect_narrow_connection(bm, vertex_set, obj, threshold=0.3):
    """
    Detect if vertex set has a narrow connection to the rest of the mesh.
    Used to find body attachment points (neck, hip, shoulder, etc.)
    
    Args:
        bm: bmesh object
        vertex_set: Set of vertex indices
        obj: Blender object
        threshold: Connection ratio threshold (lower = narrower)
        
    Returns:
        tuple: (has_narrow_connection, connection_vertices)
    """
    if not vertex_set:
        return False, set()
    
    # Find boundary vertices (vertices connected to non-set vertices)
    boundary_verts = set()
    all_verts = set(range(len(bm.verts)))
    
    for vert_idx in vertex_set:
        if vert_idx >= len(bm.verts):
            continue
        vert = bm.verts[vert_idx]
        
        for edge in vert.link_edges:
            other = edge.other_vert(vert)
            if other.index not in vertex_set:
                boundary_verts.add(vert_idx)
                break
    
    # Calculate connection ratio
    connection_ratio = len(boundary_verts) / len(vertex_set) if vertex_set else 1.0
    
    return connection_ratio < threshold, boundary_verts


def get_vertex_distance_from_center(bm, vert_idx, center, obj):
    """
    Get distance of vertex from a center point in world space.
    
    Args:
        bm: bmesh object
        vert_idx: Vertex index
        center: Center point (Vector)
        obj: Blender object
        
    Returns:
        float: Distance from center
    """
    if vert_idx >= len(bm.verts):
        return float('inf')
    
    vert_world = obj.matrix_world @ bm.verts[vert_idx].co
    return (vert_world - center).length


def bfs_expand_with_constraints(bm, start_idx, obj, max_distance=None, 
                                 stop_at_narrow_connection=True,
                                 min_vertices=10, max_vertices=None,
                                 excluded_verts=None):
    """
    BFS expansion from start vertex with constraints.
    
    Args:
        bm: bmesh object
        start_idx: Starting vertex index
        obj: Blender object
        max_distance: Maximum distance from start (world space)
        stop_at_narrow_connection: Stop when narrow connection detected
        min_vertices: Minimum vertices to select
        max_vertices: Maximum vertices to select
        excluded_verts: Set of vertex indices to exclude
        
    Returns:
        set: Selected vertex indices
    """
    if start_idx >= len(bm.verts):
        return set()
    
    excluded = excluded_verts or set()
    selected = set()
    visited = set()
    queue = deque([start_idx])
    visited.add(start_idx)
    
    start_world = obj.matrix_world @ bm.verts[start_idx].co
    
    while queue:
        if max_vertices and len(selected) >= max_vertices:
            break
        
        current_idx = queue.popleft()
        
        if current_idx in excluded:
            continue
        
        # Check distance constraint
        if max_distance:
            dist = get_vertex_distance_from_center(bm, current_idx, start_world, obj)
            if dist > max_distance:
                continue
        
        selected.add(current_idx)
        
        # Check for narrow connection (stop condition)
        if stop_at_narrow_connection and len(selected) > min_vertices:
            has_narrow, _ = detect_narrow_connection(bm, selected, obj)
            if has_narrow:
                # We've reached a narrow connection point, stop expanding
                break
        
        # Add neighbors to queue
        if current_idx < len(bm.verts):
            vert = bm.verts[current_idx]
            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                if other.index not in visited and other.index not in excluded:
                    visited.add(other.index)
                    queue.append(other.index)
    
    return selected


def analyze_region_shape(bm, vertex_set, obj):
    """
    Analyze the shape of a vertex region.
    
    Args:
        bm: bmesh object
        vertex_set: Set of vertex indices
        obj: Blender object
        
    Returns:
        dict: Shape analysis with 'is_blocky', 'is_elongated', 'length_ratio', 'bounds'
    """
    if not vertex_set:
        return {
            'is_blocky': False,
            'is_elongated': False,
            'length_ratio': 1.0,
            'bounds': (Vector(), Vector()),
            'center': Vector(),
            'size': Vector()
        }
    
    # Calculate bounding box
    coords = [obj.matrix_world @ bm.verts[i].co for i in vertex_set if i < len(bm.verts)]
    
    if not coords:
        return {
            'is_blocky': False,
            'is_elongated': False,
            'length_ratio': 1.0,
            'bounds': (Vector(), Vector()),
            'center': Vector(),
            'size': Vector()
        }
    
    min_co = Vector((min(c.x for c in coords),
                    min(c.y for c in coords),
                    min(c.z for c in coords)))
    max_co = Vector((max(c.x for c in coords),
                    max(c.y for c in coords),
                    max(c.z for c in coords)))
    
    size = max_co - min_co
    center = (min_co + max_co) / 2
    
    # Calculate length ratio
    dims = sorted([size.x, size.y, size.z], reverse=True)
    if dims[1] + dims[2] > 0:
        length_ratio = dims[0] / ((dims[1] + dims[2]) / 2 + 0.001)
    else:
        length_ratio = 1.0
    
    # Classify shape
    is_blocky = length_ratio < 2.0  # Roughly cubic/spherical
    is_elongated = length_ratio > 2.5  # Long and thin
    
    return {
        'is_blocky': is_blocky,
        'is_elongated': is_elongated,
        'length_ratio': length_ratio,
        'bounds': (min_co, max_co),
        'center': center,
        'size': size
    }


def intelligent_select_head(start_vertex_idx, obj, bm):
    """
    Intelligently select head region starting from clicked vertex.
    
    Head characteristics:
    - Blocky/rounded shape (low length ratio)
    - Includes protrusions (ears, horns, nose)
    - Stops at neck (narrow connection to body)
    
    Args:
        start_vertex_idx: Starting vertex index (where user clicked)
        obj: Blender object
        bm: bmesh object
        
    Returns:
        set: Vertex indices belonging to head
    """
    if start_vertex_idx >= len(bm.verts):
        return set()
    
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    # Get mesh bounds for scale reference
    all_coords = [obj.matrix_world @ v.co for v in bm.verts]
    if not all_coords:
        return set()
    
    mesh_min = Vector((min(c.x for c in all_coords),
                      min(c.y for c in all_coords),
                      min(c.z for c in all_coords)))
    mesh_max = Vector((max(c.x for c in all_coords),
                      max(c.y for c in all_coords),
                      max(c.z for c in all_coords)))
    mesh_size = mesh_max - mesh_min
    mesh_diagonal = mesh_size.length
    
    # Head is typically 15-30% of total mesh size
    max_head_distance = mesh_diagonal * 0.35
    
    # Phase 1: Initial BFS expansion
    selected = set()
    visited = set()
    queue = deque([start_vertex_idx])
    visited.add(start_vertex_idx)
    
    start_world = obj.matrix_world @ bm.verts[start_vertex_idx].co
    
    while queue:
        current_idx = queue.popleft()
        
        if current_idx >= len(bm.verts):
            continue
        
        vert = bm.verts[current_idx]
        vert_world = obj.matrix_world @ vert.co
        
        # Distance check
        dist = (vert_world - start_world).length
        if dist > max_head_distance:
            continue
        
        selected.add(current_idx)
        
        # Add neighbors
        for edge in vert.link_edges:
            other = edge.other_vert(vert)
            if other.index not in visited:
                visited.add(other.index)
                queue.append(other.index)
        
        # Check for narrow connection (neck detection)
        if len(selected) > 50:  # Only check after initial expansion
            shape = analyze_region_shape(bm, selected, obj)
            if shape['is_blocky']:
                # Head-like shape found, check for neck
                has_narrow, boundary = detect_narrow_connection(bm, selected, obj, threshold=0.25)
                if has_narrow and len(selected) > 100:
                    # Found neck connection, stop expanding main body
                    break
    
    # Phase 2: Include nearby protrusions (ears, horns)
    # Find vertices close to selected region that might be protrusions
    protrusion_candidates = set()
    shape = analyze_region_shape(bm, selected, obj)
    head_center = shape['center']
    head_size = shape['size'].length
    
    for vert_idx in selected:
        if vert_idx >= len(bm.verts):
            continue
        vert = bm.verts[vert_idx]
        
        for edge in vert.link_edges:
            other = edge.other_vert(vert)
            if other.index not in selected:
                other_world = obj.matrix_world @ other.co
                dist_to_head = (other_world - head_center).length
                
                # Include if close to head center
                if dist_to_head < head_size * 0.8:
                    protrusion_candidates.add(other.index)
    
    # Expand into protrusions
    for candidate in protrusion_candidates:
        if candidate in selected:
            continue
        
        # BFS expand into protrusion
        protrusion = bfs_expand_with_constraints(
            bm, candidate, obj,
            max_distance=head_size * 0.5,
            stop_at_narrow_connection=True,
            min_vertices=5,
            max_vertices=len(selected) // 4,  # Protrusions shouldn't be too large
            excluded_verts=selected
        )
        
        # Only include if it's a reasonable protrusion size
        if len(protrusion) > 3 and len(protrusion) < len(selected) // 2:
            selected.update(protrusion)
    
    return selected


def intelligent_select_leg(start_vertex_idx, obj, bm, leg_side='left', leg_position='front'):
    """
    Intelligently select leg region starting from clicked vertex.
    
    Leg characteristics:
    - Cylindrical/rectangular shape
    - Extends downward from body
    - Stops at hip/shoulder connection (narrow connection to body)
    
    Args:
        start_vertex_idx: Starting vertex index (where user clicked)
        obj: Blender object
        bm: bmesh object
        leg_side: 'left' or 'right'
        leg_position: 'front' or 'back'
        
    Returns:
        set: Vertex indices belonging to leg
    """
    if start_vertex_idx >= len(bm.verts):
        return set()
    
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    # Get mesh bounds for scale reference
    all_coords = [obj.matrix_world @ v.co for v in bm.verts]
    if not all_coords:
        return set()
    
    mesh_min = Vector((min(c.x for c in all_coords),
                      min(c.y for c in all_coords),
                      min(c.z for c in all_coords)))
    mesh_max = Vector((max(c.x for c in all_coords),
                      max(c.y for c in all_coords),
                      max(c.z for c in all_coords)))
    mesh_size = mesh_max - mesh_min
    mesh_diagonal = mesh_size.length
    
    # Leg is typically 20-40% of total mesh height
    max_leg_distance = mesh_diagonal * 0.45
    
    # Get starting position
    start_world = obj.matrix_world @ bm.verts[start_vertex_idx].co
    
    # Phase 1: BFS expansion following leg shape
    selected = set()
    visited = set()
    queue = deque([start_vertex_idx])
    visited.add(start_vertex_idx)
    
    # Track vertical extent (legs go down)
    min_z = start_world.z
    max_z = start_world.z
    
    while queue:
        current_idx = queue.popleft()
        
        if current_idx >= len(bm.verts):
            continue
        
        vert = bm.verts[current_idx]
        vert_world = obj.matrix_world @ vert.co
        
        # Distance check
        dist = (vert_world - start_world).length
        if dist > max_leg_distance:
            continue
        
        # Update vertical extent
        min_z = min(min_z, vert_world.z)
        max_z = max(max_z, vert_world.z)
        
        selected.add(current_idx)
        
        # Add neighbors
        for edge in vert.link_edges:
            other = edge.other_vert(vert)
            if other.index not in visited:
                visited.add(other.index)
                queue.append(other.index)
        
        # Check for narrow connection (hip/shoulder detection)
        if len(selected) > 30:
            shape = analyze_region_shape(bm, selected, obj)
            
            # Legs should be elongated (cylindrical)
            if shape['length_ratio'] > 1.5:
                has_narrow, boundary = detect_narrow_connection(bm, selected, obj, threshold=0.2)
                if has_narrow and len(selected) > 50:
                    # Found body connection, stop expanding
                    break
    
    # Phase 2: Ensure we got the full leg (expand toward ground)
    # Find lowest vertices and ensure they're included
    shape = analyze_region_shape(bm, selected, obj)
    leg_center = shape['center']
    
    # Find vertices below current selection that might be foot/paw
    foot_candidates = set()
    for vert_idx in selected:
        if vert_idx >= len(bm.verts):
            continue
        vert = bm.verts[vert_idx]
        
        for edge in vert.link_edges:
            other = edge.other_vert(vert)
            if other.index not in selected:
                other_world = obj.matrix_world @ other.co
                # Include if below current selection
                if other_world.z < leg_center.z:
                    foot_candidates.add(other.index)
    
    # Expand into foot area
    for candidate in foot_candidates:
        if candidate in selected:
            continue
        
        foot_expansion = bfs_expand_with_constraints(
            bm, candidate, obj,
            max_distance=shape['size'].length * 0.5,
            stop_at_narrow_connection=False,
            min_vertices=3,
            max_vertices=len(selected) // 3,
            excluded_verts=selected
        )
        
        if len(foot_expansion) > 2:
            selected.update(foot_expansion)
    
    return selected


def intelligent_select_tail(start_vertex_idx, obj, bm):
    """
    Intelligently select tail region starting from clicked vertex.
    
    Tail characteristics:
    - Elongated/thin shape (high length ratio)
    - Can be curved or straight
    - Stops at body connection (tail base)
    
    Args:
        start_vertex_idx: Starting vertex index (where user clicked)
        obj: Blender object
        bm: bmesh object
        
    Returns:
        set: Vertex indices belonging to tail
    """
    if start_vertex_idx >= len(bm.verts):
        return set()
    
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    # Get mesh bounds for scale reference
    all_coords = [obj.matrix_world @ v.co for v in bm.verts]
    if not all_coords:
        return set()
    
    mesh_min = Vector((min(c.x for c in all_coords),
                      min(c.y for c in all_coords),
                      min(c.z for c in all_coords)))
    mesh_max = Vector((max(c.x for c in all_coords),
                      max(c.y for c in all_coords),
                      max(c.z for c in all_coords)))
    mesh_size = mesh_max - mesh_min
    mesh_diagonal = mesh_size.length
    
    # Tail can be quite long
    max_tail_distance = mesh_diagonal * 0.5
    
    start_world = obj.matrix_world @ bm.verts[start_vertex_idx].co
    
    # Phase 1: BFS expansion following tail shape
    selected = set()
    visited = set()
    queue = deque([start_vertex_idx])
    visited.add(start_vertex_idx)
    
    while queue:
        current_idx = queue.popleft()
        
        if current_idx >= len(bm.verts):
            continue
        
        vert = bm.verts[current_idx]
        vert_world = obj.matrix_world @ vert.co
        
        # Distance check
        dist = (vert_world - start_world).length
        if dist > max_tail_distance:
            continue
        
        selected.add(current_idx)
        
        # Add neighbors
        for edge in vert.link_edges:
            other = edge.other_vert(vert)
            if other.index not in visited:
                visited.add(other.index)
                queue.append(other.index)
        
        # Check for narrow connection (tail base detection)
        if len(selected) > 20:
            shape = analyze_region_shape(bm, selected, obj)
            
            # Tails should be elongated
            if shape['is_elongated'] or shape['length_ratio'] > 1.5:
                has_narrow, boundary = detect_narrow_connection(bm, selected, obj, threshold=0.15)
                if has_narrow and len(selected) > 30:
                    # Found body connection, stop expanding
                    break
    
    return selected


def intelligent_select_wing(start_vertex_idx, obj, bm, wing_side='left'):
    """
    Intelligently select wing region starting from clicked vertex.
    
    Wing characteristics:
    - Large flat surface
    - Small bridge connection to body
    - Extends laterally from body
    
    Args:
        start_vertex_idx: Starting vertex index (where user clicked)
        obj: Blender object
        bm: bmesh object
        wing_side: 'left' or 'right'
        
    Returns:
        set: Vertex indices belonging to wing
    """
    if start_vertex_idx >= len(bm.verts):
        return set()
    
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    # Get mesh bounds for scale reference
    all_coords = [obj.matrix_world @ v.co for v in bm.verts]
    if not all_coords:
        return set()
    
    mesh_min = Vector((min(c.x for c in all_coords),
                      min(c.y for c in all_coords),
                      min(c.z for c in all_coords)))
    mesh_max = Vector((max(c.x for c in all_coords),
                      max(c.y for c in all_coords),
                      max(c.z for c in all_coords)))
    mesh_size = mesh_max - mesh_min
    mesh_diagonal = mesh_size.length
    
    # Wings can be large
    max_wing_distance = mesh_diagonal * 0.6
    
    start_world = obj.matrix_world @ bm.verts[start_vertex_idx].co
    mesh_center_x = (mesh_min.x + mesh_max.x) / 2
    
    # Phase 1: BFS expansion
    selected = set()
    visited = set()
    queue = deque([start_vertex_idx])
    visited.add(start_vertex_idx)
    
    while queue:
        current_idx = queue.popleft()
        
        if current_idx >= len(bm.verts):
            continue
        
        vert = bm.verts[current_idx]
        vert_world = obj.matrix_world @ vert.co
        
        # Distance check
        dist = (vert_world - start_world).length
        if dist > max_wing_distance:
            continue
        
        # Side check - only include vertices on correct side
        if wing_side == 'left' and vert_world.x > mesh_center_x + mesh_size.x * 0.1:
            continue
        if wing_side == 'right' and vert_world.x < mesh_center_x - mesh_size.x * 0.1:
            continue
        
        selected.add(current_idx)
        
        # Add neighbors
        for edge in vert.link_edges:
            other = edge.other_vert(vert)
            if other.index not in visited:
                visited.add(other.index)
                queue.append(other.index)
        
        # Check for narrow connection (wing-body connection)
        if len(selected) > 50:
            has_narrow, boundary = detect_narrow_connection(bm, selected, obj, threshold=0.2)
            if has_narrow and len(selected) > 100:
                # Found body connection, stop expanding
                break
    
    return selected


def intelligent_select_body(obj, bm, assigned_parts):
    """
    Select all remaining vertices not assigned to other parts.
    This is the BODY - everything that's not head, legs, tail, or wings.
    
    Args:
        obj: Blender object
        bm: bmesh object
        assigned_parts: Dict mapping part names to sets of vertex indices
        
    Returns:
        set: Vertex indices belonging to body
    """
    bm.verts.ensure_lookup_table()
    
    # Get all assigned vertices
    assigned_verts = set()
    for part_name, vert_set in assigned_parts.items():
        if part_name != 'body':
            assigned_verts.update(vert_set)
    
    # Body = all vertices not assigned to other parts
    all_verts = set(range(len(bm.verts)))
    body_verts = all_verts - assigned_verts
    
    return body_verts


def generic_bfs_expand(start_vertex_idx, obj, bm, max_vertices=1000):
    """
    Generic BFS expansion for fallback selection.
    
    Args:
        start_vertex_idx: Starting vertex index
        obj: Blender object
        bm: bmesh object
        max_vertices: Maximum vertices to select
        
    Returns:
        set: Selected vertex indices
    """
    if start_vertex_idx >= len(bm.verts):
        return set()
    
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    selected = set()
    visited = set()
    queue = deque([start_vertex_idx])
    visited.add(start_vertex_idx)
    
    while queue and len(selected) < max_vertices:
        current_idx = queue.popleft()
        
        if current_idx >= len(bm.verts):
            continue
        
        selected.add(current_idx)
        
        vert = bm.verts[current_idx]
        for edge in vert.link_edges:
            other = edge.other_vert(vert)
            if other.index not in visited:
                visited.add(other.index)
                queue.append(other.index)
    
    return selected
