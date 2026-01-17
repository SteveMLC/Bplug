"""
Addon preferences for Pet Model Optimizer
User settings and configuration
"""

import bpy
from bpy.types import AddonPreferences
from bpy.props import FloatProperty, IntProperty


class PET_AddonPreferences(AddonPreferences):
    """Preferences for Pet Model Optimizer addon"""
    bl_idname = __name__.split('.')[0]  # Get the addon name
    
    # Preference properties will be defined here
    # default_grid_size: FloatProperty(...)
    # default_reduction: FloatProperty(...)
    
    def draw(self, context):
        layout = self.layout
        # Preferences UI will be implemented here
        layout.label(text="Preferences not yet implemented")


classes = [
    PET_AddonPreferences,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
