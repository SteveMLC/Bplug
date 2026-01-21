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
import time


# Debug flag for optional logging during tuning
DEBUG_HEAD_SELECTION = False


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


def intelligent_select_head(start_vertex_idx, obj, bm, invert_forward_axis=False):
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
    mesh_center = (mesh_min + mesh_max) / 2.0
    total_verts = len(bm.verts)
    
    # Head is typically 15-30% of total mesh size.
    # After low-poly prep, we want to be more conservative.
    base_max_head_distance = mesh_diagonal * 0.35
    low_poly = total_verts < 10000
    if low_poly:
        max_head_distance = min(base_max_head_distance, mesh_diagonal * 0.25)
    else:
        max_head_distance = base_max_head_distance
    
    # Hard cap on head size as a fraction of total vertices.
    max_head_fraction = 0.4
    max_head_vertices = max(200, int(total_verts * max_head_fraction))
    
    # Forward-axis bias to keep growth toward the head/front.
    # Assume +Y is forward unless inverted by settings.
    forward_dir = Vector((0.0, 1.0, 0.0))
    if invert_forward_axis:
        forward_dir.y *= -1.0
    
    # Phase 1: Initial BFS expansion
    selected = set()
    visited = set()
    queue = deque([start_vertex_idx])
    visited.add(start_vertex_idx)
    
    start_world = obj.matrix_world @ bm.verts[start_vertex_idx].co
    seed_front_offset = (start_world - mesh_center).dot(forward_dir)
    
    while queue:
        current_idx = queue.popleft()
        
        if current_idx >= len(bm.verts):
            continue
        
        vert = bm.verts[current_idx]
        vert_world = obj.matrix_world @ vert.co
        
        # Distance check (keep within a reasonable radius around the seed)
        dist = (vert_world - start_world).length
        if dist > max_head_distance:
            continue
        
        # Forward-bias check: once we have some head mass, avoid growing
        # too far back into the torso along the body axis.
        if len(selected) > 50:
            front_offset = (vert_world - mesh_center).dot(forward_dir)
            # Allow a small buffer behind the seed, but strongly prefer
            # vertices at or in front of the seed along the forward axis.
            if front_offset < seed_front_offset - mesh_diagonal * 0.1:
                continue
        
        selected.add(current_idx)
        
        # Add neighbors
        for edge in vert.link_edges:
            other = edge.other_vert(vert)
            if other.index not in visited:
                visited.add(other.index)
                queue.append(other.index)
        
        # Check for narrow connection (neck detection) and size guardrail.
        if len(selected) > 50:  # Only check after initial expansion
            shape = analyze_region_shape(bm, selected, obj)
            if shape['is_blocky']:
                # Head-like shape found, check for neck with dynamic threshold.
                # On low-poly meshes we expect coarser connections, so be a bit
                # stricter to avoid flooding into the torso.
                base_threshold = 0.25
                threshold = base_threshold - (0.05 if low_poly else 0.0)
                has_narrow, boundary = detect_narrow_connection(bm, selected, obj, threshold=threshold)
                if has_narrow and len(selected) > 100:
                    # Found neck connection, stop expanding main body
                    break
        
        # Global guardrail: never let the head consume most of the mesh.
        if len(selected) >= max_head_vertices:
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

    # Phase 3: fill tiny, mostly-surrounded gaps inside the head selection.
    # This helper is deliberately conservative and only ever ADDS vertices.
    if selected:
        selected = fill_small_surrounded_gaps(
            bm,
            selected,
            # Allow slightly larger enclosed components so deeper cracks
            # and wider nose strips can be filled, while still bounded by
            # the existing head vertex cap.
            max_gap_size=min(128, max_head_vertices),
            # 0.9 = at least 90% of each vertex's neighbors must be inside
            # the head selection or the candidate gap, which still strongly
            # prefers fully enclosed regions but is tolerant of a few
            # external edges in complex topology.
            neighbor_selected_ratio=0.9,
            max_total_vertices=max_head_vertices,
            start_time=None,
            timeout_seconds=30.0,
        )
    
    if DEBUG_HEAD_SELECTION:
        # Optional lightweight diagnostics for tuning.
        connection_ratio = calculate_connection_ratio(bm, selected, set(range(total_verts)))
        print(
            "[HeadSelect] verts=%d (%.1f%% of mesh), connection_ratio=%.3f"
            % (len(selected), (len(selected) / max(1, total_verts)) * 100.0, connection_ratio)
        )
    
    return selected


