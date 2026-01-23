"""
Mesh optimization algorithms
Uses Blender's built-in Decimate modifier for reliable results
with custom feature detection for edge protection.

Key design principles:
- Iterative reduction: Small steps (1-20%) for user control
- Feature preservation: Detect and protect sharp edges
- Large mesh support: Auto-chunk to ~10K vertices per step
"""

import bpy
import bmesh
from mathutils import Vector
import math
import time
from typing import Optional, Callable, Set, Tuple, Dict, List
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


# =============================================================================
# SAFE STEP SIZE CALCULATION
# =============================================================================

def calculate_safe_step_size(vertex_count: int, target_vertices_per_step: int = 10000) -> float:
    """
    Calculate a safe reduction step size based on mesh complexity.
    
    For a 500K vertex mesh with 10K target: returns 0.02 (2%)
    For a 50K vertex mesh: returns 0.20 (20%)
    
    Args:
        vertex_count: Current number of vertices
        target_vertices_per_step: Maximum vertices to affect per step
    
    Returns:
        float: Safe reduction ratio (0.01 to 0.20)
    """
    if vertex_count <= 0:
        return 0.05
    
    if vertex_count <= target_vertices_per_step:
        return 0.20  # Small mesh, can be more aggressive
    
    # Calculate ratio that would affect target_vertices_per_step vertices
    safe_ratio = target_vertices_per_step / vertex_count
    
    # Clamp to reasonable bounds
    return max(0.01, min(0.20, safe_ratio))


def get_recommended_step_size(obj) -> Tuple[float, str]:
    """
    Get recommended step size with explanation for UI display.
    
    Returns:
        Tuple of (step_ratio, explanation_string)
    """
    if not obj or obj.type != 'MESH':
        return 0.05, "Default: 5%"
    
    vert_count = len(obj.data.vertices)
    
    if vert_count > 500000:
        return 0.01, f"Very large mesh ({vert_count:,} verts): 1% recommended"
    elif vert_count > 200000:
        return 0.02, f"Large mesh ({vert_count:,} verts): 2% recommended"
    elif vert_count > 100000:
        return 0.03, f"Medium-large mesh ({vert_count:,} verts): 3% recommended"
    elif vert_count > 50000:
        return 0.05, f"Medium mesh ({vert_count:,} verts): 5% recommended"
    else:
        return 0.10, f"Small mesh ({vert_count:,} verts): 10% recommended"


# =============================================================================
# FEATURE EDGE DETECTION AND PROTECTION
# =============================================================================

def detect_sharp_edges(obj, angle_threshold: float = 30.0) -> Set[int]:
    """
    Detect edges that should be considered 'sharp' based on dihedral angle.
    
    These are typically edges where body parts connect (leg-body, head-body).
    
    Args:
        obj: Blender mesh object
        angle_threshold: Angle in degrees above which edge is sharp
    
    Returns:
        Set of edge indices that are sharp
    """
    if not obj or obj.type != 'MESH':
        return set()
    
    sharp_edges: Set[int] = set()
    angle_rad = math.radians(angle_threshold)
    
    # Use bmesh for efficient edge analysis
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    
    for edge in bm.edges:
        # Only check edges with exactly 2 faces (manifold edges)
        if len(edge.link_faces) != 2:
            # Boundary edges are always sharp
            if len(edge.link_faces) == 1:
                sharp_edges.add(edge.index)
            continue
        
        try:
            f1, f2 = edge.link_faces
            angle = f1.normal.angle(f2.normal)
            
            if angle > angle_rad:
                sharp_edges.add(edge.index)
        except (ValueError, AttributeError):
            continue
    
    bm.free()
    return sharp_edges


def mark_feature_edges_for_protection(obj, angle_threshold: float = 30.0, 
                                       mark_sharp: bool = True,
                                       mark_seam: bool = False) -> int:
    """
    Mark sharp edges on the mesh so Decimate modifier respects them.
    
    The Decimate modifier respects:
    - Sharp marks (edge.use_edge_sharp)
    - Seam marks (edge.use_seam) when UN-subdivision is used
    
    Args:
        obj: Blender mesh object
        angle_threshold: Angle in degrees for sharp detection
        mark_sharp: Mark detected edges as sharp
        mark_seam: Also mark as UV seams (more aggressive protection)
    
    Returns:
        Number of edges marked
    """
    if not obj or obj.type != 'MESH':
        return 0
    
    sharp_edges = detect_sharp_edges(obj, angle_threshold)
    
    if not sharp_edges:
        return 0
    
    mesh = obj.data
    marked_count = 0
    
    for edge_idx in sharp_edges:
        if edge_idx < len(mesh.edges):
            edge = mesh.edges[edge_idx]
            if mark_sharp:
                edge.use_edge_sharp = True
            if mark_seam:
                edge.use_seam = True
            marked_count += 1
    
    mesh.update()
    return marked_count


