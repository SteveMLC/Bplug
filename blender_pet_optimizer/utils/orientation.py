"""Orientation detection utilities.

Goal: avoid reliance on manual `invert_forward_axis` by automatically determining the
most likely forward direction for a mesh.

This module is intentionally lightweight and dependency-tolerant: it will use numpy
(if available in Blender's Python) for PCA; otherwise it falls back to a bbox-based
heuristic.
"""

from __future__ import annotations

import random
from mathutils import Vector


def _sample_world_points(obj, max_points: int = 15000):
    mesh = obj.data
    n = len(mesh.vertices)
    if n == 0:
        return []

    if n <= max_points:
        idxs = range(n)
    else:
        idxs = random.sample(range(n), max_points)

    mw = obj.matrix_world
    return [mw @ mesh.vertices[i].co for i in idxs]


def _pca_forward_axis(points):
    """Return an estimated principal axis as a Vector in world-space."""
    # Try numpy first (fast + accurate)
    try:
        import numpy as np  # type: ignore

        P = np.array([[p.x, p.y, p.z] for p in points], dtype=np.float32)
        c = P.mean(axis=0)
        X = P - c
        C = (X.T @ X) / max(1, (len(points) - 1))
        w, v = np.linalg.eigh(C)
        order = np.argsort(w)[::-1]
        axis = v[:, order[0]]
        a = Vector((float(axis[0]), float(axis[1]), float(axis[2])))
        if a.length > 1e-12:
            a.normalize()
        return a
    except Exception:
        pass

    # Fallback: use world-space bbox longest dimension direction
    minp = Vector((1e18, 1e18, 1e18))
    maxp = Vector((-1e18, -1e18, -1e18))
    for p in points:
        minp.x = min(minp.x, p.x)
        minp.y = min(minp.y, p.y)
        minp.z = min(minp.z, p.z)
        maxp.x = max(maxp.x, p.x)
        maxp.y = max(maxp.y, p.y)
        maxp.z = max(maxp.z, p.z)

    size = maxp - minp
    # Assume longest dimension is body length.
    if size.x >= size.y and size.x >= size.z:
        return Vector((1, 0, 0))
    if size.y >= size.x and size.y >= size.z:
        return Vector((0, 1, 0))
    return Vector((0, 0, 1))


def auto_invert_forward_axis(obj, *, max_points: int = 15000, end_slice_ratio: float = 0.07) -> bool:
    """Return True if the mesh's likely "forward" points toward -Y (so we should invert).

    Heuristic:
    - Estimate forward axis via PCA (principal component) or bbox.
    - Determine which end of that axis is the "head" via vertex density in an extreme slice.
    - Map head → +Y for the addon's canonical assumptions.

    This does not rotate the mesh; it only chooses the forward *sign*.
    """
    pts = _sample_world_points(obj, max_points=max_points)
    if len(pts) < 20:
        return False

    fwd = _pca_forward_axis(pts)

    # Project points onto the forward axis.
    dots = [p.dot(fwd) for p in pts]
    min_d = min(dots)
    max_d = max(dots)
    span = max_d - min_d
    if span <= 1e-9:
        return False

    # Count points near each extreme; head is assumed to be the denser end.
    eps = span * end_slice_ratio
    pos_count = 0
    neg_count = 0
    for d in dots:
        if d >= max_d - eps:
            pos_count += 1
        if d <= min_d + eps:
            neg_count += 1

    # Decide which extreme is head and see whether that aligns with +Y.
    head_dir = fwd if pos_count >= neg_count else -fwd

    # If head direction points toward negative world Y, invert.
    return head_dir.dot(Vector((0, 1, 0))) < 0.0