def intelligent_select_head_from_seeds(seed_indices, obj, bm, invert_forward_axis=False):
    """
    Seed-set aware head selector used by auto-grow.
    
    Args:
        seed_indices: Iterable of starting vertex indices (current selection)
        obj: Blender object
        bm: bmesh object
        invert_forward_axis: Whether to invert forward axis bias
        
    Returns:
        set: Vertex indices belonging to head
    """
    if not seed_indices:
        return set()
    
    bm.verts.ensure_lookup_table()
    valid_seeds = [idx for idx in seed_indices if 0 <= idx < len(bm.verts)]
    if not valid_seeds:
        return set()
    
    # Compute geometric center of all seeds in world space.
    seed_world_positions = [obj.matrix_world @ bm.verts[i].co for i in valid_seeds]
    center = sum(seed_world_positions, Vector((0.0, 0.0, 0.0))) / len(seed_world_positions)
    
    # Choose the seed closest to the geometric center as the representative.
    best_seed = min(
        valid_seeds,
        key=lambda i: (obj.matrix_world @ bm.verts[i].co - center).length
    )
    
    head_verts = intelligent_select_head(best_seed, obj, bm, invert_forward_axis=invert_forward_axis)
    
    # Ensure all seeds are included in the final region.
    head_verts.update(valid_seeds)
    return head_verts


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
    
    
def fill_small_surrounded_gaps(
    bm,
    selected_indices,
    max_gap_size=32,
    neighbor_selected_ratio=1.0,
    max_total_vertices=None,
    start_time=None,
    timeout_seconds=30.0,
    excluded_indices=None,
    use_component_level_check=False,
):
    """
    Fill very small, fully surrounded gaps inside an existing vertex selection.

    This helper is intentionally conservative:
    - Only ever ADDS vertices to the selection (never removes).
    - Only considers connected components of unselected vertices that are
      well-enclosed by the current selection in the mesh graph.
    - Skips any component that exceeds max_gap_size or would push the total
      selection past max_total_vertices.
    - If excluded_indices is provided, those vertices are never added and are
      treated as \"external\" when evaluating surrounded-ness.
    - If use_component_level_check is True, uses a two-tier check: strict
      per-vertex first, then relaxed component-level analysis if needed.
    """
    bm.verts.ensure_lookup_table()

    total_verts = len(bm.verts)
    if not selected_indices or total_verts == 0 or max_gap_size <= 0:
        return set(selected_indices) if isinstance(selected_indices, set) else set(selected_indices)

    selected_set = set(selected_indices)
    excluded = set(excluded_indices) if excluded_indices else set()

    # If we already hit the total-vertex budget, do nothing.
    if max_total_vertices is not None and len(selected_set) >= max_total_vertices:
        return selected_set

    # Normalise timing parameters.
    have_timeout = start_time is not None and timeout_seconds is not None and timeout_seconds > 0.0

    # Collect unselected neighbors of the current selection as candidate seeds.
    candidate_seeds = set()
    for idx in selected_set:
        if idx >= len(bm.verts):
            continue
        vert = bm.verts[idx]
        for edge in vert.link_edges:
            other = edge.other_vert(vert)
            o_idx = other.index
            if o_idx not in selected_set and o_idx not in excluded:
                candidate_seeds.add(o_idx)

    if not candidate_seeds:
        return selected_set

    visited_unselected = set()
    gaps_to_add = set()

    for seed in candidate_seeds:
        if seed in visited_unselected or seed in selected_set:
            continue

        if have_timeout and (time.time() - start_time) > timeout_seconds:
            # Out of time – return what we have so far without further changes.
            return selected_set.union(gaps_to_add)

        # BFS over unselected vertices reachable from this seed.
        component = set()
        queue = deque([seed])
        visited_unselected.add(seed)
        too_big = False

        while queue:
            if have_timeout and (time.time() - start_time) > timeout_seconds:
                return selected_set.union(gaps_to_add)

            current_idx = queue.popleft()
            if current_idx >= len(bm.verts) or current_idx in excluded:
                continue

            component.add(current_idx)
            if len(component) > max_gap_size:
                # Component is too large to qualify as a tiny gap.
                too_big = True
                break

            vert = bm.verts[current_idx]
            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                o_idx = other.index
                if o_idx in selected_set or o_idx in component or o_idx in visited_unselected:
                    continue
                visited_unselected.add(o_idx)
                queue.append(o_idx)

        if too_big or not component:
            continue

        # Check that this component is strongly surrounded by the main selection.
        # We deliberately allow a small fraction of neighbors to point outside
        # the selection/component so that slightly \"open\" but clearly enclosed
        # cracks can still be filled.
        
        # Tier 1: Strict per-vertex check - all vertices must individually pass.
        component_is_surrounded = True
        vertex_ratios = []
        min_ratio = 1.0

        for vidx in component:
            vert = bm.verts[vidx]
            total_neighbors = 0
            enclosed_neighbors = 0

            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                o_idx = other.index
                total_neighbors += 1

                if o_idx in selected_set or o_idx in component:
                    enclosed_neighbors += 1

            if total_neighbors > 0:
                ratio = enclosed_neighbors / float(total_neighbors)
                vertex_ratios.append(ratio)
                min_ratio = min(min_ratio, ratio)
                if ratio < neighbor_selected_ratio:
                    component_is_surrounded = False

            if not component_is_surrounded and not use_component_level_check:
                break

        # Tier 2: Relaxed component-level check (if enabled and Tier 1 failed).
        if not component_is_surrounded and use_component_level_check and vertex_ratios:
            average_ratio = sum(vertex_ratios) / float(len(vertex_ratios))
            # Accept if average is close to threshold AND worst vertex is at least 50% enclosed.
            relaxed_threshold = neighbor_selected_ratio * 0.9
            if average_ratio >= relaxed_threshold and min_ratio >= 0.5:
                component_is_surrounded = True

        if not component_is_surrounded:
            continue

        # Respect the total-vertex cap if provided.
        if max_total_vertices is not None:
            projected_total = len(selected_set) + len(gaps_to_add) + len(component)
            if projected_total > max_total_vertices:
                # Adding this gap would exceed the allowed part size; skip it.
                continue

        gaps_to_add.update(component)

    if not gaps_to_add:
        return selected_set

    return selected_set.union(gaps_to_add)
    
    