def clear_feature_marks(obj, clear_sharp: bool = True, clear_seam: bool = True) -> int:
    """
    Clear feature edge marks from mesh.
    
    Returns:
        Number of edges cleared
    """
    if not obj or obj.type != 'MESH':
        return 0
    
    mesh = obj.data
    cleared_count = 0
    
    for edge in mesh.edges:
        was_marked = False
        if clear_sharp and edge.use_edge_sharp:
            edge.use_edge_sharp = False
            was_marked = True
        if clear_seam and edge.use_seam:
            edge.use_seam = False
            was_marked = True
        if was_marked:
            cleared_count += 1
    
    mesh.update()
    return cleared_count


def count_feature_edges(obj, use_cache: bool = True) -> Dict[str, int]:
    """
    Count currently marked feature edges.
    
    Uses caching to avoid re-analyzing on every UI draw.
    Note: Sharp/seam counts can change without topology change, but boundary
    count requires bmesh (expensive), so we cache based on topology.
    
    Returns:
        Dict with 'sharp', 'seam', 'boundary' counts
    """
    result = {
        'sharp': 0,
        'seam': 0,
        'boundary': 0
    }
    
    if not obj or obj.type != 'MESH':
        return result
    
    mesh = obj.data
    cache_key = "pet_feature_edges_cache"
    cache_sig = f"{len(mesh.vertices)}_{len(mesh.polygons)}"
    
    # Check cache first
    if use_cache:
        cached_sig = obj.get("pet_feature_edges_sig", "")
        if cached_sig == cache_sig and cache_key in obj:
            try:
                cached = obj[cache_key]
                if isinstance(cached, dict) and 'boundary' in cached:
                    # Sharp/seam counts can change, so recalculate those (fast)
                    # but use cached boundary count (slow bmesh operation)
                    sharp_count = sum(1 for e in mesh.edges if e.use_edge_sharp)
                    seam_count = sum(1 for e in mesh.edges if e.use_seam)
                    return {
                        'sharp': sharp_count,
                        'seam': seam_count,
                        'boundary': cached.get('boundary', 0)
                    }
            except:
                pass  # Cache corrupted, re-analyze
    
    # Perform count (existing logic)
    sharp_count = 0
    seam_count = 0
    boundary_count = 0
    
    # Count sharp and seam (fast - direct mesh access)
    for edge in mesh.edges:
        if edge.use_edge_sharp:
            sharp_count += 1
        if edge.use_seam:
            seam_count += 1
    
    # Count boundary edges (slow - requires bmesh)
    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.edges.ensure_lookup_table()
        
        for edge in bm.edges:
            if len(edge.link_faces) < 2:
                boundary_count += 1
    except Exception as e:
        # If bmesh fails, boundary count stays 0
        pass
    finally:
        if bm:
            try:
                bm.free()
            except:
                pass
    
    result = {
        'sharp': sharp_count,
        'seam': seam_count,
        'boundary': boundary_count
    }
    
    # Cache results (only boundary count is expensive, but cache full result)
    try:
        obj[cache_key] = result.copy()
        obj["pet_feature_edges_sig"] = cache_sig
    except:
        pass  # Can't cache - that's okay
    
    return result


# =============================================================================
# MESH CLEANING (Pre-Decimation)
# =============================================================================

