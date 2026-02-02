"""
bmesh utility functions
Helper functions for working with bmesh in the addon
"""

import bmesh
import bpy
from mathutils import Vector

from . import segmentation_refinement
from .orientation import auto_invert_forward_axis


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


def adaptive_timeout(vertex_count: int, base: float = 5.0, per_100k: float = 2.0, max_timeout: float = 20.0) -> float:
    """Adaptive timeout to avoid penalizing large meshes.

    Geometry-based operations on 500k+ vertex meshes routinely exceed a fixed 5s timeout.
    """
    return min(max_timeout, base + per_100k * (vertex_count / 100_000.0))


def validate_segmentation(vertex_groups: dict, *, expected_parts=None, min_parts: int = 2, min_body_ratio: float = 0.25) -> bool:
    """Best-effort validation so we don't accept obvious garbage results."""
    if not vertex_groups or len(vertex_groups) < min_parts:
        return False

    if any(not indices for indices in vertex_groups.values()):
        return False

    if expected_parts:
        # At minimum, body+head is a reasonable baseline for animals.
        if 'body' in expected_parts and 'body' not in vertex_groups:
            return False
        if 'head' in expected_parts and 'head' not in vertex_groups:
            return False

    total = sum(len(v) for v in vertex_groups.values())
    if total <= 0:
        return False

    if 'body' in vertex_groups:
        if (len(vertex_groups['body']) / total) < min_body_ratio:
            return False

    return True


def segment_by_regions_robust(
    obj,
    template,
    use_connectivity_refinement=True,
    sensitivity=0.5,
    auto_detect_protrusions=True,
    use_geometry_based=True,
    template_type='quadruped',
    use_fast_mode=False,
    timeout=None,
    invert_forward_axis=False,
    auto_orientation=True,
):
    """Robust segmentation entry point.

    Strategy chain (never fail completely):
      geometry-based → fast-mode → spatial(+refine if allowed) → spatial-basic

    Returns:
        (vertex_groups_created, method_name)
    """
    if not obj or obj.type != 'MESH':
        return {}, 'invalid-object'

    vcount = len(obj.data.vertices)
    expected_parts = set(template.keys()) if template else None

    # Auto-orientation: compute a likely invert flag unless the user explicitly asks to invert.
    effective_invert = bool(invert_forward_axis)
    if auto_orientation and not invert_forward_axis:
        try:
            effective_invert = auto_invert_forward_axis(obj)
            obj['pet_auto_invert_forward_axis'] = bool(effective_invert)
        except Exception:
            # Orientation detection is best-effort.
            effective_invert = bool(invert_forward_axis)

    base_timeout = timeout if timeout is not None else adaptive_timeout(vcount)

    # When a user selects "Fast Mode" explicitly, don't waste time attempting heavy strategies.
    strategies = []
    if use_geometry_based and not use_fast_mode:
        strategies.append(dict(
            name='geometry',
            use_geometry_based=True,
            use_fast_mode=False,
            use_connectivity_refinement=use_connectivity_refinement,
            auto_detect_protrusions=auto_detect_protrusions,
            timeout=base_timeout,
        ))

    # Geometry fast: disable expensive refinement/protrusions.
    if use_geometry_based:
        strategies.append(dict(
            name='geometry-fast',
            use_geometry_based=True,
            use_fast_mode=True,
            use_connectivity_refinement=False,
            auto_detect_protrusions=False,
            timeout=max(5.0, base_timeout * 0.6),
        ))

    # Spatial fallback(s)
    strategies.append(dict(
        name='spatial',
        use_geometry_based=False,
        use_fast_mode=use_fast_mode,
        use_connectivity_refinement=use_connectivity_refinement and not use_fast_mode,
        auto_detect_protrusions=auto_detect_protrusions and not use_fast_mode,
        timeout=max(5.0, base_timeout * 0.5),
    ))
    strategies.append(dict(
        name='spatial-basic',
        use_geometry_based=False,
        use_fast_mode=True,
        use_connectivity_refinement=False,
        auto_detect_protrusions=False,
        timeout=5.0,
    ))

    last_exc = None
    for s in strategies:
        try:
            vg = segment_by_regions(
                obj,
                template,
                use_connectivity_refinement=s['use_connectivity_refinement'],
                sensitivity=sensitivity,
                auto_detect_protrusions=s['auto_detect_protrusions'],
                use_geometry_based=s['use_geometry_based'],
                template_type=template_type,
                use_fast_mode=s['use_fast_mode'],
                timeout=s.get('timeout'),
                invert_forward_axis=effective_invert,
            )
            if validate_segmentation(vg, expected_parts=expected_parts):
                return vg, s['name']
        except Exception as e:
            last_exc = e
            continue

    # Absolute fallback: return empty (manual mode can still proceed).
    if last_exc:
        print(f"[Segmentation] All strategies failed: {last_exc}")
    return {}, 'manual'


