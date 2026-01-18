"""
Segmentation refinement using mesh connectivity analysis
Provides industry-standard precision through connectivity-based algorithms

Now includes geometry-based detection for accurate segmentation:
- Body = Center of geometry (largest connected component)
- Head = Top front (relative to body center and main axis)
- Legs = Bottom front/back (relative to body center)
- Tail = Back (relative to body center and main axis)
- Wings = Top/side (relative to body center)
"""

import bmesh
from mathutils import Vector
from collections import defaultdict, deque
import math


def detect_mesh_islands(mesh):
    """
    Find disconnected mesh components (islands)
    
    Args:
        mesh: Blender mesh data
        
    Returns:
        list: List of sets, each set contains vertex indices in one island
    """
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    
    visited = set()
    islands = []
    max_iterations = len(bm.verts) * 2  # Safety limit to prevent infinite loops
    
    for vert in bm.verts:
        if vert.index in visited:
            continue
        
        # BFS to find connected component
        island = set()
        queue = deque([vert])
        visited.add(vert.index)
        island.add(vert.index)
        iterations = 0
        
        while queue and iterations < max_iterations:
            iterations += 1
            current = queue.popleft()
            for edge in current.link_edges:
                other_vert = edge.other_vert(current)
                if other_vert.index not in visited:
                    visited.add(other_vert.index)
                    island.add(other_vert.index)
                    queue.append(other_vert)
        
        if iterations >= max_iterations:
            print(f"WARNING: Island detection hit iteration limit ({max_iterations})")
        
        if island:
            islands.append(island)
    
    bm.free()
    return islands


def detect_boundary_vertices(mesh, vertex_groups):
    """
    Find vertices on boundaries between vertex groups
    
    Args:
        mesh: Blender mesh data
        vertex_groups: Dict mapping vertex group names to sets of vertex indices
        
    Returns:
        dict: Mapping from vertex index to set of vertex group names it belongs to
    """
    # Build vertex to groups mapping
    vert_to_groups = defaultdict(set)
    for vg_name, vert_indices in vertex_groups.items():
        for vert_idx in vert_indices:
            vert_to_groups[vert_idx].add(vg_name)
    
    # Find boundary vertices (vertices in multiple groups or adjacent to different groups)
    boundary_verts = {}
    
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    for vert in bm.verts:
        vert_idx = vert.index
        vert_groups = vert_to_groups.get(vert_idx, set())
        
        # Check if vertex is in multiple groups
        if len(vert_groups) > 1:
            boundary_verts[vert_idx] = vert_groups
        else:
            # Check if vertex is adjacent to vertices in different groups
            neighbor_groups = set()
            for edge in vert.link_edges:
                other_vert = edge.other_vert(vert)
                other_idx = other_vert.index
                neighbor_groups.update(vert_to_groups.get(other_idx, set()))
            
            if neighbor_groups and vert_groups:
                # If neighbors have different groups, this is a boundary
                if neighbor_groups != vert_groups:
                    boundary_verts[vert_idx] = vert_groups | neighbor_groups
    
    bm.free()
    return boundary_verts


def analyze_mesh_connectivity(mesh):
    """
    Analyze mesh connectivity to improve segmentation
    
    Returns:
        dict with:
        - 'islands': list of disconnected components (sets of vertex indices)
        - 'boundary_edges': edges crossing region boundaries (placeholder for future use)
        - 'connection_points': vertices connecting parts (placeholder for future use)
    """
    islands = detect_mesh_islands(mesh)
    
    return {
        'islands': islands,
        'boundary_edges': [],  # Can be extended later
        'connection_points': [],  # Can be extended later
    }


def refine_segmentation_with_connectivity(obj, initial_regions, template, sensitivity=0.5):
    """
    Refine spatial segmentation using mesh connectivity
    Implements priority system to resolve overlapping regions
    
    Args:
        obj: Blender object with mesh data
        initial_regions: Dict mapping part names to lists of vertex indices
        template: Segmentation template dictionary
        sensitivity: Float (0.0-1.0) for boundary detection sensitivity
        
    Returns:
        dict: Refined vertex groups with vertex indices (no overlaps)
    """
    mesh = obj.data
    
    # Define priority order (higher priority parts are processed last and override others)
    # Body parts typically have priority: body > head > limbs/tail/wings
    priority_order = {
        'body': 0,  # Lowest priority - most flexible
        'head': 1,
        'leg_front_l': 2,
        'leg_front_r': 2,
        'leg_back_l': 2,
        'leg_back_r': 2,
        'leg_l': 2,
        'leg_r': 2,
        'tail': 3,
        'wing_l': 3,
        'wing_r': 3,
        'arm_l': 3,
        'arm_r': 3,
    }
    
    # Convert initial regions to sets for easier manipulation
    vertex_groups = {}
    for part_name, vert_indices in initial_regions.items():
        vertex_groups[part_name] = set(vert_indices)
    
    # First pass: Resolve overlapping vertices using priority
    # Vertices in multiple groups are assigned to the highest priority group
    all_vertices = set()
    for vert_set in vertex_groups.values():
        all_vertices.update(vert_set)
    
    # Find vertices in multiple groups
    vert_to_groups = defaultdict(set)
    for part_name, vert_set in vertex_groups.items():
        for vert_idx in vert_set:
            vert_to_groups[vert_idx].add(part_name)
    
    # Remove overlapping vertices from lower priority groups
    for vert_idx, groups in vert_to_groups.items():
        if len(groups) > 1:
            # Sort groups by priority (lower number = lower priority)
            sorted_groups = sorted(groups, key=lambda g: priority_order.get(g, 99))
            # Keep only the highest priority group
            keep_group = sorted_groups[-1]
            # Remove from all other groups
            for group_name in sorted_groups[:-1]:
                vertex_groups[group_name].discard(vert_idx)
    
    # Build edge connectivity map
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    # Find boundary vertices
    boundary_verts = detect_boundary_vertices(mesh, vertex_groups)
    
    # Refine boundaries: assign boundary vertices based on majority of connected neighbors
    for vert_idx, groups in boundary_verts.items():
        if len(groups) <= 1:
            continue
        
        # Count neighbors in each group
        group_counts = defaultdict(int)
        
        if vert_idx < len(bm.verts):
            vert = bm.verts[vert_idx]
            for edge in vert.link_edges:
                neighbor_vert = edge.other_vert(vert)
                neighbor_idx = neighbor_vert.index
                
                # Find which group(s) neighbor belongs to
                for vg_name, vert_set in vertex_groups.items():
                    if neighbor_idx in vert_set:
                        group_counts[vg_name] += 1
        
        # Assign to group with most neighbors (if above sensitivity threshold)
        if group_counts:
            max_count = max(group_counts.values())
            total_neighbors = sum(group_counts.values())
            
            if total_neighbors > 0 and max_count / total_neighbors >= sensitivity:
                # Assign to most common group
                assigned_group = max(group_counts, key=group_counts.get)
                
                # Remove from other groups, add to assigned group
                for vg_name in groups:
                    if vg_name != assigned_group:
                        vertex_groups[vg_name].discard(vert_idx)
                vertex_groups[assigned_group].add(vert_idx)
    
    bm.free()
    
    # Convert back to lists
    refined_groups = {}
    for part_name, vert_set in vertex_groups.items():
        refined_groups[part_name] = list(vert_set)
    
    return refined_groups


def analyze_template_match(obj, template, get_mesh_bounds_func):
    """
    Analyze mesh proportions and compare to template assumptions
    Warns if mesh doesn't match template well
    
    Args:
        obj: Blender object with mesh data
        template: Segmentation template dictionary
        get_mesh_bounds_func: Function to get mesh bounds
        
    Returns:
        dict: Analysis results with warnings and confidence scores
    """
    mesh = obj.data
    min_bbox, max_bbox, size = get_mesh_bounds_func(obj)
    
    if not size or size.length == 0:
        return {
            'confidence': 0.0,
            'warnings': ['Mesh has no size'],
            'match_score': 0.0
        }
    
    warnings = []
    confidence_scores = []
    
    # Calculate mesh proportions (relative to bounding box)
    # Check key body part proportions
    body_parts_to_check = ['head', 'body']
    for part_name in body_parts_to_check:
        if part_name not in template:
            continue
        
        region = template[part_name]
        
        # Expected relative size from template
        expected_height_range = region.get('y_max', 1.0) - region.get('y_min', 0.0)
        
        # Actual mesh proportion in that range
        if expected_height_range < 0.1:
            warnings.append(f"{part_name.capitalize()} region is very small in template (<10% of height)")
            confidence_scores.append(0.5)
        elif expected_height_range > 0.6:
            warnings.append(f"{part_name.capitalize()} region is very large in template (>60% of height)")
            confidence_scores.append(0.7)
        else:
            confidence_scores.append(0.9)
    
    # Check for very small mesh dimensions (might indicate wrong orientation)
    min_dimension = min(size.x, size.y, size.z)
    max_dimension = max(size.x, size.y, size.z)
    
    if min_dimension > 0 and max_dimension / min_dimension > 10:
        warnings.append("Mesh has very elongated proportions - may need rotation")
        confidence_scores.append(0.6)
    
    # Overall confidence
    if confidence_scores:
        avg_confidence = sum(confidence_scores) / len(confidence_scores)
    else:
        avg_confidence = 0.8  # Default if no specific checks
    
    match_score = avg_confidence
    
    return {
        'confidence': avg_confidence,
        'warnings': warnings,
        'match_score': match_score
    }