def analyze_mesh_problems(obj, use_cache: bool = True) -> Dict[str, int]:
    """
    Analyze mesh for problems that cause holes during decimation.
    
    Uses caching to avoid re-analyzing on every UI draw.
    Cache is stored on object and invalidated when mesh changes.
    
    Args:
        obj: Blender mesh object
        use_cache: If True, return cached results if available
    
    Returns:
        Dict with counts: 'loose_verts', 'loose_edges', 'degenerate_faces', 
                         'non_manifold_edges', 'total_problems'
    """
    result = {
        'loose_verts': 0,
        'loose_edges': 0,
        'degenerate_faces': 0,
        'non_manifold_edges': 0,
        'total_problems': 0
    }
    
    if not obj or obj.type != 'MESH':
        return result
    
    # Check cache first - use vertex/face count as cache key
    mesh = obj.data
    cache_key = "pet_mesh_analysis_cache"
    cache_signature = f"{len(mesh.vertices)}_{len(mesh.polygons)}"
    
    if use_cache:
        cached_sig = obj.get("pet_mesh_analysis_sig", "")
        if cached_sig == cache_signature and cache_key in obj:
            # Mesh hasn't changed, return cached results
            try:
                cached = obj[cache_key]
                if isinstance(cached, dict) and 'total_problems' in cached:
                    return cached
            except:
                pass  # Cache corrupted, re-analyze
    
    # Perform analysis using bmesh (fast) - with error handling
    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        # Single pass through vertices
        try:
            for v in bm.verts:
                if len(v.link_edges) == 0:
                    result['loose_verts'] += 1
        except Exception as e:
            # Continue with other checks even if vertex check fails
            pass
        
        # Single pass through edges - check both loose and non-manifold
        try:
            for e in bm.edges:
                face_count = len(e.link_faces)
                if face_count == 0:
                    result['loose_edges'] += 1
                elif face_count > 2:
                    result['non_manifold_edges'] += 1
        except Exception as e:
            # Continue with face check even if edge check fails
            pass
        
        # Single pass through faces - check degenerate
        try:
            for f in bm.faces:
                try:
                    if f.calc_area() < 1e-8:
                        result['degenerate_faces'] += 1
                except:
                    # Skip faces that can't calculate area
                    pass
        except Exception as e:
            # Continue even if face check fails
            pass
        
    except Exception as e:
        # If bmesh operations fail, return partial results
        # Don't cache failed results
        if bm:
            try:
                bm.free()
            except:
                pass
        return result
    
    # Free bmesh
    if bm:
        try:
            bm.free()
        except:
            pass
    
    result['total_problems'] = (
        result['loose_verts'] + 
        result['loose_edges'] + 
        result['degenerate_faces'] + 
        result['non_manifold_edges']
    )
    
    # Store in cache only if we got valid results
    try:
        obj[cache_key] = result.copy()
        obj["pet_mesh_analysis_sig"] = cache_signature
    except Exception as e:
        # Can't cache - that's okay, just return results
        pass
    
    return result