def fill_gaps_aggressive(
    bm,
    selected_indices,
    max_gap_size=512,
    neighbor_selected_ratio=0.75,
    max_total_vertices=None,
    start_time=None,
    timeout_seconds=10.0,
    excluded_indices=None,
):
    """
    Higher-aggression wrapper around fill_small_surrounded_gaps for
    explicit \"Fill Gaps\" tools.

    Differences from the conservative helper:
    - Allows larger gap components (up to max_gap_size).
    - Uses a lower neighbor_selected_ratio so mostly-surrounded vertical
      strips can still be included.
    - Clamps total selection size to at most:
        * 60% of mesh vertices, and
        * ~120% of the original selection size,
      and also respects any caller-provided max_total_vertices.
    - Respects excluded_indices, which are never added and are treated as
      external neighbors.
    """
    bm.verts.ensure_lookup_table()
    total_verts = len(bm.verts)
    base_selection = set(selected_indices or [])

    if not base_selection or total_verts == 0:
        return base_selection

    # Compute an effective cap on total vertices after filling. For an
    # explicit user-triggered operation we prioritize staying close to
    # the current selection size, rather than enforcing a global mesh
    # fraction cap, to allow filling small cracks even when the part
    # already occupies most of the mesh.
    selection_cap = int(len(base_selection) * 1.2)
    effective_cap = selection_cap
    if max_total_vertices is not None:
        effective_cap = min(effective_cap, int(max_total_vertices), total_verts)

    return fill_small_surrounded_gaps(
        bm,
        base_selection,
        max_gap_size=max_gap_size,
        neighbor_selected_ratio=neighbor_selected_ratio,
        max_total_vertices=effective_cap,
        start_time=start_time,
        timeout_seconds=timeout_seconds,
        excluded_indices=excluded_indices,
        use_component_level_check=True,
    )
    
    
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


