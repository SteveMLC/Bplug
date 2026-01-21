"""
Mesh optimization algorithms
QEM edge collapse and centroid clustering implementations
Preserves UV coordinates, vertex colors, and material assignments
"""

import bmesh
from mathutils import Vector
import math
import time
from typing import Optional, Callable, Set, Tuple
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    # Fallback for quadric computation without numpy
    pass


class TimeoutManager:
    """
    Manages time-limited processing chunks for large mesh operations.
    
    Usage:
        timeout_mgr = TimeoutManager(time_limit_per_chunk=1.0)
        timeout_mgr.start_chunk()
        for item in items:
            if timeout_mgr.check_timeout():
                break  # Stop processing
            process(item)
    """
    def __init__(self, time_limit_per_chunk: float = 1.0):
        self.time_limit = time_limit_per_chunk
        self.start_time: Optional[float] = None
        self.chunk_count = 0
    
    def start_chunk(self):
        """Start a new time-limited chunk"""
        self.start_time = time.time()
        self.chunk_count += 1
    
    def check_timeout(self) -> bool:
        """Returns True if timeout exceeded"""
        if self.start_time is None:
            return False
        elapsed = time.time() - self.start_time
        return elapsed > self.time_limit
    
    def get_progress(self) -> float:
        """Returns progress within current chunk (0.0-1.0)"""
        if self.start_time is None:
            return 0.0
        elapsed = time.time() - self.start_time
        return min(1.0, elapsed / self.time_limit)
    
    def reset(self):
        """Reset timeout manager"""
        self.start_time = None
        self.chunk_count = 0


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
    # Map 0..1 -> 0.1..1.0 scaling factor (more conservative)
    #  - very small reduction (1-5%) ≈ 0.1 * grid_size (very gentle)
    #  - medium reduction (10-20%) ≈ 0.5 * grid_size (moderate)
    #  - large reduction (50%+) ≈ 1.0 * grid_size (full strength)
    # Use exponential scaling for better control at low reductions
    if tr < 0.1:
        # Very small reductions: use minimal scaling
        scale = 0.1 + 0.2 * (tr / 0.1)  # 0.1 to 0.3 for 0-10% reduction
    else:
        # Larger reductions: scale more aggressively
        scale = 0.3 + 0.7 * ((tr - 0.1) / 0.9)  # 0.3 to 1.0 for 10-100% reduction
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
    # Increased limit for large meshes - allow more time for queue building
    start_time = time.time()
    initial_face_count_for_time = initial_face_count
    # Scale time limit with mesh size: 3s for small, up to 30s for very large
    TIME_LIMIT_SECONDS = min(30.0, 3.0 + (initial_face_count_for_time / 50000) * 2.0)
    
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
    # Allow more time for actual collapse operations (separate from queue building)
    collapse_start_time = time.time()
    COLLAPSE_TIME_LIMIT = min(60.0, 10.0 + (initial_face_count_for_time / 50000) * 5.0)
    
    for priority, edge in edge_priorities:
        # Check collapse time limit (separate from queue building)
        if time.time() - collapse_start_time > COLLAPSE_TIME_LIMIT:
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


def detect_feature_edges(
    bm: bmesh.types.BMesh,
    feature_angle_threshold: float = math.radians(30.0),
    batch_size: int = 50000,
    progress_callback: Optional[Callable[[float], None]] = None,
    timeout_manager: Optional[TimeoutManager] = None
) -> Set[int]:
    """
    Detect sharp edges using dihedral angle - optimized for large meshes.
    
    Args:
        bm: bmesh object
        feature_angle_threshold: Angle in radians (default ~30°)
        batch_size: Number of edges to process per batch (default 50K)
        progress_callback: Optional callback(progress: float) for UI updates
        timeout_manager: Optional timeout manager for time-limited processing
    
    Returns:
        set[int]: Set of edge indices that are feature edges
    """
    feature_edges: Set[int] = set()
    
    all_edges = list(bm.edges)
    total_edges = len(all_edges)
    
    if total_edges == 0:
        return feature_edges
    
    processed = 0
    batch_start = 0
    
    while batch_start < total_edges:
        if timeout_manager and timeout_manager.check_timeout():
            break
        
        batch_end = min(batch_start + batch_size, total_edges)
        batch = all_edges[batch_start:batch_end]
        
        for edge in batch:
            if len(edge.link_faces) != 2:
                continue
            
            try:
                f1, f2 = edge.link_faces
                angle = f1.normal.angle(f2.normal)
                
                if angle > feature_angle_threshold:
                    feature_edges.add(edge.index)
            
            except (ValueError, AttributeError):
                continue
        
        processed += len(batch)
        batch_start = batch_end
        
        if progress_callback:
            progress = processed / total_edges
            progress_callback(progress)
    
    return feature_edges