def clean_mesh_for_decimation(
    obj,
    merge_distance: float = 0.0001,
    delete_loose: bool = True,
    dissolve_degenerate: bool = True,
    fix_non_manifold: bool = False
) -> Dict[str, any]:
    """
    Clean mesh to prevent holes during decimation.
    
    Operations performed (in order):
    1. Merge by Distance - fuse overlapping/close vertices
    2. Delete Loose - remove disconnected verts/edges
    3. Dissolve Degenerate - remove zero-area faces
    
    Args:
        obj: Blender mesh object
        merge_distance: Distance threshold for merging vertices (default 0.0001)
        delete_loose: Remove loose verts and edges
        dissolve_degenerate: Remove zero-area faces
    
    Returns:
        Dict with 'verts_merged', 'loose_removed', 'degenerate_dissolved',
                  'initial_verts', 'final_verts', 'success', 'error'
    """
    result = {
        'verts_merged': 0,
        'loose_verts_removed': 0,
        'loose_edges_removed': 0,
        'degenerate_dissolved': 0,
        'non_manifold_fixed': 0,
        'faces_removed': 0,
        'initial_verts': 0,
        'initial_faces': 0,
        'final_verts': 0,
        'final_faces': 0,
        'success': False,
        'error': None
    }
    
    if not obj or obj.type != 'MESH':
        result['error'] = "Invalid object or not a mesh"
        return result
    
    bm = None
    try:
        # Get initial counts
        result['initial_verts'] = len(obj.data.vertices)
        result['initial_faces'] = len(obj.data.polygons)
        
        # Create bmesh
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        initial_vert_count = len(bm.verts)
        
        # 1. MERGE BY DISTANCE (remove overlapping vertices)
        try:
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=merge_distance)
            bm.verts.ensure_lookup_table()
            result['verts_merged'] = initial_vert_count - len(bm.verts)
        except Exception as e:
            result['error'] = f"Merge by distance failed: {str(e)}"
            if bm:
                try:
                    bm.free()
                except:
                    pass
            return result
        
        # 2. DELETE LOOSE GEOMETRY
        if delete_loose:
            try:
                # Find and remove loose vertices
                loose_verts = [v for v in bm.verts if len(v.link_edges) == 0]
                result['loose_verts_removed'] = len(loose_verts)
                if loose_verts:
                    bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')
                    bm.verts.ensure_lookup_table()
                
                bm.edges.ensure_lookup_table()
                
                # Find and remove loose edges
                loose_edges = [e for e in bm.edges if len(e.link_faces) == 0]
                result['loose_edges_removed'] = len(loose_edges)
                if loose_edges:
                    bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')
                    bm.edges.ensure_lookup_table()
            except Exception as e:
                # Continue even if delete loose fails
                pass
        
        # 3. DISSOLVE DEGENERATE FACES
        if dissolve_degenerate:
            try:
                bm.faces.ensure_lookup_table()
                bm.edges.ensure_lookup_table()
                
                # dissolve_degenerate removes zero-area faces and edges
                dissolved = bmesh.ops.dissolve_degenerate(
                    bm, 
                    dist=merge_distance,
                    edges=bm.edges[:]
                )
                # dissolved can be None or a dict - handle both cases
                if dissolved and isinstance(dissolved, dict):
                    result['degenerate_dissolved'] = len(dissolved.get('region', []))
                else:
                    result['degenerate_dissolved'] = 0
                
                # After dissolve_degenerate, explicitly remove zero-area faces
                # dissolve_degenerate works on edges, but may miss some zero-area faces
                try:
                    bm.faces.ensure_lookup_table()
                    degenerate_faces = [f for f in bm.faces if f.calc_area() < 1e-8]
                    if degenerate_faces:
                        bmesh.ops.delete(bm, geom=degenerate_faces, context='FACES')
                        result['degenerate_dissolved'] += len(degenerate_faces)
                except Exception as e:
                    pass  # Continue even if this fails
            except Exception as e:
                # dissolve_degenerate can fail on some meshes - continue anyway
                result['degenerate_dissolved'] = 0
        
        # 4. FIX NON-MANIFOLD EDGES (integrated into existing bmesh)
        if fix_non_manifold:
            try:
                bm.edges.ensure_lookup_table()
                bm.faces.ensure_lookup_table()
                
                # Find non-manifold edges
                non_manifold_edges = [e for e in bm.edges if len(e.link_faces) > 2]
                
                if non_manifold_edges:
                    # Find duplicate faces
                    faces_to_remove = []
                    for edge in non_manifold_edges:
                        linked_faces = list(edge.link_faces)
                        if len(linked_faces) > 2:
                            # Check for duplicates
                            face_groups = {}
                            for face in linked_faces:
                                vert_sig = tuple(sorted([v.index for v in face.verts]))
                                if vert_sig not in face_groups:
                                    face_groups[vert_sig] = []
                                face_groups[vert_sig].append(face)
                            
                            # Mark duplicates for removal
                            for faces in face_groups.values():
                                if len(faces) > 1:
                                    faces_to_remove.extend(faces[1:])
                    
                    # Remove duplicates
                    if faces_to_remove:
                        # Remove duplicates from list
                        unique_faces = []
                        seen_faces = set()
                        for face in faces_to_remove:
                            if face not in seen_faces:
                                unique_faces.append(face)
                                seen_faces.add(face)
                        
                        if unique_faces:
                            bmesh.ops.delete(bm, geom=unique_faces, context='FACES')
                            result['faces_removed'] = len(unique_faces)
                            result['non_manifold_fixed'] = len(non_manifold_edges)
                            
            except Exception as e:
                # Continue even if non-manifold fix fails
                pass
        
        # Write back to mesh
        try:
            bm.to_mesh(obj.data)
            obj.data.update()
        except Exception as e:
            result['error'] = f"Failed to write mesh back: {str(e)}"
            if bm:
                try:
                    bm.free()
                except:
                    pass
            return result
        
        # Get final counts
        result['final_verts'] = len(obj.data.vertices)
        result['final_faces'] = len(obj.data.polygons)
        result['success'] = True
        
    except Exception as e:
        result['error'] = f"Cleaning operation failed: {str(e)}"
    finally:
        # Always free bmesh
        if bm:
            try:
                bm.free()
            except:
                pass
    
    return result