def find_protrusions(obj, main_body_region_name, vertex_groups, threshold_ratio=0.3):
    """
    Detect parts extending from main body (legs, wings, tails)
    
    Args:
        obj: Blender object with mesh data
        main_body_region_name: Name of the main body vertex group
        vertex_groups: Dict mapping vertex group names to lists of vertex indices
        threshold_ratio: Ratio threshold for identifying protrusions (0.0-1.0)
        
    Returns:
        dict: Mapping of part names to protrusion scores (higher = more likely protrusion)
    """
    if main_body_region_name not in vertex_groups:
        return {}
    
    mesh = obj.data
    body_verts = set(vertex_groups[main_body_region_name])
    
    # Build connectivity map
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    protrusion_scores = {}
    
    # For each vertex group (excluding body), check if it's a protrusion
    for part_name, vert_indices in vertex_groups.items():
        if part_name == main_body_region_name:
            continue
        
        part_verts = set(vert_indices)
        
        # Find connection points (vertices in part that have neighbors in body)
        connection_count = 0
        connection_area = 0.0
        
        for vert_idx in part_verts:
            if vert_idx >= len(bm.verts):
                continue
            vert = bm.verts[vert_idx]
            
            # Check if connected to body
            for edge in vert.link_edges:
                neighbor = edge.other_vert(vert)
                if neighbor.index in body_verts:
                    connection_count += 1
                    # Approximate connection area using edge length
                    connection_area += (vert.co - neighbor.co).length
                    break
        
        # Calculate protrusion metrics
        if len(part_verts) > 0:
            # Ratio of connection points to total vertices (lower = more protrusion-like)
            connection_ratio = connection_count / len(part_verts)
            
            # Calculate bounding box to estimate shape
            part_coords = [bm.verts[idx].co for idx in part_verts if idx < len(bm.verts)]
            if part_coords:
                min_co = Vector((min(c.x for c in part_coords), 
                                min(c.y for c in part_coords), 
                                min(c.z for c in part_coords)))
                max_co = Vector((max(c.x for c in part_coords), 
                                max(c.y for c in part_coords), 
                                max(c.z for c in part_coords)))
                size = max_co - min_co
                
                # Calculate aspect ratio (length/width) - higher = more protrusion-like
                if size.length > 0:
                    max_dim = max(size)
                    avg_dim = sum(size) / 3.0
                    aspect_ratio = max_dim / (avg_dim + 0.001)
                else:
                    aspect_ratio = 1.0
                
                # Protrusion score: lower connection ratio + higher aspect ratio = more protrusion-like
                protrusion_score = (1.0 - connection_ratio) * aspect_ratio
                protrusion_scores[part_name] = protrusion_score
    
    bm.free()
    return protrusion_scores


# =============================================================================
# GEOMETRY-BASED SEGMENTATION FUNCTIONS
# These functions use actual mesh geometry rather than bounding box percentages
# =============================================================================

def calculate_geometric_center(vertices_coords):
    """
    Calculate the geometric center (centroid) of a set of vertices
    
    Args:
        vertices_coords: List of Vector coordinates
        
    Returns:
        Vector: Center position
    """
    if not vertices_coords:
        return Vector((0, 0, 0))
    
    total = Vector((0, 0, 0))
    for co in vertices_coords:
        total += co
    
    return total / len(vertices_coords)