def classify_corner_vertices(
    bm: bmesh.types.BMesh,
    feature_edges: Set[int],
    min_feature_edges: int = 2,
    progress_callback: Optional[Callable[[float], None]] = None
) -> Set[int]:
    """
    Classify vertices as corners based on incident feature edges.
    """
    corner_vertices: Set[int] = set()
    vert_feature_count: dict[int, int] = {}
    
    total_feature_edges = len(feature_edges)
    processed = 0
    
    for edge_idx in feature_edges:
        try:
            edge = bm.edges[edge_idx]
            if not edge.is_valid:
                continue
            
            for vert in edge.verts:
                vert_idx = vert.index
                vert_feature_count[vert_idx] = vert_feature_count.get(vert_idx, 0) + 1
        
        except (IndexError, AttributeError):
            continue
        
        processed += 1
        if progress_callback and processed % 10000 == 0:
            progress_callback(processed / total_feature_edges)
    
    for vert_idx, count in vert_feature_count.items():
        if count >= min_feature_edges:
            corner_vertices.add(vert_idx)
    
    return corner_vertices


def mark_protected_geometry(
    bm: bmesh.types.BMesh,
    corner_vertices: Set[int],
    feature_edges: Set[int]
) -> Tuple[Set[int], Set[int]]:
    """
    Mark protected vertices and edges for decimation.
    """
    protected_vertices = set(corner_vertices)
    protected_edges = set(feature_edges)
    
    for vert_idx in corner_vertices:
        try:
            vert = bm.verts[vert_idx]
            if not vert.is_valid:
                continue
            
            for edge in vert.link_edges:
                protected_edges.add(edge.index)
        
        except (IndexError, AttributeError):
            continue
    
    return protected_vertices, protected_edges


def compute_vertex_quadric_lazy(
    bm: bmesh.types.BMesh,
    vertex_index: int,
    cache: dict
):
    """
    Compute QEM quadric matrix for vertex (lazy evaluation with caching).
    
    Quadric Q for vertex v is sum of (A^T * A) for all incident faces,
    where A represents the plane equation ax + by + cz + d = 0.
    
    Returns numpy array if available, otherwise list of lists.
    """
    # Check cache
    if vertex_index in cache:
        return cache[vertex_index]
    
    try:
        vert = bm.verts[vertex_index]
        if not vert.is_valid:
            if NUMPY_AVAILABLE:
                Q = np.zeros((4, 4))
            else:
                Q = [[0.0] * 4 for _ in range(4)]
            cache[vertex_index] = Q
            return Q
        
        if NUMPY_AVAILABLE:
            Q = np.zeros((4, 4))
        else:
            Q = [[0.0] * 4 for _ in range(4)]
        
        # Sum quadrics from all incident faces
        for face in vert.link_faces:
            if len(face.verts) < 3:
                continue
            
            # Compute plane equation: ax + by + cz + d = 0
            normal = face.normal
            point = face.verts[0].co
            
            a, b, c = normal.x, normal.y, normal.z
            d = -(a * point.x + b * point.y + c * point.z)
            
            # Quadric for plane: p = [a, b, c, d]^T
            # Q = p * p^T (outer product)
            if NUMPY_AVAILABLE:
                p = np.array([a, b, c, d])
                Q += np.outer(p, p)
            else:
                # Manual outer product
                p = [a, b, c, d]
                for i in range(4):
                    for j in range(4):
                        Q[i][j] += p[i] * p[j]
        
        cache[vertex_index] = Q
        return Q
    
    except (IndexError, AttributeError):
        if NUMPY_AVAILABLE:
            Q = np.zeros((4, 4))
        else:
            Q = [[0.0] * 4 for _ in range(4)]
        cache[vertex_index] = Q
        return Q