def compute_selection_boundary_edges(bm, selected_indices, excluded_indices=None):
    """
    Compute edges that form the boundary between selected and unselected vertices.
    
    A boundary edge has one vertex in the selection and one vertex outside.
    This is used to find cut boundaries for edge loop segmentation.
    
    Args:
        bm: bmesh object
        selected_indices: Set of vertex indices that are selected (part of the segment)
        excluded_indices: Optional set of vertex indices to exclude from boundary calculation
        
    Returns:
        set: Set of tuples (v1_idx, v2_idx) representing boundary edges
    """
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    selected_set = set(selected_indices) if selected_indices else set()
    excluded_set = set(excluded_indices) if excluded_indices else set()
    
    boundary_edges = set()
    
    for edge in bm.edges:
        v1_idx = edge.verts[0].index
        v2_idx = edge.verts[1].index
        
        # Skip if either vertex is excluded
        if v1_idx in excluded_set or v2_idx in excluded_set:
            continue
        
        # Check if this is a boundary edge (one vertex in selection, one outside)
        v1_selected = v1_idx in selected_set
        v2_selected = v2_idx in selected_set
        
        if v1_selected != v2_selected:
            # This is a boundary edge - one vertex is in selection, one is not
            # Store in canonical order (smaller index first) for consistency
            if v1_idx < v2_idx:
                boundary_edges.add((v1_idx, v2_idx))
            else:
                boundary_edges.add((v2_idx, v1_idx))
    
    return boundary_edges