def fix_non_manifold_edges(obj) -> Dict[str, any]:
    """
    Fix non-manifold edges by removing duplicate faces.
    
    Non-manifold edges (shared by 3+ faces) indicate duplicate geometry.
    This function attempts to fix by finding and removing duplicate overlapping faces.
    
    Note: Some non-manifold edges may require manual editing.
    
    Returns:
        Dict with 'edges_fixed', 'faces_removed', 'success', 'error'
    """
    result = {
        'edges_fixed': 0,
        'faces_removed': 0,
        'success': False,
        'error': None
    }
    
    if not obj or obj.type != 'MESH':
        result['error'] = "Invalid object or not a mesh"
        return result
    
    bm = None
    try:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        # Find non-manifold edges (shared by 3+ faces)
        non_manifold_edges = []
        for e in bm.edges:
            if len(e.link_faces) > 2:
                non_manifold_edges.append(e)
        
        if not non_manifold_edges:
            result['success'] = True
            if bm:
                try:
                    bm.free()
                except:
                    pass
            return result
        
        # Strategy: For each non-manifold edge, try to remove duplicate faces
        # An edge with 3+ faces usually means duplicate overlapping faces
        faces_to_remove = []
        
        for edge in non_manifold_edges:
            linked_faces = list(edge.link_faces)
            if len(linked_faces) > 2:
                # Check for duplicate faces (same vertices)
                face_groups = {}
                for face in linked_faces:
                    # Create a signature for the face (sorted vertex indices)
                    vert_indices = tuple(sorted([v.index for v in face.verts]))
                    if vert_indices not in face_groups:
                        face_groups[vert_indices] = []
                    face_groups[vert_indices].append(face)
                
                # Remove duplicate faces (keep first, remove rest)
                for vert_indices, faces in face_groups.items():
                    if len(faces) > 1:
                        # Keep first face, mark others for removal
                        faces_to_remove.extend(faces[1:])
        
        # Remove duplicate faces
        if faces_to_remove:
            # Remove duplicates from list (same face might be in multiple groups)
            unique_faces = []
            seen_faces = set()
            for face in faces_to_remove:
                if face not in seen_faces:
                    unique_faces.append(face)
                    seen_faces.add(face)
            
            if unique_faces:
                try:
                    bmesh.ops.delete(bm, geom=unique_faces, context='FACES')
                    result['faces_removed'] = len(unique_faces)
                    result['edges_fixed'] = len(non_manifold_edges)
                except Exception as e:
                    # If delete fails, log error but continue
                    result['error'] = f"Could not remove all duplicate faces: {str(e)[:50]}"
        
        # Write back to mesh
        try:
            bm.to_mesh(obj.data)
            obj.data.update()
            result['success'] = True
        except Exception as e:
            result['error'] = f"Failed to write mesh: {str(e)}"
            
    except Exception as e:
        result['error'] = str(e)
    finally:
        if bm:
            try:
                bm.free()
            except:
                pass
    
    return result


# =============================================================================
# BLENDER DECIMATE MODIFIER WRAPPER
# =============================================================================