def compute_qem_error(
    position: Vector,
    quadric1,
    quadric2
) -> float:
    """
    Compute QEM error for collapsing edge to given position.
    
    Error = v^T * (Q1 + Q2) * v, where v = [x, y, z, 1]^T
    """
    if NUMPY_AVAILABLE:
        combined_Q = quadric1 + quadric2
        v = np.array([position.x, position.y, position.z, 1.0])
        error = v.T @ combined_Q @ v
        return float(error)
    else:
        # Manual computation without numpy
        combined_Q = [[quadric1[i][j] + quadric2[i][j] for j in range(4)] for i in range(4)]
        v = [position.x, position.y, position.z, 1.0]
        
        # Compute v^T * Q * v
        result = 0.0
        for i in range(4):
            for j in range(4):
                result += v[i] * combined_Q[i][j] * v[j]
        return result


def qem_edge_collapse_advanced(
    mesh,
    target_reduction: float,
    preserve_corners: bool = True,
    corner_threshold: int = 2,
    feature_angle: float = math.radians(30.0),
    corner_weight: float = 50.0,
    feature_weight: float = 10.0,
    time_limit_per_chunk: float = 1.0,
    max_queue_size: int = 100000,
    use_lazy_quadrics: bool = True,
    progress_callback: Optional[Callable[[float], None]] = None
) -> int:
    """
    Advanced QEM edge collapse with corner preservation - optimized for large meshes.
    """
    if target_reduction <= 0 or target_reduction >= 1:
        return 0
    
    import heapq
    
    # Create bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    
    initial_face_count = len(bm.faces)
    target_face_count = int(initial_face_count * (1 - target_reduction))
    
    # Detect features and corners (one-time, can be expensive)
    protected_vertices: Set[int] = set()
    protected_edges: Set[int] = set()
    
    if preserve_corners:
        if progress_callback:
            progress_callback(0.1)  # 10% for feature detection
        
        timeout_mgr = TimeoutManager(time_limit_per_chunk=time_limit_per_chunk * 2)
        timeout_mgr.start_chunk()
        
        feature_edges = detect_feature_edges(
            bm, feature_angle, batch_size=50000,
            progress_callback=lambda p: progress_callback(0.1 * p) if progress_callback else None,
            timeout_manager=timeout_mgr
        )
        
        corner_vertices = classify_corner_vertices(
            bm, feature_edges, min_feature_edges=corner_threshold,
            progress_callback=lambda p: progress_callback(0.1 + 0.05 * p) if progress_callback else None
        )
        
        protected_vertices, protected_edges = mark_protected_geometry(
            bm, corner_vertices, feature_edges
        )
    
    # Quadric cache (lazy evaluation)
    quadric_cache: dict = {}
    
    # Build priority queue (limited size for large meshes)
    edge_queue: list = []
    processed_edges = 0
    
    if progress_callback:
        progress_callback(0.2)  # 20% for queue building
    
    timeout_mgr = TimeoutManager(time_limit_per_chunk=time_limit_per_chunk * 2)
    timeout_mgr.start_chunk()
    
    # Build queue in batches
    all_edges = list(bm.edges)
    batch_size = 10000
    
    # Handle empty mesh case
    if len(all_edges) == 0:
        if progress_callback:
            progress_callback(1.0)
        bm.to_mesh(mesh)
        mesh.update()
        bm.free()
        return 0
    
    for i in range(0, len(all_edges), batch_size):
        if timeout_mgr.check_timeout():
            break
        
        batch = all_edges[i:min(i + batch_size, len(all_edges))]
        
        for edge in batch:
            if not edge.is_valid:
                continue
            
            # Skip protected edges
            if edge.index in protected_edges:
                continue
            
            if len(edge.link_faces) == 0:
                continue
            
            # Compute collapse cost
            v1_idx, v2_idx = edge.verts[0].index, edge.verts[1].index
            
            if use_lazy_quadrics:
                q1 = compute_vertex_quadric_lazy(bm, v1_idx, quadric_cache)
                q2 = compute_vertex_quadric_lazy(bm, v2_idx, quadric_cache)
            else:
                if v1_idx not in quadric_cache:
                    quadric_cache[v1_idx] = compute_vertex_quadric_lazy(bm, v1_idx, quadric_cache)
                if v2_idx not in quadric_cache:
                    quadric_cache[v2_idx] = compute_vertex_quadric_lazy(bm, v2_idx, quadric_cache)
                q1, q2 = quadric_cache[v1_idx], quadric_cache[v2_idx]
            
            # Optimal collapse position (minimizes error)
            midpoint = (edge.verts[0].co + edge.verts[1].co) / 2
            base_cost = compute_qem_error(midpoint, q1, q2)
            
            # Apply feature weights
            weight = 1.0
            if v1_idx in protected_vertices or v2_idx in protected_vertices:
                weight *= corner_weight
            elif edge.index in protected_edges:
                weight *= feature_weight
            
            cost = base_cost * weight
            
            # Add to queue
            heapq.heappush(edge_queue, (cost, edge.index))
            processed_edges += 1
        
        # Limit queue size
        if len(edge_queue) > max_queue_size:
            edge_queue = heapq.nsmallest(max_queue_size, edge_queue)
            heapq.heapify(edge_queue)
        
        if progress_callback:
            if len(all_edges) > 0:
                progress = 0.2 + 0.3 * (i / len(all_edges))  # 20-50% for queue
                progress_callback(progress)
            else:
                progress_callback(0.5)  # Skip to 50% if no edges
    
    # Collapse edges until target
    collapsed = 0
    timeout_mgr.start_chunk()
    
    if progress_callback:
        progress_callback(0.5)  # 50% for collapses
    
    while edge_queue and len(bm.faces) > target_face_count:
        if timeout_mgr.check_timeout():
            break
        
        cost, edge_idx = heapq.heappop(edge_queue)
        
        try:
            # Edge indices may become invalid after collapses, so we catch IndexError
            edge = bm.edges[edge_idx]
            if not edge.is_valid:
                continue
            
            # Skip if protected
            if edge.index in protected_edges:
                continue
            
            # Collapse edge
            v1, v2 = edge.verts
            midpoint = (v1.co + v2.co) / 2
            
            bmesh.ops.pointmerge(bm, verts=[v1, v2], merge_co=midpoint)
            
            collapsed += 1
            
            # Update lookup tables periodically
            if collapsed % 1000 == 0:
                bm.faces.ensure_lookup_table()
                bm.verts.ensure_lookup_table()
                bm.edges.ensure_lookup_table()
            
            if progress_callback and collapsed % 5000 == 0:
                remaining = len(bm.faces) - target_face_count
                total_remaining = initial_face_count - target_face_count
                if total_remaining > 0:
                    progress = 0.5 + 0.4 * (1.0 - remaining / total_remaining)
                    progress_callback(min(0.9, progress))
        
        except (IndexError, AttributeError, ValueError):
            # Edge may have been removed or index invalidated by previous collapses
            continue
    
    # Cleanup
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.001)
    
    degenerate_faces = [f for f in bm.faces if f.calc_area() < 0.0001 or len(f.verts) < 3]
    if degenerate_faces:
        bmesh.ops.delete(bm, geom=degenerate_faces, context='FACES')
    
    # Update mesh
    bm.to_mesh(mesh)
    mesh.update()
    bm.free()
    
    if progress_callback:
        progress_callback(1.0)
    
    final_face_count = len(mesh.polygons)
    return initial_face_count - final_face_count