def compute_selection_boundary_rings(bm, boundary_edges, close_loop_tolerance=5):
    """
    Group boundary edges into ordered edge loops (rings).
    
    Takes a set of boundary edges and organizes them into connected loops
    that can be used for edge loop selection. Handles multiple disconnected
    loops and attempts to close nearly-complete loops within tolerance.
    
    Args:
        bm: bmesh object
        boundary_edges: Set of tuples (v1_idx, v2_idx) representing boundary edges
        close_loop_tolerance: Maximum number of missing edges to bridge when closing a loop
        
    Returns:
        list: List of edge loops, where each loop is a list of vertex indices in order
    """
    if not boundary_edges:
        return []
    
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    # Build adjacency map: vertex -> set of connected vertices via boundary edges
    vertex_connections = {}
    edge_set = set(boundary_edges)
    
    for v1_idx, v2_idx in boundary_edges:
        if v1_idx not in vertex_connections:
            vertex_connections[v1_idx] = set()
        if v2_idx not in vertex_connections:
            vertex_connections[v2_idx] = set()
        vertex_connections[v1_idx].add(v2_idx)
        vertex_connections[v2_idx].add(v1_idx)
    
    if not vertex_connections:
        return []
    
    # Find connected components (loops)
    visited_vertices = set()
    loops = []
    
    for start_vertex in vertex_connections:
        if start_vertex in visited_vertices:
            continue
        
        # Build a loop starting from this vertex
        loop_vertices = []
        current_vertex = start_vertex
        visited_in_loop = set()
        
        # Traverse the loop
        while current_vertex is not None:
            if current_vertex in visited_in_loop:
                # We've completed a loop
                break
            
            loop_vertices.append(current_vertex)
            visited_in_loop.add(current_vertex)
            visited_vertices.add(current_vertex)
            
            # Find next vertex in the loop
            next_vertex = None
            neighbors = vertex_connections.get(current_vertex, set())
            
            # Prefer unvisited neighbors
            unvisited_neighbors = [n for n in neighbors if n not in visited_in_loop]
            if unvisited_neighbors:
                next_vertex = unvisited_neighbors[0]
            elif neighbors:
                # All neighbors visited - check if we can close the loop
                if start_vertex in neighbors and len(loop_vertices) > 2:
                    # Loop is closed
                    break
                # Otherwise, we've hit a dead end or branch
                break
            
            current_vertex = next_vertex
        
        if len(loop_vertices) >= 2:
            loops.append(loop_vertices)
    
    # Attempt to close nearly-complete loops within tolerance
    # This is the "balanced" approach: prefer conservative boundaries but allow
    # small extensions to close loops when it's clearly beneficial
    closed_loops = []
    for loop in loops:
        if len(loop) < 3:
            # Too short to be a meaningful loop
            closed_loops.append(loop)
            continue
        
        # Check if loop is already closed (first and last vertices are connected)
        first_vert = loop[0]
        last_vert = loop[-1]
        
        if first_vert in vertex_connections.get(last_vert, set()):
            # Loop is already closed
            closed_loops.append(loop)
            continue
        
        # Check if we can close the loop by bridging a small gap
        # Look for a path between first and last vertex through the mesh
        gap_size = _find_gap_size(bm, first_vert, last_vert, vertex_connections)
        
        if gap_size is not None and gap_size <= close_loop_tolerance:
            # Small gap - try to bridge it by finding intermediate vertices
            bridge_path = _find_bridge_path(bm, first_vert, last_vert, gap_size, vertex_connections)
            if bridge_path:
                # Extend the loop with the bridge path
                extended_loop = loop + bridge_path[1:-1]  # Exclude endpoints (already in loop)
                closed_loops.append(extended_loop)
            else:
                closed_loops.append(loop)
        else:
            # Gap too large or no path found - keep loop as-is
            closed_loops.append(loop)
    
    return closed_loops


def _find_gap_size(bm, start_vert_idx, end_vert_idx, vertex_connections):
    """
    Find the minimum path length between two vertices through the mesh.
    Used to determine if a loop can be closed with a small bridge.
    
    Returns:
        int: Path length, or None if no path found
    """
    if start_vert_idx == end_vert_idx:
        return 0
    
    # Simple BFS to find shortest path
    queue = deque([(start_vert_idx, 0)])
    visited = {start_vert_idx}
    
    while queue:
        current, distance = queue.popleft()
        
        if current == end_vert_idx:
            return distance
        
        # Check direct connections first
        if current in vertex_connections:
            for neighbor in vertex_connections[current]:
                if neighbor not in visited:
                    if neighbor == end_vert_idx:
                        return distance + 1
                    visited.add(neighbor)
                    queue.append((neighbor, distance + 1))
        
        # Also check mesh edges (for bridging gaps)
        if current < len(bm.verts):
            vert = bm.verts[current]
            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                if other.index not in visited:
                    if other.index == end_vert_idx:
                        return distance + 1
                    visited.add(other.index)
                    queue.append((other.index, distance + 1))
    
    return None


def _find_bridge_path(bm, start_vert_idx, end_vert_idx, max_length, vertex_connections):
    """
    Find a path between two vertices to bridge a gap in a loop.
    
    Returns:
        list: List of vertex indices forming the bridge path, or None if no path found
    """
    if start_vert_idx == end_vert_idx:
        return [start_vert_idx]
    
    # BFS to find path
    queue = deque([(start_vert_idx, [start_vert_idx])])
    visited = {start_vert_idx}
    
    while queue:
        current, path = queue.popleft()
        
        if len(path) > max_length + 1:
            continue
        
        if current == end_vert_idx:
            return path
        
        # Check mesh edges for bridging
        if current < len(bm.verts):
            vert = bm.verts[current]
            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                if other.index not in visited:
                    visited.add(other.index)
                    queue.append((other.index, path + [other.index]))
    
    return None