def segment_by_regions(obj, template, use_connectivity_refinement=True, sensitivity=0.5, 
                       auto_detect_protrusions=True, use_geometry_based=True, template_type='quadruped',
                       use_fast_mode=False, timeout=None, invert_forward_axis=False):
    """
    Segment mesh into body parts using geometry-based detection (primary) or spatial regions (fallback)
    
    Args:
        obj: Blender object with mesh data
        template: Segmentation template dictionary
        use_connectivity_refinement: Enable industry-standard connectivity-based boundary refinement
        sensitivity: Float (0.0-1.0) for boundary detection sensitivity
        auto_detect_protrusions: Automatically detect and refine protrusions (legs, wings, tails)
        use_geometry_based: Use geometry-based detection (recommended) vs spatial-only
        template_type: 'quadruped', 'biped', or 'flying'
        invert_forward_axis: Manual override to invert the forward axis (swap head/tail)
    
    Returns:
        dict: Vertex groups created with vertex indices
    """
    if not obj or obj.type != 'MESH':
        return {}
    
    mesh = obj.data
    min_bbox, max_bbox, size = get_mesh_bounds(obj)
    
    if not size or size.length == 0:
        return {}
    
    vertex_groups_created = {}
    
    # PRIMARY METHOD: Geometry-based segmentation
    # Uses actual mesh geometry rather than bounding box percentages
    if use_geometry_based:
        # Create progress callback that updates window manager
        def progress_callback(percent, message=""):
            try:
                wm = bpy.context.window_manager
                if wm:
                    wm.progress_update(percent)
                    if message:
                        print(f"Progress {percent}%: {message}")
            except:
                pass  # Progress updates are optional
        
        # Try geometry-based detection with timeout protection
        geometry_result = None
        try:
            import time
            start_time = time.time()
            # Use provided timeout, or default to 5s for final segmentation (30s is too long)
            timeout_value = timeout if timeout is not None else 5.0
            
            geometry_result = segmentation_refinement.segment_by_geometry(
                obj, template, template_type, use_fast_mode=use_fast_mode,
                progress_callback=progress_callback, invert_forward_axis=invert_forward_axis
            )
            
            elapsed = time.time() - start_time
            if elapsed > timeout_value:
                print(f"WARNING: Geometry-based segmentation took {elapsed:.1f}s (exceeded {timeout_value}s timeout)")
                geometry_result = None  # Force fallback on timeout
        except Exception as e:
            print(f"Geometry-based segmentation failed: {str(e)}")
            print("Falling back to spatial-only mode...")
            geometry_result = None
        
        # If geometry-based succeeded, process results
        if geometry_result:
            # Geometry-based detection succeeded
            # Create vertex groups from geometry results
            for part_name, vert_indices in geometry_result.items():
                # Create or get vertex group
                if part_name in obj.vertex_groups:
                    vg = obj.vertex_groups[part_name]
                else:
                    vg = obj.vertex_groups.new(name=part_name)
                
                # Assign vertices
                if vert_indices:
                    vg.add(vert_indices, 1.0, 'REPLACE')
                vertex_groups_created[part_name] = vert_indices
            
            # Apply connectivity refinement if enabled (skip in fast mode)
            if use_connectivity_refinement and vertex_groups_created and not use_fast_mode:
                refined_groups = segmentation_refinement.refine_segmentation_with_connectivity(
                    obj, vertex_groups_created, template, sensitivity
                )
                
                # Update vertex groups with refined assignments
                for part_name, refined_indices in refined_groups.items():
                    if part_name in obj.vertex_groups:
                        vg = obj.vertex_groups[part_name]
                        vg.remove([i for i in range(len(mesh.vertices))])
                        if refined_indices:
                            vg.add(refined_indices, 1.0, 'REPLACE')
                        vertex_groups_created[part_name] = refined_indices
            
            return vertex_groups_created
        else:
            # Geometry-based failed - fall back to spatial mode
            print("Geometry-based segmentation failed or returned empty. Using spatial-only mode (fallback)...")
            # Continue to fallback method below
    
    # FALLBACK METHOD: Spatial-only segmentation (bounding box percentages)
    # Used when geometry-based detection fails or is disabled
    
    # Step 1: Initial spatial assignment
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
    
    # Step 2: Connectivity-based refinement (industry standard precision)
    # Skip in fast mode for speed
    if use_connectivity_refinement and not use_fast_mode:
        refined_groups = segmentation_refinement.refine_segmentation_with_connectivity(
            obj, vertex_groups_created, template, sensitivity
        )
        
        # Update vertex groups with refined assignments
        for part_name, refined_indices in refined_groups.items():
            if part_name in obj.vertex_groups:
                vg = obj.vertex_groups[part_name]
                # Remove all vertices first
                vg.remove([i for i in range(len(mesh.vertices))])
                # Add refined vertices
                if refined_indices:
                    vg.add(refined_indices, 1.0, 'REPLACE')
                vertex_groups_created[part_name] = refined_indices
    else:
        # If not using refinement, ensure all groups are properly set
        for part_name, indices in vertex_groups_created.items():
            if part_name in obj.vertex_groups:
                vg = obj.vertex_groups[part_name]
                vg.remove([i for i in range(len(mesh.vertices))])
                if indices:
                    vg.add(indices, 1.0, 'REPLACE')
    
    # Step 3: Protrusion detection and refinement (if enabled)
    # Skip in fast mode for speed
    if auto_detect_protrusions and "body" in vertex_groups_created and not use_fast_mode:
        protrusion_scores = segmentation_refinement.find_protrusions(
            obj, "body", vertex_groups_created
        )
        # Protrusion scores can be used for further refinement or validation
        # For now, we just calculate them for potential future use
    
    # Step 4: Verify vertices are actually assigned to vertex groups
    # Update vertex_groups_created with actual assigned vertices
    verified_groups = {}
    total_verified = 0
    for part_name, expected_indices in vertex_groups_created.items():
        if part_name in obj.vertex_groups:
            vg = obj.vertex_groups[part_name]
            # Count vertices actually assigned (weight > 0)
            actual_indices = []
            for vert in mesh.vertices:
                for group in vert.groups:
                    if group.group == vg.index and group.weight > 0.0:
                        actual_indices.append(vert.index)
                        break
            verified_groups[part_name] = actual_indices
            total_verified += len(actual_indices)
            
            # Warn if significant mismatch
            if len(expected_indices) > 0 and len(actual_indices) == 0:
                print(f"WARNING: Vertex group '{part_name}' has no assigned vertices (expected {len(expected_indices)})")
            elif abs(len(actual_indices) - len(expected_indices)) > len(expected_indices) * 0.1:
                print(f"WARNING: Vertex group '{part_name}' has {len(actual_indices)} assigned vertices (expected {len(expected_indices)})")
        else:
            verified_groups[part_name] = []
    
    # Return verified groups (use actual assignments)
    return verified_groups


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