def detect_main_body_fast(obj):
    """
    Fast body detection for large meshes - uses bounding box center instead of full BFS
    
    Args:
        obj: Blender object with mesh data
        
    Returns:
        dict: Same format as detect_main_body()
    """
    if not obj or obj.type != 'MESH':
        return None
    
    mesh = obj.data
    vertex_count = len(mesh.vertices)
    
    if vertex_count == 0:
        return None
    
    # Use bounding box center as body center (much faster)
    bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_co = Vector((min(v.x for v in bbox), min(v.y for v in bbox), min(v.z for v in bbox)))
    max_co = Vector((max(v.x for v in bbox), max(v.y for v in bbox), max(v.z for v in bbox)))
    body_center = (min_co + max_co) / 2
    
    # For fast mode, use vertices within 80% of bounding box center
    # Sample vertices instead of processing all (every 10th vertex for large meshes)
    sample_rate = max(1, vertex_count // 10000)  # Sample every Nth vertex
    body_verts = set()
    
    for i in range(0, vertex_count, sample_rate):
        vert = mesh.vertices[i]
        world_pos = obj.matrix_world @ vert.co
        # Distance from center normalized by bounding box size
        bbox_size = max_co - min_co
        max_dist = bbox_size.length
        dist_from_center = (world_pos - body_center).length
        
        if max_dist > 0 and dist_from_center / max_dist <= 0.8:
            body_verts.add(i)
    
    # If we sampled, add nearby vertices
    if sample_rate > 1:
        # Add vertices adjacent to sampled ones (within small radius)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        
        sampled_verts = list(body_verts)
        for vert_idx in sampled_verts:
            if vert_idx < len(bm.verts):
                vert = bm.verts[vert_idx]
                for edge in vert.link_edges:
                    other = edge.other_vert(vert)
                    if other.index not in body_verts:
                        other_world = obj.matrix_world @ other.co
                        dist = (other_world - body_center).length
                        bbox_size = max_co - min_co
                        max_dist = bbox_size.length
                        if max_dist > 0 and dist / max_dist <= 0.85:
                            body_verts.add(other.index)
        
        bm.free()
    
    # Calculate actual center from selected vertices
    if body_verts:
        body_coords = [obj.matrix_world @ mesh.vertices[i].co for i in body_verts]
        body_center = calculate_geometric_center(body_coords)
    else:
        # Fallback: use all vertices
        body_verts = set(range(vertex_count))
        body_coords = [obj.matrix_world @ mesh.vertices[i].co for i in body_verts]
        body_center = calculate_geometric_center(body_coords)
    
    return {
        'vertex_indices': body_verts,
        'center': body_center,
        'bounds': (min_co, max_co),
        'mesh_center': body_center
    }


def detect_main_body(obj):
    """
    Detect the main body region using connectivity and centrality analysis
    
    The main body is defined as:
    1. The largest connected component (or the most central region)
    2. The region closest to the geometric center of the mesh
    
    Args:
        obj: Blender object with mesh data
        
    Returns:
        dict: {
            'vertex_indices': set of vertex indices in main body,
            'center': Vector geometric center,
            'bounds': (min_co, max_co) tuple
        }
    """
    if not obj or obj.type != 'MESH':
        return None
    
    mesh = obj.data
    vertex_count = len(mesh.vertices)
    
    # Always use bounding box approximation first (faster, more reliable)
    # Only use BFS connectivity analysis if bounding box method doesn't work well
    # For large meshes or in fast mode, skip BFS entirely
    if vertex_count > 100000:
        print("Large mesh detected - using optimized body detection")
        # Limit component detection to first component only
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        
        # Fast path: assume single component, use center-based detection
        all_coords = [obj.matrix_world @ v.co for v in bm.verts]
        mesh_center = calculate_geometric_center(all_coords)
        
        # Sample vertices for distance calculation (every 10th for large meshes)
        sample_rate = max(1, vertex_count // 50000)
        distances = []
        for i in range(0, vertex_count, sample_rate):
            vert_co = obj.matrix_world @ bm.verts[i].co
            dist = (vert_co - mesh_center).length
            distances.append((i, dist))
        
        if distances:
            max_dist = max(d[1] for d in distances)
            threshold = max_dist * 0.75
            body_verts = set(idx for idx, dist in distances if dist <= threshold)
            
            # Expand to include nearby vertices
            for vert_idx in list(body_verts)[:1000]:  # Limit expansion
                if vert_idx < len(bm.verts):
                    vert = bm.verts[vert_idx]
                    for edge in vert.link_edges[:5]:  # Limit edges checked
                        other = edge.other_vert(vert)
                        if other.index not in body_verts and other.index < vertex_count:
                            other_co = obj.matrix_world @ other.co
                            dist = (other_co - mesh_center).length
                            if dist <= threshold * 1.1:
                                body_verts.add(other.index)
        else:
            body_verts = set(range(vertex_count))
        
        body_coords = [obj.matrix_world @ bm.verts[i].co for i in body_verts if i < len(bm.verts)]
        body_center = calculate_geometric_center(body_coords) if body_coords else mesh_center
        
        if body_coords:
            min_co = Vector((min(c.x for c in body_coords),
                            min(c.y for c in body_coords),
                            min(c.z for c in body_coords)))
            max_co = Vector((max(c.x for c in body_coords),
                            max(c.y for c in body_coords),
                            max(c.z for c in body_coords)))
        else:
            min_co = max_co = mesh_center
        
        bm.free()
        return {
            'vertex_indices': body_verts,
            'center': body_center,
            'bounds': (min_co, max_co),
            'mesh_center': mesh_center
        }
    
    # Normal path for smaller meshes
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    # Get all vertex coordinates in world space
    all_coords = [obj.matrix_world @ v.co for v in bm.verts]
    mesh_center = calculate_geometric_center(all_coords)
    
    # Find connected components
    # Limit to first 10 components for performance (usually only 1-2 exist anyway)
    visited = set()
    components = []
    max_iterations = len(bm.verts) * 2  # Safety limit to prevent infinite loops
    max_components = 10  # Don't process more than 10 components
    
    for start_vert in bm.verts:
        if start_vert.index in visited:
            continue
        
        if len(components) >= max_components:
            # Found enough components, break early
            break
        
        # BFS to find connected component
        component_verts = set()
        queue = deque([start_vert])
        visited.add(start_vert.index)
        component_verts.add(start_vert.index)
        iterations = 0
        
        while queue and iterations < max_iterations:
            iterations += 1
            current = queue.popleft()
            for edge in current.link_edges:
                other_vert = edge.other_vert(current)
                if other_vert.index not in visited:
                    visited.add(other_vert.index)
                    component_verts.add(other_vert.index)
                    queue.append(other_vert)
        
        if iterations >= max_iterations:
            print(f"WARNING: Component detection hit iteration limit ({max_iterations})")
            # Still add the component we found so far
            if not component_verts:
                continue
        
        if component_verts:
            # Calculate component center (sample for large components)
            if len(component_verts) > 50000:
                # Sample vertices for center calculation
                sample_verts = list(component_verts)[::max(1, len(component_verts) // 10000)]
                component_coords = [obj.matrix_world @ bm.verts[i].co for i in sample_verts if i < len(bm.verts)]
            else:
                component_coords = [obj.matrix_world @ bm.verts[i].co for i in component_verts if i < len(bm.verts)]
            component_center = calculate_geometric_center(component_coords)
            
            components.append({
                'vertex_indices': component_verts,
                'center': component_center,
                'size': len(component_verts)
            })
            
            # Early exit: if first component is > 90% of mesh, it's likely the body
            if len(component_verts) > len(mesh.vertices) * 0.9:
                break
    
    if not components:
        bm.free()
        return None
    
    # If single component, identify "body core" using distance from center
    if len(components) == 1:
        all_verts = components[0]['vertex_indices']
        
        # For large meshes, sample vertices for distance calculation
        if len(all_verts) > 100000:
            # Sample every Nth vertex
            sample_rate = max(1, len(all_verts) // 50000)
            sampled_verts = list(all_verts)[::sample_rate]
            distances = []
            for vert_idx in sampled_verts:
                if vert_idx < len(bm.verts):
                    vert_co = obj.matrix_world @ bm.verts[vert_idx].co
                    dist = (vert_co - mesh_center).length
                    distances.append((vert_idx, dist))
            
            if distances:
                max_dist = max(d[1] for d in distances)
                threshold = max_dist * 0.75
                # Use sampled vertices as seed, then expand
                body_verts = set(idx for idx, dist in distances if dist <= threshold)
                # Expand to include nearby vertices
                for vert_idx in list(body_verts)[:5000]:  # Limit expansion
                    if vert_idx < len(bm.verts):
                        vert = bm.verts[vert_idx]
                        for edge in vert.link_edges[:3]:  # Limit edges
                            other = edge.other_vert(vert)
                            if other.index in all_verts and other.index not in body_verts:
                                other_co = obj.matrix_world @ other.co
                                dist = (other_co - mesh_center).length
                                if dist <= threshold * 1.1:
                                    body_verts.add(other.index)
            else:
                body_verts = all_verts
        else:
            # Normal path: process all vertices
            distances = []
            for vert_idx in all_verts:
                if vert_idx < len(bm.verts):
                    vert_co = obj.matrix_world @ bm.verts[vert_idx].co
                    dist = (vert_co - mesh_center).length
                    distances.append((vert_idx, dist))
            
            if distances:
                max_dist = max(d[1] for d in distances)
                # Body core = vertices within 75% of max distance from center
                # (increased from 60% to capture more of the body for spread-out models like goats)
                threshold = max_dist * 0.75
                body_verts = set(idx for idx, dist in distances if dist <= threshold)
            else:
                body_verts = all_verts
            
            body_coords = [obj.matrix_world @ bm.verts[i].co for i in body_verts]
            body_center = calculate_geometric_center(body_coords) if body_coords else mesh_center
            
            # Calculate bounds
            if body_coords:
                min_co = Vector((min(c.x for c in body_coords),
                                min(c.y for c in body_coords),
                                min(c.z for c in body_coords)))
                max_co = Vector((max(c.x for c in body_coords),
                                max(c.y for c in body_coords),
                                max(c.z for c in body_coords)))
            else:
                min_co = max_co = mesh_center
            
            bm.free()
            return {
                'vertex_indices': body_verts,
                'center': body_center,
                'bounds': (min_co, max_co),
                'mesh_center': mesh_center
            }
    
    # Multiple components: find the largest/most central one
    # Score by size and centrality
    best_component = None
    best_score = -1
    
    for comp in components:
        size_score = comp['size'] / len(mesh.vertices)  # Normalized size
        dist_to_center = (comp['center'] - mesh_center).length
        max_possible_dist = max((obj.matrix_world @ v.co - mesh_center).length for v in bm.verts)
        centrality_score = 1.0 - (dist_to_center / (max_possible_dist + 0.001))
        
        # Combined score: favor size but also consider centrality
        score = size_score * 0.7 + centrality_score * 0.3
        
        if score > best_score:
            best_score = score
            best_component = comp
    
    if best_component:
        body_coords = [obj.matrix_world @ bm.verts[i].co for i in best_component['vertex_indices']]
        min_co = Vector((min(c.x for c in body_coords),
                        min(c.y for c in body_coords),
                        min(c.z for c in body_coords)))
        max_co = Vector((max(c.x for c in body_coords),
                        max(c.y for c in body_coords),
                        max(c.z for c in body_coords)))
        
        bm.free()
        return {
            'vertex_indices': best_component['vertex_indices'],
            'center': best_component['center'],
            'bounds': (min_co, max_co),
            'mesh_center': mesh_center
        }
    
    bm.free()
    return None


def detect_model_orientation(obj, body_info, protrusions=None, primary_axis=None, lateral_axis=None):
    """
    Detect model orientation to determine forward direction (head location).
    
    Uses multiple heuristics to determine if head is at -Y or +Y:
    1. Shape analysis: Find blocky protrusions (head candidates) vs elongated (tail candidates)
    2. Size analysis: Head is typically LARGER than tail (15-35% of body)
    3. Horn detection: Top lateral protrusions (+Z, lateral) indicate head region
    4. Position analysis: Head protrudes at forward end, tail at backward end
    5. Fallback: Vertex distribution (body mass typically in middle/back)
    
    Args:
        obj: Blender object with mesh data
        body_info: Result from detect_main_body()
        protrusions: Optional list of protrusion dicts
        primary_axis: Optional Vector for primary axis (if None, determined from body_size)
        lateral_axis: Optional Vector for lateral axis (if None, determined from body_size)
        
    Returns:
        dict: {
            'head_direction': -1 or +1,  # -1 = head at -Y, +1 = head at +Y
            'confidence': 0.0-1.0,
            'reason': str,
            'is_inverted': bool  # True if head is at -Y (inverted from standard)
        }
    """
    if not body_info:
        return {
            'head_direction': 1,
            'confidence': 0.5,
            'reason': 'fallback_no_body_info',
            'is_inverted': False
        }
    
    body_center = body_info['center']
    body_bounds = body_info['bounds']
    body_size = body_bounds[1] - body_bounds[0]
    
    # Default axes for analysis
    up = Vector((0, 0, 1))  # Z up
    
    # Determine primary horizontal axis (X or Y)
    # Use provided axes if available, otherwise determine from body_size
    if primary_axis is None or lateral_axis is None:
        if abs(body_size.x) > abs(body_size.y):
            # X is longer, Y is forward/back
            primary_axis = Vector((0, 1, 0))
            lateral_axis = Vector((1, 0, 0))
        else:
            # Y is longer, X is forward/back
            primary_axis = Vector((1, 0, 0))
            lateral_axis = Vector((0, 1, 0))
    
    # Initialize scores for each direction
    # Positive score = head at positive direction, negative = head at negative direction
    head_score = 0.0
    confidence_factors = []
    reasons = []
    
    if protrusions:
        # Analyze protrusions at each end
        positive_end_protrusions = []
        negative_end_protrusions = []
        top_lateral_protrusions = []  # Potential horns
        
        body_length = max(abs(body_size.dot(primary_axis.normalized())), 0.001)
        body_height = max(abs(body_size.dot(up.normalized())), 0.001)
        body_width = max(abs(body_size.dot(lateral_axis.normalized())), 0.001)
        
        for p in protrusions:
            relative_pos = p['relative_position']
            forward_component = relative_pos.dot(primary_axis)
            vertical_component = relative_pos.dot(up)
            lateral_component = relative_pos.dot(lateral_axis)
            
            norm_forward = forward_component / body_length
            norm_vertical = vertical_component / body_height
            norm_lateral = lateral_component / body_width
            
            # Categorize protrusions by position
            if norm_forward > 0.2:
                positive_end_protrusions.append(p)
            elif norm_forward < -0.2:
                negative_end_protrusions.append(p)
            
            # Check for horn-like protrusions (top + lateral)
            if norm_vertical > 0.3 and abs(norm_lateral) > 0.2:
                top_lateral_protrusions.append({
                    'protrusion': p,
                    'norm_forward': norm_forward
                })
        
        # Heuristic 1: Shape analysis - blocky = head, elongated = tail
        # Shape is the most reliable indicator, so give it higher weight
        for p in positive_end_protrusions:
            shape = analyze_protrusion_shape(p)
            if shape['is_blocky'] and not shape['is_elongated']:
                head_score += 3.0  # Increased weight: Blocky at positive end = head at positive
                reasons.append('blocky_protrusion_at_positive')
            elif shape['is_elongated'] and shape['length_ratio'] > 2.0:  # Lowered threshold from 2.5
                head_score -= 2.0  # Increased weight: Elongated at positive end = tail at positive, head at negative
                reasons.append('elongated_protrusion_at_positive')
        
        for p in negative_end_protrusions:
            shape = analyze_protrusion_shape(p)
            if shape['is_blocky'] and not shape['is_elongated']:
                head_score -= 3.0  # Increased weight: Blocky at negative end = head at negative
                reasons.append('blocky_protrusion_at_negative')
            elif shape['is_elongated'] and shape['length_ratio'] > 2.0:  # Lowered threshold from 2.5
                head_score += 2.0  # Increased weight: Elongated at negative end = tail at negative, head at positive
                reasons.append('elongated_protrusion_at_negative')
        
        # Heuristic 2: Size analysis - head is typically LARGER than tail
        # Lowered threshold from 1.3x to 1.2x to be less strict
        positive_sizes = [p.get('size', 0) for p in positive_end_protrusions]
        negative_sizes = [p.get('size', 0) for p in negative_end_protrusions]
        
        if positive_sizes and negative_sizes:
            avg_positive_size = sum(positive_sizes) / len(positive_sizes)
            avg_negative_size = sum(negative_sizes) / len(negative_sizes)
            
            if avg_positive_size > avg_negative_size * 1.2:  # Lowered from 1.3
                head_score += 1.5  # Larger at positive = head at positive
                reasons.append('larger_protrusion_at_positive')
            elif avg_negative_size > avg_positive_size * 1.2:  # Lowered from 1.3
                head_score -= 1.5  # Larger at negative = head at negative
                reasons.append('larger_protrusion_at_negative')
        
        # Heuristic 3: Horn detection - horns indicate head region
        for horn_info in top_lateral_protrusions:
            if horn_info['norm_forward'] > 0.1:
                head_score += 3.0  # Horns at positive end = head at positive
                reasons.append('horns_at_positive')
            elif horn_info['norm_forward'] < -0.1:
                head_score -= 3.0  # Horns at negative end = head at negative
                reasons.append('horns_at_negative')
        
        confidence_factors.append(min(len(protrusions) / 5.0, 1.0))  # More protrusions = more confidence
    
    # Heuristic 4: Vertex distribution (fallback)
    # Body mass is typically in middle/back, head is lighter
    mesh = obj.data
    if len(mesh.vertices) > 0:
        positive_count = 0
        negative_count = 0
        
        # Sample vertices for efficiency
        sample_rate = max(1, len(mesh.vertices) // 1000)
        for i in range(0, len(mesh.vertices), sample_rate):
            vert = mesh.vertices[i]
            world_pos = obj.matrix_world @ vert.co
            relative_pos = world_pos - body_center
            forward_component = relative_pos.dot(primary_axis)
            
            if forward_component > 0:
                positive_count += 1
            else:
                negative_count += 1
        
        # Head end typically has fewer vertices (lighter)
        if positive_count > 0 and negative_count > 0:
            ratio = positive_count / negative_count
            if ratio < 0.7:
                head_score += 0.5  # Fewer at positive = head at positive (lighter)
                reasons.append('fewer_vertices_at_positive')
            elif ratio > 1.4:
                head_score -= 0.5  # Fewer at negative = head at negative
                reasons.append('fewer_vertices_at_negative')
    
    # Determine final direction
    if head_score > 0:
        head_direction = 1  # Head at positive direction
        is_inverted = False
    elif head_score < 0:
        head_direction = -1  # Head at negative direction
        is_inverted = True
    else:
        # Neutral - default to positive (standard orientation)
        head_direction = 1
        is_inverted = False
    
    # Calculate confidence
    confidence = min(abs(head_score) / 5.0, 1.0)  # Normalize to 0-1
    if confidence_factors:
        confidence = confidence * 0.7 + sum(confidence_factors) / len(confidence_factors) * 0.3
    
    # Combine reasons
    reason = ', '.join(reasons) if reasons else 'fallback_vertex_distribution'
    
    return {
        'head_direction': head_direction,
        'confidence': confidence,
        'reason': reason,
        'is_inverted': is_inverted
    }


def calculate_main_axis(obj, body_info, protrusions=None, invert_forward_axis=False):
    """
    Calculate the main axis (front/back direction) of the mesh.
    Uses the longest dimension in the horizontal plane and shape analysis
    to determine the correct forward direction (head location).
    
    Args:
        obj: Blender object with mesh data
        body_info: Result from detect_main_body()
        protrusions: Optional list of protrusions for better orientation detection
        invert_forward_axis: Manual override to invert the forward axis
        
    Returns:
        dict: {
            'forward': Vector (normalized forward direction, pointing toward head),
            'up': Vector (normalized up direction),
            'right': Vector (normalized right direction),
            'is_inverted': bool (True if head is at -Y)
        }
    """
    if not body_info:
        # Default axes (Y forward, Z up for Blender)
        return {
            'forward': Vector((0, 1, 0)),
            'up': Vector((0, 0, 1)),
            'right': Vector((1, 0, 0)),
            'is_inverted': False
        }
    
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    
    # Get all vertex coordinates
    all_coords = [obj.matrix_world @ bm.verts[i].co for i in range(len(bm.verts))]
    
    if not all_coords:
        bm.free()
        return {
            'forward': Vector((0, 1, 0)),
            'up': Vector((0, 0, 1)),
            'right': Vector((1, 0, 0)),
            'is_inverted': False
        }
    
    # Calculate bounding box dimensions
    min_co = Vector((min(c.x for c in all_coords),
                    min(c.y for c in all_coords),
                    min(c.z for c in all_coords)))
    max_co = Vector((max(c.x for c in all_coords),
                    max(c.y for c in all_coords),
                    max(c.z for c in all_coords)))
    size = max_co - min_co
    
    # Determine up axis (Z is up in Blender)
    up = Vector((0, 0, 1))
    
    # Forward is along the longest horizontal dimension
    # Compare X and Y dimensions
    if size.x > size.y:
        # X is longer, so Y is forward/back axis
        # Default to -Y as forward (standard Blender convention)
        forward_candidate_pos = Vector((0, 1, 0))
        forward_candidate_neg = Vector((0, -1, 0))
        right = Vector((1, 0, 0))
        primary_axis = 'Y'
    else:
        # Y is longer, so X is forward/back axis
        forward_candidate_pos = Vector((1, 0, 0))
        forward_candidate_neg = Vector((-1, 0, 0))
        right = Vector((0, 1, 0))
        primary_axis = 'X'
    
    bm.free()
    
    # Determine primary and lateral axes for orientation detection
    # Use the same axis determination logic as above
    if size.x > size.y:
        # X is longer, so Y is forward/back axis
        primary_axis_vec = Vector((0, 1, 0))
        lateral_axis_vec = Vector((1, 0, 0))
    else:
        # Y is longer, so X is forward/back axis
        primary_axis_vec = Vector((1, 0, 0))
        lateral_axis_vec = Vector((0, 1, 0))
    
    # Use detect_model_orientation() to determine which direction is head
    # Pass the determined primary axis to ensure consistency
    orientation = detect_model_orientation(obj, body_info, protrusions, 
                                          primary_axis=primary_axis_vec, 
                                          lateral_axis=lateral_axis_vec)
    
    # Apply orientation detection result
    if orientation['head_direction'] < 0:
        # Head is at negative direction
        forward = forward_candidate_neg
        is_inverted = True
    else:
        # Head is at positive direction
        forward = forward_candidate_pos
        is_inverted = False
    
    # Apply manual override if specified
    if invert_forward_axis:
        forward = -forward
        is_inverted = not is_inverted
    
    return {
        'forward': forward.normalized(),
        'up': up.normalized(),
        'right': right.normalized(),
        'is_inverted': is_inverted,
        'orientation_confidence': orientation['confidence'],
        'orientation_reason': orientation['reason']
    }


def identify_protrusions_geometry(obj, body_info, axes):
    """
    Identify protrusions (legs, head, tail, wings) using geometry analysis
    
    A protrusion is a connected region that:
    1. Extends significantly from the body center
    2. Has a narrow connection to the body
    3. Has elongated proportions (length > width)
    
    Args:
        obj: Blender object with mesh data
        body_info: Result from detect_main_body()
        axes: Result from calculate_main_axis()
        
    Returns:
        list: List of protrusion dicts with:
            - 'vertex_indices': set of vertex indices
            - 'center': Vector geometric center
            - 'relative_position': Vector position relative to body center
            - 'length_ratio': float (length/width ratio)
            - 'connection_point': Vector where protrusion connects to body
    """
    if not body_info or not obj or obj.type != 'MESH':
        return []
    
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    body_center = body_info['center']
    body_verts = body_info['vertex_indices']
    
    # Find vertices NOT in body (potential protrusions)
    non_body_verts = set(range(len(bm.verts))) - body_verts
    
    if not non_body_verts:
        bm.free()
        return []
    
    # Find connected components among non-body vertices
    visited = set()
    protrusions = []
    max_iterations = len(non_body_verts) * 2  # Safety limit to prevent infinite loops
    
    for start_idx in non_body_verts:
        if start_idx in visited:
            continue
        
        # BFS to find connected component (only among non-body verts)
        component_verts = set()
        queue = deque([start_idx])
        visited.add(start_idx)
        component_verts.add(start_idx)
        
        # Track connection points to body
        connection_points = []
        iterations = 0
        
        while queue and iterations < max_iterations:
            iterations += 1
            current_idx = queue.popleft()
            if current_idx >= len(bm.verts):
                continue
            current_vert = bm.verts[current_idx]
            
            for edge in current_vert.link_edges:
                other_vert = edge.other_vert(current_vert)
                other_idx = other_vert.index
                
                if other_idx in body_verts:
                    # This edge connects to body - record connection point
                    connection_points.append(obj.matrix_world @ current_vert.co)
                elif other_idx not in visited and other_idx in non_body_verts:
                    visited.add(other_idx)
                    component_verts.add(other_idx)
                    queue.append(other_idx)
        
        if iterations >= max_iterations:
            print(f"WARNING: Protrusion detection hit iteration limit ({max_iterations})")
            # Still process the component we found so far
            if not component_verts:
                continue
        
        # Calculate protrusion properties first (needed for validation)
        protrusion_coords = [obj.matrix_world @ bm.verts[i].co for i in component_verts]
        protrusion_center = calculate_geometric_center(protrusion_coords)
        
        # Calculate minimum distance from body center to ensure separation
        min_dist_from_body = min((obj.matrix_world @ bm.verts[i].co - body_center).length 
                                  for i in component_verts)
        
        # Calculate connection ratio (narrow connection = more protrusion-like)
        # Connection ratio = connection points / total vertices (lower = more protrusion-like)
        connection_ratio = len(connection_points) / max(len(component_verts), 1)
        
        # Only consider significant protrusions (at least 0.5% of mesh, lowered for small tails)
        # But also check if it's a tail-like protrusion (elongated, at back) - accept smaller ones
        is_potential_tail = False
        relative_pos = protrusion_center - body_center
        forward_component = relative_pos.dot(axes['forward'])
        
        # Calculate bounding box for length/width ratio
        min_co = Vector((min(c.x for c in protrusion_coords),
                        min(c.y for c in protrusion_coords),
                        min(c.z for c in protrusion_coords)))
        max_co = Vector((max(c.x for c in protrusion_coords),
                        max(c.y for c in protrusion_coords),
                        max(c.z for c in protrusion_coords)))
        size = max_co - min_co
        
        # Calculate length ratio: longest dimension / average of other two
        dims = sorted([size.x, size.y, size.z], reverse=True)
        if dims[1] + dims[2] > 0:
            length_ratio = dims[0] / ((dims[1] + dims[2]) / 2 + 0.001)
        else:
            length_ratio = 1.0
        
        # If it's at the back and elongated, it might be a tail even if small
        if forward_component < -0.2:  # Back position
            if length_ratio > 1.2:
                is_potential_tail = True
        
        # Accept if significant OR if it's a potential tail (even if small)
        if len(component_verts) < len(bm.verts) * 0.005 and not is_potential_tail:
            continue
        
        # IMPROVED: Filter out protrusions that are too close to body center (likely body vertices)
        # Legs should be separated from body center by at least 10% of body size
        body_bounds = body_info.get('bounds', (body_center, body_center))
        body_size_vec = body_bounds[1] - body_bounds[0]
        body_size_length = body_size_vec.length
        min_separation = body_size_length * 0.1  # At least 10% of body size
        
        if min_dist_from_body < min_separation and connection_ratio > 0.3:
            # Too close to body center and wide connection = likely body, not protrusion
            continue
        
        # Connection point (average if multiple)
        if connection_points:
            connection_point = calculate_geometric_center(connection_points)
        else:
            connection_point = protrusion_center
        
        # Relative position from body center
        relative_position = protrusion_center - body_center
        
        protrusions.append({
            'vertex_indices': component_verts,
            'center': protrusion_center,
            'relative_position': relative_position,
            'length_ratio': length_ratio,
            'connection_point': connection_point,
            'bounds': (min_co, max_co),
            'size': len(component_verts),
            'connection_ratio': connection_ratio,
            'min_dist_from_body': min_dist_from_body
        })
    
    bm.free()
    return protrusions


def detect_leg_pairs(protrusions, body_info, axes):
    """
    Detect leg pairs/groups using symmetry and grouping analysis.
    
    Legs characteristics:
    - Come in sets of 2 or 4 (pairs)
    - Cylindrical or squarish/rectangular (moderate length_ratio 1.5-3.0)
    - Symmetrical: left/right pairs are mirror images
    - All on same side: bottom position (norm_vertical < 0.1)
    - Similar size within pairs
    
    Args:
        protrusions: List of protrusion dicts from identify_protrusions_geometry()
        body_info: Result from detect_main_body()
        axes: Result from calculate_main_axis()
        
    Returns:
        dict: {
            'leg_groups': list of grouped protrusions (each group is a pair),
            'leg_candidates': list of protrusions that are likely legs,
            'confidence': float,
            'leg_count': int (2 or 4)
        }
    """
    if not protrusions or not body_info:
        return {
            'leg_groups': [],
            'leg_candidates': [],
            'confidence': 0.0,
            'leg_count': 0
        }
    
    body_center = body_info['center']
    body_bounds = body_info['bounds']
    body_size = body_bounds[1] - body_bounds[0]
    
    forward = axes['forward']
    up = axes['up']
    right = axes['right']
    
    # Calculate body dimensions for normalization
    body_height = max(abs(body_size.dot(up.normalized())), 0.001)
    body_width = max(abs(body_size.dot(right.normalized())), 0.001)
    body_length = max(abs(body_size.dot(forward.normalized())), 0.001)
    
    # Filter protrusions at bottom that are leg-shaped
    leg_candidates = []
    
    for p in protrusions:
        relative_pos = p['relative_position']
        
        # Calculate normalized position
        vertical_component = relative_pos.dot(up)
        lateral_component = relative_pos.dot(right)
        forward_component = relative_pos.dot(forward)
        
        norm_vertical = vertical_component / body_height
        norm_lateral = lateral_component / body_width
        norm_forward = forward_component / body_length
        
        # Check if at bottom position (all legs on same side)
        if norm_vertical < 0.1:  # Below body center
            # Check if cylindrical/squarish (leg-shaped)
            length_ratio = p.get('length_ratio', 1.0)
            
            # Legs have moderate elongation (1.5-3.0), not too elongated like tail
            if 1.5 <= length_ratio <= 3.0:
                leg_candidates.append({
                    'protrusion': p,
                    'norm_vertical': norm_vertical,
                    'norm_lateral': norm_lateral,
                    'norm_forward': norm_forward,
                    'length_ratio': length_ratio,
                    'size': p.get('size', 0)
                })
    
    # Group into pairs based on symmetry (left/right pairs)
    # Find pairs by matching lateral position (opposite signs, similar magnitude)
    leg_groups = []
    used_indices = set()
    
    # Sort by forward position to group front/back pairs
    leg_candidates.sort(key=lambda x: x['norm_forward'], reverse=True)
    
    for i, leg1 in enumerate(leg_candidates):
        if i in used_indices:
            continue
        
        # Find matching pair (opposite lateral position, similar forward position)
        best_match = None
        best_match_score = float('inf')
        best_match_idx = -1
        
        for j, leg2 in enumerate(leg_candidates):
            if j in used_indices or j == i:
                continue
            
            # Check if opposite lateral position (left/right pair)
            lateral_diff = abs(leg1['norm_lateral'] + leg2['norm_lateral'])  # Should be close to 0 for symmetric pair
            forward_diff = abs(leg1['norm_forward'] - leg2['norm_forward'])  # Should be similar
            size_diff = abs(leg1['size'] - leg2['size']) / max(leg1['size'], leg2['size'], 1)  # Similar size
            
            # Score: lower is better (more symmetric)
            score = lateral_diff + forward_diff * 0.5 + size_diff * 0.3
            
            # Check if this is a valid pair (opposite sides, similar forward position)
            if leg1['norm_lateral'] * leg2['norm_lateral'] < 0:  # Opposite sides
                if score < best_match_score and forward_diff < 0.3:  # Similar forward position
                    best_match_score = score
                    best_match = leg2
                    best_match_idx = j
        
        if best_match is not None:
            # Found a pair
            leg_groups.append([leg1['protrusion'], best_match['protrusion']])
            used_indices.add(i)
            used_indices.add(best_match_idx)
    
    # Calculate confidence based on how well pairs match
    confidence = 0.0
    if leg_groups:
        # More pairs = higher confidence
        if len(leg_groups) == 2:  # 4 legs (2 pairs)
            confidence = 0.9
        elif len(leg_groups) == 1:  # 2 legs (1 pair)
            confidence = 0.7
        else:
            confidence = 0.5
    
    # Count total legs
    leg_count = len(leg_groups) * 2
    
    # Also include unpaired leg candidates (might be single legs or misdetected)
    unpaired_candidates = [leg_candidates[i]['protrusion'] for i in range(len(leg_candidates)) if i not in used_indices]
    
    return {
        'leg_groups': leg_groups,
        'leg_candidates': [lc['protrusion'] for lc in leg_candidates],
        'unpaired_candidates': unpaired_candidates,
        'confidence': confidence,
        'leg_count': leg_count
    }


def analyze_protrusion_shape(protrusion):
    """
    Analyze shape characteristics of a protrusion to help distinguish body parts.
    
    Key shape heuristics:
    - Head: blocky/square/circular (length_ratio < 2.0), higher compactness
    - Tail: elongated/thin (length_ratio > 1.5), NEVER blocky
    - Legs: moderate length_ratio (1.5-3.0), cylindrical or squarish/rectangular
    - Wings: large lateral extent, mid-to-high vertical position
    
    Args:
        protrusion: Protrusion dict from identify_protrusions_geometry()
        
    Returns:
        dict: {
            'is_blocky': bool,  # Square/circular shape (length_ratio < 2.0)
            'is_elongated': bool,  # Thin/elongated shape (length_ratio > 1.5)
            'is_cylindrical': bool,  # Cylindrical/squarish (moderate length_ratio 1.5-3.0)
            'length_ratio': float,
            'compactness': float,  # Volume/surface area ratio
            'shape_type': 'head'|'tail'|'leg'|'wing'|'unknown'
        }
    """
    length_ratio = protrusion.get('length_ratio', 1.0)
    bounds = protrusion.get('bounds', (Vector(), Vector()))
    
    # Calculate compactness (simplified: use bounding box volume/surface area)
    size = bounds[1] - bounds[0]
    volume = abs(size.x * size.y * size.z)
    surface_area = 2 * (abs(size.x * size.y) + abs(size.y * size.z) + abs(size.x * size.z))
    compactness = volume / max(surface_area, 0.001)
    
    # Shape classification based on length_ratio
    # Head: blocky/square/circular (length_ratio < 2.0) - NEVER elongated
    is_blocky = length_ratio < 2.0
    
    # Tail: elongated/thin (length_ratio > 1.5) - NEVER blocky
    is_elongated = length_ratio > 1.5
    
    # Legs: cylindrical or squarish (moderate length_ratio 1.5-3.0)
    is_cylindrical = 1.5 <= length_ratio <= 3.0
    
    # Determine shape type based on characteristics
    # Head is NEVER elongated, tail is NEVER blocky
    if is_blocky and not is_elongated:
        shape_type = 'head'
    elif is_elongated and length_ratio > 3.0:
        # Very elongated = likely tail (not leg)
        shape_type = 'tail'
    elif is_cylindrical:
        # Moderate elongation = could be leg or tail depending on position
        shape_type = 'leg'  # Position will determine final classification
    elif is_elongated:
        # Elongated but not very elongated = could be tail or leg
        shape_type = 'tail'  # Default to tail, position will refine
    else:
        shape_type = 'unknown'
    
    return {
        'is_blocky': is_blocky,
        'is_elongated': is_elongated,
        'is_cylindrical': is_cylindrical,
        'length_ratio': length_ratio,
        'compactness': compactness,
        'shape_type': shape_type
    }


def classify_protrusion(protrusion, body_info, axes, template_type='quadruped', leg_candidates=None):
    """
    Classify a protrusion as head, leg, tail, or wing based on geometry-relative position
    and shape analysis.
    
    Classification rules (geometry-relative with shape analysis):
    - Head: Blocky/square shape (length_ratio < 2.0), top-front position, larger size (15-35% of body)
    - Tail: Elongated/thin shape (length_ratio > 1.5), back position, NEVER blocky
    - Legs: Cylindrical/squarish (length_ratio 1.5-3.0), bottom position, come in symmetrical pairs
    - Horns: Top + lateral position, should be included with head (not classified as legs)
    - Wings: Top + Side (high vertical, lateral position)
    
    Args:
        protrusion: Protrusion dict from identify_protrusions_geometry()
        body_info: Result from detect_main_body()
        axes: Result from calculate_main_axis()
        template_type: 'quadruped', 'biped', or 'flying'
        leg_candidates: Optional list of protrusions identified as leg candidates by detect_leg_pairs()
        
    Returns:
        str: Part name ('head', 'leg_front_l', 'leg_back_r', 'tail', 'wing_l', etc.)
    """
    body_center = body_info['center']
    body_bounds = body_info['bounds']
    body_size = body_bounds[1] - body_bounds[0]
    
    relative_pos = protrusion['relative_position']
    length_ratio = protrusion['length_ratio']
    
    forward = axes['forward']
    up = axes['up']
    right = axes['right']
    
    # Check if forward axis is inverted (head at -Y instead of +Y)
    is_inverted = axes.get('is_inverted', False)
    
    # Project relative position onto axes
    forward_component = relative_pos.dot(forward)
    vertical_component = relative_pos.dot(up)
    lateral_component = relative_pos.dot(right)
    
    # Normalize by body size for consistent thresholds
    body_length = max(abs(body_size.dot(forward.normalized())), 0.001)
    body_height = max(abs(body_size.dot(up.normalized())), 0.001)
    body_width = max(abs(body_size.dot(right.normalized())), 0.001)
    
    norm_forward = forward_component / body_length
    norm_vertical = vertical_component / body_height
    norm_lateral = lateral_component / body_width
    
    # CRITICAL FIX: If inverted, flip the forward component for classification
    # This makes thresholds work correctly for both orientations
    # When is_inverted=True (head at -Y), we need to flip so that:
    # - Head at -Y appears as norm_forward > 0.15 (after flip)
    # - Tail at +Y appears as norm_forward < -0.15 (after flip)
    if is_inverted:
        norm_forward = -norm_forward
    
    # Get shape analysis for this protrusion
    shape = analyze_protrusion_shape(protrusion)
    is_blocky = shape['is_blocky']
    is_elongated = shape['is_elongated']
    is_cylindrical = shape['is_cylindrical']
    
    # Check if this protrusion is in the leg candidates list
    is_leg_candidate = False
    if leg_candidates:
        for lc in leg_candidates:
            if lc.get('vertex_indices') == protrusion.get('vertex_indices'):
                is_leg_candidate = True
                break
    
    # ==========================================================================
    # HORN DETECTION (check first to exclude from leg classification)
    # Horns: Top position (+Z) and lateral position - should be included with head
    # ==========================================================================
    if norm_vertical > 0.3 and abs(norm_lateral) > 0.2:
        # Horns are at top and sides - exclude from leg classification
        # Horns are typically at head region, so include with head
        if abs(norm_forward) > 0.1:
            # Near head region - include with head
            return 'head'
    
    # ==========================================================================
    # HEAD DETECTION (shape-based: blocky/square, larger size)
    # Head: blocky/square shape (length_ratio < 2.0), top-front position
    # ==========================================================================
    if abs(norm_forward) > 0.15:  # Significant forward/back position
        # Check shape: head is blocky/square (low length_ratio)
        if is_blocky and not is_elongated:  # Head is NEVER elongated
            # Check size: head is typically 15-35% of body (larger than tail)
            body_vertex_count = len(body_info.get('vertex_indices', set()))
            protrusion_vertex_count = protrusion.get('size', 0)
            if body_vertex_count > 0:
                size_ratio = protrusion_vertex_count / body_vertex_count
                is_head_sized = 0.10 <= size_ratio <= 0.40  # Head size range (10-40%)
                
                if is_head_sized:
                    # Check vertical position (head is typically at top or mid-height)
                    if norm_vertical > -0.2:  # Not at bottom
                        # Head at forward position
                        if norm_forward > 0.15:
                            return 'head'
    
    # ==========================================================================
    # TAIL DETECTION (shape-based: elongated/thin, back position)
    # Tail: elongated/thin shape (length_ratio > 1.5), NEVER blocky
    # NOTE: Models may have no tail - don't force tail classification
    # ==========================================================================
    if norm_forward < -0.15:  # Back position
        # Tail is ALWAYS elongated (high length_ratio), NEVER blocky
        if is_elongated and not is_blocky:
            # Only classify as tail if it's clearly elongated (not a back leg)
            if length_ratio > 1.8:  # Higher threshold to avoid misclassifying back legs
                return 'tail'
        
        # Very elongated protrusion at back = definitely tail
        if length_ratio > 2.5:
            return 'tail'
        
        # Back position + not at bottom + not blocky = likely tail
        # But only if it's elongated enough to be a tail (not just a back protrusion)
        if norm_vertical > -0.2 and not is_blocky:
            if length_ratio > 1.5:  # Require more elongation
                return 'tail'
        
        # Very back position = tail regardless of shape (unless at bottom = back legs)
        # But only if it's elongated - blocky back protrusions are not tails
        if norm_forward < -0.4 and norm_vertical > -0.1 and length_ratio > 1.2:
            return 'tail'
    
    # ==========================================================================
    # WINGS: Top + Side (large lateral extent, mid-to-high vertical)
    # Works for flying template and also detects wings in other templates
    # ==========================================================================
    # Check for wing-like protrusions: large lateral extent, mid-to-high vertical
    if abs(norm_lateral) > 0.3 and norm_vertical > -0.1:
        # Wings have large lateral extent
        # Check if this protrusion has wing-like shape (large lateral, mid-height)
        protrusion_bounds = protrusion.get('bounds', (Vector(), Vector()))
        protrusion_size = protrusion_bounds[1] - protrusion_bounds[0]
        
        # Wings are typically wider than they are tall/deep
        lateral_extent = abs(protrusion_size.dot(right.normalized()))
        vertical_extent = abs(protrusion_size.dot(up.normalized()))
        forward_extent = abs(protrusion_size.dot(forward.normalized()))
        
        # Wing heuristic: lateral extent > vertical extent, and lateral > forward
        is_wing_shaped = lateral_extent > vertical_extent * 0.8 and lateral_extent > forward_extent * 0.5
        
        if template_type == 'flying' or is_wing_shaped:
            if norm_lateral < 0:
                return 'wing_l'
            else:
                return 'wing_r'
    
    # ==========================================================================
    # LEG DETECTION (shape-based: cylindrical/squarish, bottom position, pairs)
    # Legs: cylindrical/squarish (length_ratio 1.5-3.0), bottom position
    # ==========================================================================
    if norm_vertical < 0.1:  # Below body center (all legs on same side)
        # Check shape: legs are cylindrical/squarish (moderate length_ratio)
        # Legs are NOT as elongated as tail, NOT as blocky as head
        is_leg_shaped = is_cylindrical or (1.0 <= length_ratio <= 3.5)
        
        # If this protrusion is in the leg candidates list, prioritize leg classification
        if is_leg_shaped or is_leg_candidate:
            # Front legs: bottom + front
            if norm_forward > -0.1:
                if norm_lateral < 0:
                    return 'leg_front_l'
                else:
                    return 'leg_front_r'
            # Back legs: bottom + back
            else:
                if norm_lateral < 0:
                    return 'leg_back_l'
                else:
                    return 'leg_back_r'
    
    # ==========================================================================
    # ARMS (for biped): Mid-height + Side
    # ==========================================================================
    if template_type == 'biped':
        if abs(norm_lateral) > 0.3 and norm_vertical > -0.2:
            if norm_lateral < 0:
                return 'arm_l'
            else:
                return 'arm_r'
    
    # ==========================================================================
    # FALLBACK: Ambiguous position - use shape and position heuristics
    # ==========================================================================
    # Elongated protrusions at bottom are likely legs
    if norm_vertical < 0.2 and is_cylindrical:
        if norm_forward > 0:
            if norm_lateral < 0:
                return 'leg_front_l'
            else:
                return 'leg_front_r'
        else:
            if norm_lateral < 0:
                return 'leg_back_l'
            else:
                return 'leg_back_r'
    
    # Blocky protrusion at front = likely head
    if is_blocky and norm_forward > 0.1 and norm_vertical > -0.2:
        return 'head'
    
    # Elongated protrusion at back = likely tail (only if clearly elongated)
    # Don't force tail classification - models may have no tail
    if is_elongated and norm_forward < -0.1 and length_ratio > 1.8:
        return 'tail'
    
    # Large lateral protrusions at mid-height could be wings
    if abs(norm_lateral) > 0.4 and norm_vertical > -0.1:
        if norm_lateral < 0:
            return 'wing_l'
        else:
            return 'wing_r'
    
    # Fallback: assign to body
    # This is the correct behavior for models without tails or wings
    return 'body'


def segment_by_geometry(obj, template, template_type='quadruped', use_fast_mode=False, progress_callback=None, invert_forward_axis=False):
    """
    Segment mesh using geometry-relative positioning
    
    This is the primary segmentation method that uses actual mesh geometry
    rather than bounding box percentages.
    
    Key principle: Use geometry-relative positioning
    - Body = Center of geometry (largest connected component, central mass)
    - Head = Top front (relative to body center and main axis), blocky/square shape
    - Legs = Bottom front/back (relative to body center), cylindrical/squarish, symmetrical pairs
    - Tail = Back (relative to body center and main axis), elongated/thin shape
    - Wings = Top/side (relative to body center)
    
    Args:
        obj: Blender object with mesh data
        template: Segmentation template dictionary (used for part names)
        template_type: 'quadruped', 'biped', or 'flying'
        use_fast_mode: If True, skip expensive operations
        progress_callback: Optional function(percent, message) for progress updates
        invert_forward_axis: Manual override to invert the forward axis
        
    Returns:
        dict: Mapping of part names to lists of vertex indices
    """
    if not obj or obj.type != 'MESH':
        return {}
    
    mesh = obj.data
    
    if progress_callback:
        progress_callback(10, "Detecting main body...")
    
    # Step 1: Detect main body and calculate geometric center
    # In fast mode, use simpler detection
    if use_fast_mode:
        body_info = detect_main_body_fast(obj)
    else:
        body_info = detect_main_body(obj)
    
    if not body_info:
        # Fallback: return empty (caller should use spatial method)
        return {}
    
    if progress_callback:
        progress_callback(25, "Identifying protrusions for orientation detection...")
    
    # Step 2: Identify protrusions FIRST (needed for orientation detection)
    # Protrusion detection is expensive - skip for speed in preview mode
    if use_fast_mode or len(mesh.vertices) > 100000:
        # Skip protrusion detection for speed - use default axes
        protrusions = []
        # Use simple axis calculation without protrusions
        axes = calculate_main_axis(obj, body_info, protrusions=None, invert_forward_axis=invert_forward_axis)
    else:
        # First pass: get preliminary axes for protrusion detection
        preliminary_axes = {
            'forward': Vector((0, -1, 0)),  # Default -Y forward
            'up': Vector((0, 0, 1)),
            'right': Vector((1, 0, 0)),
            'is_inverted': False
        }
        
        if progress_callback:
            progress_callback(30, "Identifying protrusions...")
        
        protrusions = identify_protrusions_geometry(obj, body_info, preliminary_axes)
        
        if progress_callback:
            progress_callback(40, "Calculating main axis with orientation detection...")
        
        # Step 3: Calculate main axis with protrusions for better orientation detection
        axes = calculate_main_axis(obj, body_info, protrusions=protrusions, invert_forward_axis=invert_forward_axis)
        
        # Re-identify protrusions with correct axes if orientation was inverted
        if axes.get('is_inverted', False):
            if progress_callback:
                progress_callback(45, "Re-analyzing protrusions with corrected orientation...")
            protrusions = identify_protrusions_geometry(obj, body_info, axes)
    
    if progress_callback:
        progress_callback(50, "Detecting leg pairs...")
    
    # Step 3.5: Detect leg pairs/groups using symmetry analysis
    leg_info = detect_leg_pairs(protrusions, body_info, axes)
    leg_candidates = leg_info.get('leg_candidates', [])
    
    if progress_callback:
        progress_callback(55, "Initializing vertex groups...")
    
    # Step 4: Initialize vertex groups
    vertex_groups = {}
    
    # Initialize all expected parts from template
    for part_name in template.keys():
        vertex_groups[part_name] = []
    
    # Ensure body exists
    if 'body' not in vertex_groups:
        vertex_groups['body'] = []
    
    # Step 5: Assign body vertices
    vertex_groups['body'] = list(body_info['vertex_indices'])
    
    if progress_callback:
        progress_callback(60, "Classifying protrusions...")
    
    # Step 6: Classify and assign protrusions
    assigned_verts = set(body_info['vertex_indices'])
    
    # Group protrusions by classification
    classified_protrusions = defaultdict(list)
    
    for protrusion in protrusions:
        # Pass leg candidates to improve leg classification
        part_name = classify_protrusion(protrusion, body_info, axes, template_type, leg_candidates=leg_candidates)
        classified_protrusions[part_name].append(protrusion)
    
    # Handle multiple protrusions classified as the same part
    # (e.g., two protrusions both classified as 'leg_front_l')
    for part_name, protrusion_list in classified_protrusions.items():
        if part_name == 'body':
            # Add to body if classified as such
            for p in protrusion_list:
                vertex_groups['body'].extend(list(p['vertex_indices']))
                assigned_verts.update(p['vertex_indices'])
        elif len(protrusion_list) == 1:
            # Single protrusion for this part
            if part_name in vertex_groups:
                vertex_groups[part_name] = list(protrusion_list[0]['vertex_indices'])
                assigned_verts.update(protrusion_list[0]['vertex_indices'])
            else:
                # Part not in template, add to body
                vertex_groups['body'].extend(list(protrusion_list[0]['vertex_indices']))
                assigned_verts.update(protrusion_list[0]['vertex_indices'])
        else:
            # Multiple protrusions for same part - merge them
            merged_verts = set()
            for p in protrusion_list:
                merged_verts.update(p['vertex_indices'])
            
            if part_name in vertex_groups:
                vertex_groups[part_name] = list(merged_verts)
            else:
                vertex_groups['body'].extend(list(merged_verts))
            assigned_verts.update(merged_verts)
    
    if progress_callback:
        progress_callback(70, "Processing unassigned vertices...")
    
    # Step 7: Assign any unassigned vertices to nearest classified region
    # In fast mode, skip this expensive operation and assign all to body
    if use_fast_mode:
        # Fast mode: assign all unassigned vertices to body
        all_vert_indices = set(range(len(mesh.vertices)))
        unassigned = all_vert_indices - assigned_verts
        if unassigned:
            vertex_groups['body'].extend(list(unassigned))
    else:
        # Normal mode: assign unassigned vertices to nearest region
        all_vert_indices = set(range(len(mesh.vertices)))
        unassigned = all_vert_indices - assigned_verts
        
        if unassigned:
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.verts.ensure_lookup_table()
            
            # Limit processing to prevent hangs on very large meshes
            max_unassigned_to_process = 10000
            unassigned_list = list(unassigned)[:max_unassigned_to_process]
            
            if len(unassigned) > max_unassigned_to_process:
                print(f"WARNING: {len(unassigned)} unassigned vertices, processing first {max_unassigned_to_process}")
            
            for vert_idx in unassigned_list:
                if vert_idx >= len(bm.verts):
                    continue
                vert_co = obj.matrix_world @ bm.verts[vert_idx].co
                
                # Find nearest assigned vertex
                min_dist = float('inf')
                nearest_part = 'body'
                
                for part_name, vert_list in vertex_groups.items():
                    if not vert_list:
                        continue
                    # Sample for speed - limit to 100 vertices per part
                    sample_size = min(100, len(vert_list))
                    for assigned_idx in vert_list[:sample_size]:
                        if assigned_idx < len(bm.verts):
                            assigned_co = obj.matrix_world @ bm.verts[assigned_idx].co
                            dist = (vert_co - assigned_co).length
                            if dist < min_dist:
                                min_dist = dist
                                nearest_part = part_name
                
                vertex_groups[nearest_part].append(vert_idx)
            
            bm.free()
    
    if progress_callback:
        progress_callback(85, "Validating results...")
    
    # Step 8: Validate leg balance (not perfect symmetry, but should be "close")
    # Check left/right leg pairs for reasonable balance
    leg_pairs = [
        ('leg_front_l', 'leg_front_r'),
        ('leg_back_l', 'leg_back_r'),
        ('leg_l', 'leg_r')  # For biped templates
    ]
    
    for left_leg, right_leg in leg_pairs:
        if left_leg in vertex_groups and right_leg in vertex_groups:
            left_count = len(vertex_groups[left_leg])
            right_count = len(vertex_groups[right_leg])
            
            if left_count > 0 and right_count > 0:
                # Calculate asymmetry percentage
                avg_count = (left_count + right_count) / 2
                asymmetry = abs(left_count - right_count) / avg_count if avg_count > 0 else 0
                
                # Warn if asymmetry > 20% (suggests misclassification)
                if asymmetry > 0.20:
                    print(f"WARNING: {left_leg} ({left_count:,} verts) and {right_leg} ({right_count:,} verts) "
                          f"have {asymmetry:.1%} asymmetry - may indicate misclassification")
                # Log info if asymmetry is moderate (10-20%) - acceptable but worth noting
                elif asymmetry > 0.10:
                    print(f"INFO: {left_leg} and {right_leg} have {asymmetry:.1%} asymmetry (acceptable variation)")
    
    # Step 9: Fallback - if tail is empty, try to extract it from body region
    if 'tail' in template and (not vertex_groups.get('tail') or len(vertex_groups.get('tail', [])) == 0):
        # Find vertices in body that are at the back and might be tail
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        
        body_center = body_info['center']
        forward = axes['forward']
        
        # Find body vertices that are significantly behind the body center
        potential_tail_verts = []
        for vert_idx in vertex_groups.get('body', []):
            if vert_idx >= len(bm.verts):
                continue
            vert_co = obj.matrix_world @ bm.verts[vert_idx].co
            relative_pos = vert_co - body_center
            forward_component = relative_pos.dot(forward)
            
            # If vertex is significantly behind body center, it might be tail
            if forward_component < -0.3:  # Behind body
                potential_tail_verts.append(vert_idx)
        
        # If we found potential tail vertices, extract them
        if potential_tail_verts and len(potential_tail_verts) > len(mesh.vertices) * 0.001:  # At least 0.1% of mesh
            # Remove from body, add to tail
            vertex_groups['body'] = [v for v in vertex_groups.get('body', []) if v not in potential_tail_verts]
            vertex_groups['tail'] = potential_tail_verts
        
        bm.free()
    
    if progress_callback:
        progress_callback(90, "Finalizing segmentation...")
    
    # Step 10: Validate body is largest component and reclassify oversized parts
    total_vertices = len(mesh.vertices)
    body_count = len(vertex_groups.get('body', []))
    body_ratio = body_count / total_vertices if total_vertices > 0 else 0
    
    # Body should be at least 30% of total vertices for quadrupeds
    min_body_ratio = 0.30
    
    if body_ratio < min_body_ratio:
        print(f"WARNING: Body is only {body_ratio:.1%} of mesh (expected at least {min_body_ratio:.0%})")
        print(f"  Body: {body_count:,} vertices, Total: {total_vertices:,}")
        
        # Find the largest part (should be body)
        part_sizes = {name: len(verts) for name, verts in vertex_groups.items() if verts}
        if part_sizes:
            largest_part = max(part_sizes.items(), key=lambda x: x[1])
            if largest_part[0] != 'body' and largest_part[1] > body_count:
                print(f"  Largest part is '{largest_part[0]}' with {largest_part[1]:,} vertices - may indicate misclassification")
    
    # Check for oversized parts (head/legs that are larger than body)
    # Head should typically be 15-25% of body, legs 10-20% each
    if body_count > 0:
        for part_name, vert_list in vertex_groups.items():
            if part_name == 'body' or not vert_list:
                continue
            
            part_count = len(vert_list)
            part_to_body_ratio = part_count / body_count
            
            # Warn if part is larger than body (definitely wrong)
            if part_count > body_count:
                print(f"WARNING: '{part_name}' ({part_count:,} verts) is larger than body ({body_count:,} verts) - misclassification likely")
            
            # Warn if part is unusually large relative to body
            elif part_name.startswith('head') and part_to_body_ratio > 0.35:
                print(f"WARNING: '{part_name}' is {part_to_body_ratio:.1%} of body size (expected 15-25%) - may include neck/upper body")
            elif part_name.startswith('leg') and part_to_body_ratio > 0.25:
                print(f"WARNING: '{part_name}' is {part_to_body_ratio:.1%} of body size (expected 10-20%) - may include body vertices")
    
    # Remove empty groups (but keep groups that exist in template even if empty)
    # Only remove if they're truly empty and not in template
    final_groups = {}
    for part_name in template.keys():
        if part_name in vertex_groups and vertex_groups[part_name]:
            final_groups[part_name] = vertex_groups[part_name]
        elif part_name in template:
            # Keep empty groups that are in template (for UI display)
            final_groups[part_name] = []
    
    return final_groups


def analyze_mesh_geometry(obj):
    """
    Comprehensive mesh geometry analysis for segmentation
    
    Args:
        obj: Blender object with mesh data
        
    Returns:
        dict: Analysis results including body info, axes, protrusions, recommendations
    """
    if not obj or obj.type != 'MESH':
        return None
    
    # Detect main body
    body_info = detect_main_body(obj)
    
    if not body_info:
        return {
            'success': False,
            'error': 'Could not detect main body',
            'recommendation': 'Use spatial-only segmentation'
        }
    
    # Calculate axes
    axes = calculate_main_axis(obj, body_info)
    
    # Find protrusions
    protrusions = identify_protrusions_geometry(obj, body_info, axes)
    
    # Analyze protrusion distribution
    protrusion_count = len(protrusions)
    
    # Determine likely template type
    if protrusion_count >= 5:
        # Many protrusions: likely quadruped (4 legs + head/tail)
        likely_template = 'quadruped'
    elif protrusion_count >= 3:
        # Could be biped (2 legs + 2 arms + head) or quadruped
        likely_template = 'quadruped'
    else:
        # Few protrusions: might need manual adjustment
        likely_template = 'quadruped'
    
    return {
        'success': True,
        'body_info': body_info,
        'axes': axes,
        'protrusions': protrusions,
        'protrusion_count': protrusion_count,
        'likely_template': likely_template,
        'body_vertex_count': len(body_info['vertex_indices']),
        'total_vertex_count': len(obj.data.vertices),
        'body_coverage': len(body_info['vertex_indices']) / max(len(obj.data.vertices), 1)
    }
