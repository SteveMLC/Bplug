"""
Animal preset templates for different body proportions
Each preset defines typical body part ratios and positions for auto-segmentation
"""

ANIMAL_PRESETS = {
    'dog': {
        'name': 'Dog / Wolf',
        'description': 'Four-legged canine with long snout',
        'symmetry_axis': 'X',
        'body_proportions': {
            'head_ratio': 0.15,
            'body_ratio': 0.50,
            'leg_ratio': 0.30,
            'tail_ratio': 0.05,
        },
        'segment_hints': {
            'head': {
                'position': 'front_top',
                'z_min': 0.65,
                'z_max': 1.0,
                'y_min': 0.6,
                'y_max': 1.0,
                'expected_volume_ratio': 0.10,
            },
            'body': {
                'position': 'center',
                'z_min': 0.3,
                'z_max': 0.85,
                'y_min': 0.15,
                'y_max': 0.85,
                'expected_volume_ratio': 0.45,
            },
            'leg_front_l': {
                'position': 'front_bottom_left',
                'z_min': 0.0,
                'z_max': 0.5,
                'y_min': 0.5,
                'y_max': 0.8,
                'x_side': 'negative',
                'expected_volume_ratio': 0.08,
            },
            'leg_front_r': {
                'position': 'front_bottom_right',
                'z_min': 0.0,
                'z_max': 0.5,
                'y_min': 0.5,
                'y_max': 0.8,
                'x_side': 'positive',
                'expected_volume_ratio': 0.08,
            },
            'leg_back_l': {
                'position': 'back_bottom_left',
                'z_min': 0.0,
                'z_max': 0.5,
                'y_min': 0.1,
                'y_max': 0.4,
                'x_side': 'negative',
                'expected_volume_ratio': 0.08,
            },
            'leg_back_r': {
                'position': 'back_bottom_right',
                'z_min': 0.0,
                'z_max': 0.5,
                'y_min': 0.1,
                'y_max': 0.4,
                'x_side': 'positive',
                'expected_volume_ratio': 0.08,
            },
            'tail': {
                'position': 'back',
                'z_min': 0.4,
                'z_max': 0.8,
                'y_min': 0.0,
                'y_max': 0.2,
                'expected_volume_ratio': 0.03,
            },
        },
        'joint_offsets': {
            'neck': {'from_body': (0, 0.4, 0.15), 'from_head': (0, -0.1, -0.05)},
            'front_legs': {'from_body': (0.12, 0.35, -0.1)},
            'back_legs': {'from_body': (0.12, -0.35, -0.1)},
            'tail': {'from_body': (0, -0.45, 0.05)},
        },
    },
    
    'cat': {
        'name': 'Cat',
        'description': 'Four-legged feline with shorter snout',
        'symmetry_axis': 'X',
        'body_proportions': {
            'head_ratio': 0.18,
            'body_ratio': 0.48,
            'leg_ratio': 0.28,
            'tail_ratio': 0.06,
        },
        'segment_hints': {
            'head': {
                'position': 'front_top',
                'z_min': 0.60,
                'z_max': 1.0,
                'y_min': 0.65,
                'y_max': 1.0,
                'expected_volume_ratio': 0.12,
            },
            'body': {
                'position': 'center',
                'z_min': 0.25,
                'z_max': 0.80,
                'y_min': 0.20,
                'y_max': 0.80,
                'expected_volume_ratio': 0.42,
            },
            'leg_front_l': {
                'position': 'front_bottom_left',
                'z_min': 0.0,
                'z_max': 0.45,
                'y_min': 0.55,
                'y_max': 0.80,
                'x_side': 'negative',
                'expected_volume_ratio': 0.07,
            },
            'leg_front_r': {
                'position': 'front_bottom_right',
                'z_min': 0.0,
                'z_max': 0.45,
                'y_min': 0.55,
                'y_max': 0.80,
                'x_side': 'positive',
                'expected_volume_ratio': 0.07,
            },
            'leg_back_l': {
                'position': 'back_bottom_left',
                'z_min': 0.0,
                'z_max': 0.5,
                'y_min': 0.15,
                'y_max': 0.45,
                'x_side': 'negative',
                'expected_volume_ratio': 0.08,
            },
            'leg_back_r': {
                'position': 'back_bottom_right',
                'z_min': 0.0,
                'z_max': 0.5,
                'y_min': 0.15,
                'y_max': 0.45,
                'x_side': 'positive',
                'expected_volume_ratio': 0.08,
            },
            'tail': {
                'position': 'back',
                'z_min': 0.3,
                'z_max': 0.7,
                'y_min': 0.0,
                'y_max': 0.25,
                'expected_volume_ratio': 0.04,
            },
        },
        'joint_offsets': {
            'neck': {'from_body': (0, 0.35, 0.12), 'from_head': (0, -0.08, -0.04)},
            'front_legs': {'from_body': (0.10, 0.30, -0.08)},
            'back_legs': {'from_body': (0.10, -0.30, -0.08)},
            'tail': {'from_body': (0, -0.40, 0.04)},
        },
    },
    
    'horse': {
        'name': 'Horse',
        'description': 'Four-legged equine with long legs and neck',
        'symmetry_axis': 'X',
        'body_proportions': {
            'head_ratio': 0.12,
            'body_ratio': 0.40,
            'leg_ratio': 0.42,
            'tail_ratio': 0.06,
        },
        'segment_hints': {
            'head': {
                'position': 'front_top',
                'z_min': 0.55,
                'z_max': 1.0,
                'y_min': 0.70,
                'y_max': 1.0,
                'expected_volume_ratio': 0.08,
            },
            'body': {
                'position': 'center',
                'z_min': 0.40,
                'z_max': 0.85,
                'y_min': 0.20,
                'y_max': 0.75,
                'expected_volume_ratio': 0.35,
            },
            'leg_front_l': {
                'position': 'front_bottom_left',
                'z_min': 0.0,
                'z_max': 0.55,
                'y_min': 0.50,
                'y_max': 0.75,
                'x_side': 'negative',
                'expected_volume_ratio': 0.10,
            },
            'leg_front_r': {
                'position': 'front_bottom_right',
                'z_min': 0.0,
                'z_max': 0.55,
                'y_min': 0.50,
                'y_max': 0.75,
                'x_side': 'positive',
                'expected_volume_ratio': 0.10,
            },
            'leg_back_l': {
                'position': 'back_bottom_left',
                'z_min': 0.0,
                'z_max': 0.55,
                'y_min': 0.10,
                'y_max': 0.35,
                'x_side': 'negative',
                'expected_volume_ratio': 0.10,
            },
            'leg_back_r': {
                'position': 'back_bottom_right',
                'z_min': 0.0,
                'z_max': 0.55,
                'y_min': 0.10,
                'y_max': 0.35,
                'x_side': 'positive',
                'expected_volume_ratio': 0.10,
            },
            'tail': {
                'position': 'back',
                'z_min': 0.35,
                'z_max': 0.70,
                'y_min': 0.0,
                'y_max': 0.15,
                'expected_volume_ratio': 0.04,
            },
        },
        'joint_offsets': {
            'neck': {'from_body': (0, 0.40, 0.20), 'from_head': (0, -0.15, -0.08)},
            'front_legs': {'from_body': (0.15, 0.35, -0.15)},
            'back_legs': {'from_body': (0.15, -0.35, -0.12)},
            'tail': {'from_body': (0, -0.45, 0.08)},
        },
    },
    
    'bird': {
        'name': 'Bird',
        'description': 'Two-legged with wings instead of front legs',
        'symmetry_axis': 'X',
        'body_proportions': {
            'head_ratio': 0.15,
            'body_ratio': 0.55,
            'leg_ratio': 0.15,
            'wing_ratio': 0.15,
        },
        'segment_hints': {
            'head': {
                'position': 'front_top',
                'z_min': 0.70,
                'z_max': 1.0,
                'y_min': 0.60,
                'y_max': 1.0,
                'expected_volume_ratio': 0.10,
            },
            'body': {
                'position': 'center',
                'z_min': 0.20,
                'z_max': 0.80,
                'y_min': 0.20,
                'y_max': 0.80,
                'expected_volume_ratio': 0.50,
            },
            'leg_back_l': {
                'position': 'bottom_left',
                'z_min': 0.0,
                'z_max': 0.35,
                'y_min': 0.30,
                'y_max': 0.60,
                'x_side': 'negative',
                'expected_volume_ratio': 0.06,
            },
            'leg_back_r': {
                'position': 'bottom_right',
                'z_min': 0.0,
                'z_max': 0.35,
                'y_min': 0.30,
                'y_max': 0.60,
                'x_side': 'positive',
                'expected_volume_ratio': 0.06,
            },
            'wing_l': {
                'position': 'side_left',
                'z_min': 0.35,
                'z_max': 0.75,
                'y_min': 0.30,
                'y_max': 0.70,
                'x_side': 'negative',
                'x_extent': 'far',
                'expected_volume_ratio': 0.12,
            },
            'wing_r': {
                'position': 'side_right',
                'z_min': 0.35,
                'z_max': 0.75,
                'y_min': 0.30,
                'y_max': 0.70,
                'x_side': 'positive',
                'x_extent': 'far',
                'expected_volume_ratio': 0.12,
            },
            'tail': {
                'position': 'back',
                'z_min': 0.25,
                'z_max': 0.55,
                'y_min': 0.0,
                'y_max': 0.25,
                'expected_volume_ratio': 0.04,
            },
        },
        'joint_offsets': {
            'neck': {'from_body': (0, 0.30, 0.15), 'from_head': (0, -0.05, -0.05)},
            'back_legs': {'from_body': (0.08, 0.0, -0.15)},
            'wings': {'from_body': (0.20, 0.10, 0.05)},
            'tail': {'from_body': (0, -0.35, 0.0)},
        },
    },
    
    'rabbit': {
        'name': 'Rabbit',
        'description': 'Four-legged with long ears and short tail',
        'symmetry_axis': 'X',
        'body_proportions': {
            'head_ratio': 0.20,
            'body_ratio': 0.55,
            'leg_ratio': 0.22,
            'tail_ratio': 0.03,
        },
        'segment_hints': {
            'head': {
                'position': 'front_top',
                'z_min': 0.50,
                'z_max': 1.0,
                'y_min': 0.60,
                'y_max': 1.0,
                'expected_volume_ratio': 0.15,
            },
            'body': {
                'position': 'center',
                'z_min': 0.20,
                'z_max': 0.70,
                'y_min': 0.15,
                'y_max': 0.75,
                'expected_volume_ratio': 0.50,
            },
            'leg_front_l': {
                'position': 'front_bottom_left',
                'z_min': 0.0,
                'z_max': 0.40,
                'y_min': 0.50,
                'y_max': 0.75,
                'x_side': 'negative',
                'expected_volume_ratio': 0.05,
            },
            'leg_front_r': {
                'position': 'front_bottom_right',
                'z_min': 0.0,
                'z_max': 0.40,
                'y_min': 0.50,
                'y_max': 0.75,
                'x_side': 'positive',
                'expected_volume_ratio': 0.05,
            },
            'leg_back_l': {
                'position': 'back_bottom_left',
                'z_min': 0.0,
                'z_max': 0.50,
                'y_min': 0.10,
                'y_max': 0.40,
                'x_side': 'negative',
                'expected_volume_ratio': 0.08,
            },
            'leg_back_r': {
                'position': 'back_bottom_right',
                'z_min': 0.0,
                'z_max': 0.50,
                'y_min': 0.10,
                'y_max': 0.40,
                'x_side': 'positive',
                'expected_volume_ratio': 0.08,
            },
            'tail': {
                'position': 'back',
                'z_min': 0.30,
                'z_max': 0.50,
                'y_min': 0.0,
                'y_max': 0.15,
                'expected_volume_ratio': 0.02,
            },
        },
        'joint_offsets': {
            'neck': {'from_body': (0, 0.30, 0.10), 'from_head': (0, -0.08, -0.05)},
            'front_legs': {'from_body': (0.08, 0.28, -0.08)},
            'back_legs': {'from_body': (0.10, -0.25, -0.06)},
            'tail': {'from_body': (0, -0.35, 0.02)},
        },
    },
}


