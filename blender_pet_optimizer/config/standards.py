"""
Standard configuration for parts
Standard scales, orientations, attachment points
"""

# Standard attachment points
STANDARD_ATTACHMENTS = {
    "neck": "NeckAttachment",
    "hip": "HipAttachment",
    "root": "RootAttachment",
    # More attachment points will be added
}

# Standard orientations
STANDARD_FORWARD = (0, 1, 0)  # +Y axis
STANDARD_UP = (0, 0, 1)  # +Z axis

# Bone naming conventions
BONE_ROOT = "Root"
BONE_NAMING_PREFIX = ""

# Standard scales
REFERENCE_SCALE = 1.0  # Body part = 1.0 scale
