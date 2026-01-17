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


def calculate_main_axis(obj, body_info):
    """
    Calculate the main axis (front/back direction) of the mesh
    Uses the longest dimension in the horizontal plane (X-Z for Y-up, X-Y for Z-up)
    
    Args:
        obj: Blender object with mesh data
        body_info: Result from detect_main_body()
        
    Returns:
        dict: {
            'forward': Vector (normalized forward direction),
            'up': Vector (normalized up direction),
            'right': Vector (normalized right direction)
        }
    """
    if not body_info:
        # Default axes (Y forward, Z up for Blender)
        return {
            'forward': Vector((0, 1, 0)),
            'up': Vector((0, 0, 1)),
            'right': Vector((1, 0, 0))
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
            'right': Vector((1, 0, 0))
        }
    
    # Calculate bounding box dimensions
    min_co = Vector((min(c.x for c in all_coords),
                    min(c.y for c in all_coords),
                    min(c.z for c in all_coords)))
    max_co = Vector((max(c.x for c in all_coords),
                    max(c.y for c in all_coords),
                    max(c.z for c in all_coords)))
    size = max_co - min_co
    
    # Determine up axis (smallest horizontal dimension typically)
    # In Blender, Z is usually up
    up = Vector((0, 0, 1))
    
    # Forward is the longest horizontal dimension
    # Compare X and Y dimensions
    if size.x > size.y:
        # X is longer, so Y is forward/back (standard Blender -Y forward)
        forward = Vector((0, -1, 0))  # -Y is forward in Blender
        right = Vector((1, 0, 0))
    else:
        # Y is longer, so X is forward/back
        forward = Vector((1, 0, 0))
        right = Vector((0, 1, 0))
    
    # Refine forward direction using vertex distribution
    # The "front" typically has fewer vertices (head end) vs "back" (body mass)
    center = body_info['center']
    
    # Count vertices in front vs back
    forward_count = 0
    backward_count = 0
    
    for co in all_coords:
        relative = co - center
        projection = relative.dot(forward)
        if projection > 0:
            forward_count += 1
        else:
            backward_count += 1
    
    # If more vertices are in the "forward" direction, flip (head is usually lighter)
    # Actually, for animals, the body mass is usually in the middle/back
    # This heuristic may need adjustment based on actual models
    
    bm.free()
    
    return {
        'forward': forward.normalized(),
        'up': up.normalized(),
        'right': right.normalized()
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


def classify_protrusion(protrusion, body_info, axes, template_type='quadruped'):
    """
    Classify a protrusion as head, leg, tail, or wing based on geometry-relative position
    
    Classification rules (geometry-relative):
    - Head: Top + Front (high vertical, forward position)
    - Front Legs: Bottom + Front (low vertical, forward position)
    - Back Legs: Bottom + Back (low vertical, backward position)
    - Tail: Back + Any vertical (backward position, any height)
    - Wings: Top + Side (high vertical, lateral position)
    
    Args:
        protrusion: Protrusion dict from identify_protrusions_geometry()
        body_info: Result from detect_main_body()
        axes: Result from calculate_main_axis()
        template_type: 'quadruped', 'biped', or 'flying'
        
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
    
    # Project relative position onto axes
    forward_component = relative_pos.dot(forward)
    vertical_component = relative_pos.dot(up)
    lateral_component = relative_pos.dot(right)
    
    # Normalize by body size for consistent thresholds
    body_length = max(body_size.dot(forward.normalized()), 0.001)
    body_height = max(body_size.dot(up.normalized()), 0.001)
    body_width = max(body_size.dot(right.normalized()), 0.001)
    
    norm_forward = forward_component / body_length
    norm_vertical = vertical_component / body_height
    norm_lateral = lateral_component / body_width
    
    # Classification thresholds
    # Adjusted for more accurate detection
    
    # HEAD: Top front - high vertical component, forward position
    # Tightened thresholds to prevent neck/upper body from being included
    if norm_vertical > 0.15 and norm_forward > 0.2:  # Increased vertical threshold from 0.1 to 0.15
        # Additional checks to prevent misclassification
        # Head usually has moderate length ratio (not too elongated like neck)
        if length_ratio < 3.5:  # Tightened from 4.0 to exclude elongated neck regions
            # Check size relative to body - head should be 15-35% of body size
            body_vertex_count = len(body_info.get('vertex_indices', set()))
            protrusion_vertex_count = protrusion.get('size', 0)
            if body_vertex_count > 0:
                size_ratio = protrusion_vertex_count / body_vertex_count
                # Head should not be larger than 35% of body (typically 15-25%)
                if size_ratio <= 0.35:
                    return 'head'
    
    # TAIL: Back position - prioritize this classification
    # Tail can be at various vertical positions but is always at the back
    if norm_forward < -0.2:  # Lowered threshold - any significant backward position
        # Check if it's elongated (typical tail shape)
        if length_ratio > 1.2:  # Lowered from 1.5
            return 'tail'
        # Even if not elongated, if it's clearly at the back and not a leg, it's tail
        # Legs are at bottom (norm_vertical < 0.1), tail can be at any height
        if norm_forward < -0.3 and norm_vertical > -0.3:  # Back but not bottom = tail
            return 'tail'
        # Very back position = tail regardless of shape
        if norm_forward < -0.4:
            return 'tail'
    
    # WINGS (for flying template): Top + Side
    if template_type == 'flying':
        if norm_vertical > 0.0 and abs(norm_lateral) > 0.3:
            if norm_lateral < 0:
                return 'wing_l'
            else:
                return 'wing_r'
    
    # LEGS: Bottom position
    if norm_vertical < 0.1:  # Below body center
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
    
    # ARMS (for biped): Mid-height + Side
    if template_type == 'biped':
        if abs(norm_lateral) > 0.3 and norm_vertical > -0.2:
            if norm_lateral < 0:
                return 'arm_l'
            else:
                return 'arm_r'
    
    # Default: if position is ambiguous, check length ratio
    # Elongated protrusions at bottom are likely legs
    if norm_vertical < 0.2 and length_ratio > 1.5:
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
    
    # Fallback: assign to body
    return 'body'


def segment_by_geometry(obj, template, template_type='quadruped', use_fast_mode=False, progress_callback=None):
    """
    Segment mesh using geometry-relative positioning
    
    This is the primary segmentation method that uses actual mesh geometry
    rather than bounding box percentages.
    
    Key principle: Use geometry-relative positioning
    - Body = Center of geometry (largest connected component, central mass)
    - Head = Top front (relative to body center and main axis)
    - Legs = Bottom front/back (relative to body center)
    - Tail = Back (relative to body center and main axis)
    - Wings = Top/side (relative to body center)
    
    Args:
        obj: Blender object with mesh data
        template: Segmentation template dictionary (used for part names)
        template_type: 'quadruped', 'biped', or 'flying'
        use_fast_mode: If True, skip expensive operations
        progress_callback: Optional function(percent, message) for progress updates
        
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
        progress_callback(30, "Calculating main axis...")
    
    # Step 2: Calculate main axis (front/back direction)
    axes = calculate_main_axis(obj, body_info)
    
    if progress_callback:
        progress_callback(40, "Identifying protrusions...")
    
    # Step 3: Identify protrusions (skip in fast mode or for large meshes)
    # Protrusion detection is expensive - skip for speed in preview mode
    if use_fast_mode or len(mesh.vertices) > 100000:
        # Skip protrusion detection for speed
        protrusions = []
    else:
        protrusions = identify_protrusions_geometry(obj, body_info, axes)
    
    if progress_callback:
        progress_callback(50, "Initializing vertex groups...")
    
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
        part_name = classify_protrusion(protrusion, body_info, axes, template_type)
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