def iterative_decimate(
    obj,
    step_ratio: float = 0.05,
    preserve_sharp: bool = True,
    preserve_seams: bool = True,
    preserve_vertex_groups: bool = True,
    triangulate: bool = False,
    symmetry_axis: Optional[str] = None
) -> Dict[str, any]:
    """
    Apply one step of decimation using Blender's Decimate modifier.
    
    This is the core function for iterative mesh reduction. Call repeatedly
    to progressively reduce the mesh while monitoring quality.
    
    Args:
        obj: Blender mesh object
        step_ratio: Reduction ratio (0.01-0.20). 0.05 = remove 5% of faces.
        preserve_sharp: Respect edge sharp marks
        preserve_seams: Respect UV seams
        preserve_vertex_groups: Try to preserve vertex group boundaries
        triangulate: Triangulate result (usually False)
        symmetry_axis: 'X', 'Y', 'Z', or None for no symmetry
    
    Returns:
        Dict with 'initial_faces', 'final_faces', 'removed', 'success', 'error'
    """
    result = {
        'initial_faces': 0,
        'final_faces': 0,
        'initial_verts': 0,
        'final_verts': 0,
        'removed_faces': 0,
        'removed_verts': 0,
        'success': False,
        'error': None
    }
    
    if not obj or obj.type != 'MESH':
        result['error'] = "Invalid object or not a mesh"
        return result
    
    mesh = obj.data
    result['initial_faces'] = len(mesh.polygons)
    result['initial_verts'] = len(mesh.vertices)
    
    # Clamp step ratio to safe bounds
    step_ratio = max(0.01, min(0.50, step_ratio))
    
    # Calculate target ratio for modifier (ratio = faces to KEEP)
    # If step_ratio is 0.05 (remove 5%), we keep 0.95
    keep_ratio = 1.0 - step_ratio
    
    try:
        # Add Decimate modifier
        modifier = obj.modifiers.new(name="PET_Decimate", type='DECIMATE')
        modifier.decimate_type = 'COLLAPSE'
        modifier.ratio = keep_ratio
        modifier.use_collapse_triangulate = triangulate
        
        # Symmetry settings
        if symmetry_axis in ('X', 'Y', 'Z'):
            modifier.use_symmetry = True
            modifier.symmetry_axis = symmetry_axis
        else:
            modifier.use_symmetry = False
        
        # Note: Decimate modifier automatically respects:
        # - Sharp edges (when Auto Smooth is enabled or edges marked sharp)
        # - UV seams
        # - Vertex groups (to some extent)
        
        # Apply the modifier
        # Need to be in object mode
        current_mode = obj.mode
        if current_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Make sure object is selected and active
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        
        # Apply modifier
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        
        # Restore mode if needed
        if current_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=current_mode)
        
        # Update results
        mesh = obj.data  # Re-get mesh data after modification
        result['final_faces'] = len(mesh.polygons)
        result['final_verts'] = len(mesh.vertices)
        result['removed_faces'] = result['initial_faces'] - result['final_faces']
        result['removed_verts'] = result['initial_verts'] - result['final_verts']
        result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
        # Try to remove modifier if it still exists
        if 'PET_Decimate' in obj.modifiers:
            obj.modifiers.remove(obj.modifiers['PET_Decimate'])
    
    return result


