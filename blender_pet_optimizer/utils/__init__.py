"""
Utility modules for Pet Model Optimizer
Contains algorithms, helpers, and templates
"""

from . import algorithms
from . import bmesh_helpers

# Optional imports that may not always be present
try:
    from . import segmentation_templates
except ImportError:
    segmentation_templates = None

try:
    from . import segmentation_refinement
except ImportError:
    segmentation_refinement = None

try:
    from . import spatial_selection
except ImportError:
    spatial_selection = None

try:
    from . import roblox_export
except ImportError:
    roblox_export = None

__all__ = [
    "algorithms",
    "bmesh_helpers",
    "segmentation_templates",
    "segmentation_refinement",
    "spatial_selection",
    "roblox_export",
]
