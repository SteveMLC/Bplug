"""
Blender Pet Model Optimizer
A Blender addon for mesh optimization, segmentation, and rigging of organic animal models.
"""

bl_info = {
    "name": "Pet Model Optimizer",
    "author": "Your Name",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > N-Panel > Pet Model Optimizer",
    "description": "Mesh optimization, segmentation, and rigging tools for organic animal models",
    "category": "Mesh",
}

# Import operator modules
from . import operators
from . import ui

# All classes will be registered by their respective modules
modules_to_register = [
    operators.mesh_optimizer,
    operators.segmentation,
    operators.mesh_splitter,
    operators.rigging,
    operators.standardization,
    operators.export,
    ui.panels,
    ui.preferences,
]


def register():
    """Register all addon classes"""
    for module in modules_to_register:
        if hasattr(module, 'register'):
            module.register()


def unregister():
    """Unregister all addon classes"""
    for module in reversed(modules_to_register):
        if hasattr(module, 'unregister'):
            module.unregister()


if __name__ == "__main__":
    register()