def get_preset_names():
    """Return list of (id, name, description) for UI enum"""
    return [(key, preset['name'], preset['description']) 
            for key, preset in ANIMAL_PRESETS.items()]


def get_preset(preset_id):
    """Get preset configuration by ID"""
    return ANIMAL_PRESETS.get(preset_id)


def get_segment_bounds_from_preset(preset_id, mesh_bounds):
    """
    Calculate segment bounding boxes based on preset ratios and mesh dimensions
    
    Args:
        preset_id: Animal preset identifier
        mesh_bounds: Dictionary with 'min', 'max', 'size' vectors
    
    Returns:
        Dictionary mapping segment names to their expected bounding regions
    """
    preset = get_preset(preset_id)
    if not preset:
        return {}
    
    result = {}
    
    min_co = mesh_bounds['min']
    max_co = mesh_bounds['max']
    size = mesh_bounds['size']
    
    for segment_name, hints in preset['segment_hints'].items():
        seg_min = min_co.copy()
        seg_max = max_co.copy()
        
        seg_min.z = min_co.z + size.z * hints['z_min']
        seg_max.z = min_co.z + size.z * hints['z_max']
        
        seg_min.y = min_co.y + size.y * hints['y_min']
        seg_max.y = min_co.y + size.y * hints['y_max']
        
        if 'x_side' in hints:
            center_x = (min_co.x + max_co.x) / 2
            if hints['x_side'] == 'negative':
                seg_max.x = center_x
            else:
                seg_min.x = center_x
        
        result[segment_name] = {
            'min': seg_min,
            'max': seg_max,
            'expected_ratio': hints.get('expected_volume_ratio', 0.1),
        }
    
    return result