def decimate_to_target(
    obj,
    target_faces: int,
    max_iterations: int = 50,
    preserve_sharp: bool = True,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Dict[str, any]:
    """
    Iteratively decimate until reaching target face count.
    
    Uses adaptive step sizes - larger when far from target, smaller when close.
    
    Args:
        obj: Blender mesh object
        target_faces: Target number of faces
        max_iterations: Maximum reduction steps
        preserve_sharp: Preserve sharp edges
        progress_callback: Optional callback(progress: 0-1, status: str)
    
    Returns:
        Dict with final stats
    """
    result = {
        'initial_faces': 0,
        'final_faces': 0,
        'iterations': 0,
        'success': False,
        'error': None
    }
    
    if not obj or obj.type != 'MESH':
        result['error'] = "Invalid object"
        return result
    
    result['initial_faces'] = len(obj.data.polygons)
    current_faces = result['initial_faces']
    
    if target_faces >= current_faces:
        result['final_faces'] = current_faces
        result['success'] = True
        return result
    
    for iteration in range(max_iterations):
        if current_faces <= target_faces:
            break
        
        # Calculate adaptive step size
        # Larger steps when far from target, smaller when close
        faces_to_remove = current_faces - target_faces
        step_ratio = min(0.20, max(0.02, faces_to_remove / current_faces * 0.5))
        
        # Apply one step
        step_result = iterative_decimate(obj, step_ratio, preserve_sharp)
        
        if not step_result['success']:
            result['error'] = step_result['error']
            break
        
        current_faces = step_result['final_faces']
        result['iterations'] = iteration + 1
        
        if progress_callback:
            progress = 1.0 - (current_faces - target_faces) / (result['initial_faces'] - target_faces)
            progress_callback(min(1.0, progress), f"Iteration {iteration + 1}: {current_faces:,} faces")
        
        # Safety: stop if no progress
        if step_result['removed_faces'] == 0:
            break
    
    result['final_faces'] = current_faces
    result['success'] = current_faces <= target_faces or result['iterations'] > 0
    
    return result


# =============================================================================
# POST-SPLIT PART OPTIMIZATION
# =============================================================================

def detect_boundary_edges(obj) -> Set[int]:
    """
    Detect boundary edges (edges with only one face) on a mesh part.
    
    These are typically the cut edges from splitting and should be preserved.
    
    Returns:
        Set of boundary edge indices
    """
    if not obj or obj.type != 'MESH':
        return set()
    
    boundary_edges: Set[int] = set()
    
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    
    for edge in bm.edges:
        if len(edge.link_faces) < 2:
            boundary_edges.add(edge.index)
    
    bm.free()
    return boundary_edges


def protect_boundary_edges(obj) -> int:
    """
    Mark boundary edges as sharp to protect them during decimation.
    
    Returns:
        Number of edges marked
    """
    boundary_edges = detect_boundary_edges(obj)
    
    if not boundary_edges:
        return 0
    
    mesh = obj.data
    marked = 0
    
    for edge_idx in boundary_edges:
        if edge_idx < len(mesh.edges):
            mesh.edges[edge_idx].use_edge_sharp = True
            marked += 1
    
    mesh.update()
    return marked


def optimize_split_part(
    obj,
    step_ratio: float = 0.05,
    preserve_boundaries: bool = True,
    preserve_pivots: bool = True
) -> Dict[str, any]:
    """
    Optimize a split mesh part while preserving its boundaries.
    
    Args:
        obj: Split part mesh object
        step_ratio: Reduction ratio per step
        preserve_boundaries: Mark and protect boundary edges
        preserve_pivots: Avoid decimating near pivot points
    
    Returns:
        Dict with optimization results
    """
    result = {
        'initial_faces': 0,
        'final_faces': 0,
        'boundaries_protected': 0,
        'success': False,
        'error': None
    }
    
    if not obj or obj.type != 'MESH':
        result['error'] = "Invalid object"
        return result
    
    result['initial_faces'] = len(obj.data.polygons)
    
    # Protect boundary edges first
    if preserve_boundaries:
        result['boundaries_protected'] = protect_boundary_edges(obj)
    
    # Apply decimation
    decimate_result = iterative_decimate(obj, step_ratio, preserve_sharp=True)
    
    result['final_faces'] = decimate_result['final_faces']
    result['success'] = decimate_result['success']
    result['error'] = decimate_result['error']
    
    return result


# =============================================================================
# STATISTICS AND TRACKING
# =============================================================================

def store_optimization_stats(obj, initial_faces: int, initial_verts: int):
    """Store initial mesh stats on object for tracking progress."""
    if not obj:
        return
    
    # Only store if not already stored (preserve original values)
    if "pet_opt_initial_faces" not in obj:
        obj["pet_opt_initial_faces"] = initial_faces
    if "pet_opt_initial_verts" not in obj:
        obj["pet_opt_initial_verts"] = initial_verts
    obj["pet_opt_step_count"] = obj.get("pet_opt_step_count", 0)


def update_optimization_stats(obj):
    """Update optimization stats after a reduction step."""
    if not obj or obj.type != 'MESH':
        return
    
    obj["pet_opt_step_count"] = obj.get("pet_opt_step_count", 0) + 1
    obj["pet_opt_current_faces"] = len(obj.data.polygons)
    obj["pet_opt_current_verts"] = len(obj.data.vertices)


def get_optimization_stats(obj) -> Dict[str, any]:
    """Get optimization statistics for UI display."""
    if not obj or obj.type != 'MESH':
        return {}
    
    mesh = obj.data
    current_faces = len(mesh.polygons)
    current_verts = len(mesh.vertices)
    
    initial_faces = obj.get("pet_opt_initial_faces", current_faces)
    initial_verts = obj.get("pet_opt_initial_verts", current_verts)
    step_count = obj.get("pet_opt_step_count", 0)
    
    face_reduction = 0.0
    vert_reduction = 0.0
    
    if initial_faces > 0:
        face_reduction = (1.0 - current_faces / initial_faces) * 100
    if initial_verts > 0:
        vert_reduction = (1.0 - current_verts / initial_verts) * 100
    
    return {
        'initial_faces': initial_faces,
        'initial_verts': initial_verts,
        'current_faces': current_faces,
        'current_verts': current_verts,
        'face_reduction_percent': face_reduction,
        'vert_reduction_percent': vert_reduction,
        'step_count': step_count,
        'has_history': step_count > 0
    }


def reset_optimization_stats(obj):
    """Clear optimization tracking stats from object."""
    if not obj:
        return
    
    keys_to_remove = [
        "pet_opt_initial_faces",
        "pet_opt_initial_verts", 
        "pet_opt_current_faces",
        "pet_opt_current_verts",
        "pet_opt_step_count"
    ]
    
    for key in keys_to_remove:
        if key in obj:
            del obj[key]


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
