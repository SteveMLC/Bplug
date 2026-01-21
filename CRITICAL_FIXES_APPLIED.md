# Critical Fixes Applied for Mesh Optimization

## Issues Identified from User Feedback

1. **Preview reduces too aggressively** - 97.9% reduction instead of small iterative steps
2. **Feature Angle showing 1719°** - Unit conversion bug
3. **Step reduction range too limited** - Max 50% is too high, need smaller steps (1-5%)
4. **Not iterative** - Should go 499k → 470k, not 499k → 10k
5. **Centroid clustering too aggressive** - Unpredictable for small reductions

## Fixes Applied

### 1. ✅ Fixed Feature Angle Bug
**Problem:** Feature angle showing 1719° (30 radians instead of 30 degrees)

**Fix:**
- Changed default from `30.0` to `math.radians(30.0)` in PropertyGroup
- Updated preset application to use `math.radians()` for all angle values
- Removed double conversion in operator (was converting radians to radians)

**Files:**
- `blender_pet_optimizer/ui/panels.py` - Fixed default value
- `blender_pet_optimizer/operators/mesh_optimizer.py` - Fixed preset application

### 2. ✅ Expanded Step Reduction Range
**Problem:** Max step reduction was 50%, too high for fine control

**Fix:**
- Changed max from 0.5 (50%) to 0.20 (20%)
- Changed min from 0.01 (1%) to 0.005 (0.5%)
- Changed default from 0.1 (10%) to 0.05 (5%)
- Changed precision to 3 decimal places for fine control

**Files:**
- `blender_pet_optimizer/ui/panels.py` - PET_LowPolySettings
- `blender_pet_optimizer/operators/mesh_optimizer.py` - PET_OT_lowpoly_prep and PET_OT_iterative_optimize

### 3. ✅ Made Algorithm Selection Smarter
**Problem:** Centroid clustering too aggressive and unpredictable for small reductions

**Fix:**
- For steps <10%, always use QEM (better control)
- For steps <5%, always use QEM (precise control)
- Only use centroid for large meshes (200K+) with larger steps (10%+)
- Iterative operator now uses QEM for small steps automatically

**Files:**
- `blender_pet_optimizer/operators/mesh_optimizer.py` - Both operators

### 4. ✅ Improved Centroid Clustering Grid Size
**Problem:** Grid size calculation too aggressive, causing massive reductions

**Fix:**
- Grid size now scales with reduction amount
- For 1% reduction: uses 0.005 * size (very fine grid)
- For 20% reduction: uses 0.02 * size (moderate grid)
- Changed scaling algorithm to be more conservative for small reductions

**Files:**
- `blender_pet_optimizer/utils/algorithms.py` - centroid_cluster_decimate()
- `blender_pet_optimizer/operators/mesh_optimizer.py` - Grid size calculation

### 5. ✅ Increased Time Limits for Large Meshes
**Problem:** 3-second time limit causes early stops on large meshes

**Fix:**
- Time limit now scales with mesh size
- Small meshes: 3 seconds
- Large meshes (500K+): up to 30 seconds for queue building
- Separate time limits for queue building vs edge collapsing
- Collapse operations: up to 60 seconds for very large meshes

**Files:**
- `blender_pet_optimizer/utils/algorithms.py` - qem_edge_collapse()

### 6. ✅ Made Old Operator Use Advanced QEM
**Problem:** Old "Preview Low-Poly" operator doesn't use advanced features

**Fix:**
- Old operator now uses advanced QEM for large meshes (>100K) or small steps (<10%)
- Falls back to basic QEM only for smaller meshes with larger steps
- Better integration with advanced settings

**Files:**
- `blender_pet_optimizer/operators/mesh_optimizer.py` - PET_OT_lowpoly_prep.execute()

### 7. ✅ Improved Adaptive Step Sizing
**Problem:** Auto step size was too large (3-10%)

**Fix:**
- 500K+ vertices: 1% steps (was 3%)
- 300K-500K: 2% steps (was 5%)
- 100K-300K: 3% steps (was 7%)
- <100K: 5% steps (was 10%)

**Files:**
- `blender_pet_optimizer/operators/mesh_optimizer.py` - PET_OT_iterative_optimize.invoke()

### 8. ✅ Added UI Warnings and Guidance
**Problem:** Users don't know which operator to use

**Fix:**
- Added warning in Low-Poly Prep section to use "Iterative Optimize" for large meshes
- Added recommendation text with step size guidance
- Made "Iterative Optimize" button more prominent with "(Recommended)" label
- Added info about auto-adjusted step sizes

**Files:**
- `blender_pet_optimizer/ui/panels.py` - PET_PT_mesh_optimization.draw()

## Expected Behavior After Fixes

### For 499K Face Mesh:

**Before:**
- Step reduction 50% → 97.9% actual reduction (unpredictable)
- Goes from 499k → 10k in one step
- Feature angle shows 1719° (broken)

**After:**
- Step reduction 1-5% → Actual reduction matches target (1-5%)
- Goes from 499k → 470k-495k in one step (iterative)
- Feature angle shows 30° (correct)
- Uses QEM for precise control
- Can iterate: 499k → 470k → 445k → 420k, etc.

## Usage Recommendations

### For Large Meshes (500K+ faces):

1. **Use "Iterative Optimize" button** (not "Preview Low-Poly")
2. **Start with 1-2% steps** (auto-adjusted)
3. **Use "Balanced" preset** for good quality/reduction balance
4. **Iterate multiple times** to gradually reduce
5. **Check results after each step** before continuing

### Step Size Guidelines:

- **500K+ faces**: 1-2% per step
- **200K-500K faces**: 2-5% per step
- **100K-200K faces**: 5-10% per step
- **<100K faces**: 10-15% per step

### Algorithm Selection:

- **Small steps (<5%)**: Always uses QEM (automatic)
- **Medium steps (5-10%)**: Uses QEM for better control
- **Large steps (10%+)**: May use centroid for speed on very large meshes

## Testing Checklist

- [ ] Feature angle displays correctly (30°, not 1719°)
- [ ] Step reduction slider allows 0.5%-20% range
- [ ] 1% step on 499k mesh reduces to ~494k (not 10k)
- [ ] Can iterate: 499k → 494k → 489k → 484k
- [ ] "Iterative Optimize" button works correctly
- [ ] Presets apply correct values
- [ ] Corner preservation strength affects results

## Files Modified

1. `blender_pet_optimizer/ui/panels.py`
   - Fixed feature_angle default (math.radians)
   - Expanded step_reduction range (0.5%-20%)
   - Added UI warnings and guidance

2. `blender_pet_optimizer/operators/mesh_optimizer.py`
   - Fixed feature_angle in presets (math.radians)
   - Expanded step_reduction range
   - Improved algorithm selection
   - Made old operator use advanced QEM
   - Improved adaptive step sizing
   - Added warnings for large steps

3. `blender_pet_optimizer/utils/algorithms.py`
   - Improved centroid clustering grid size calculation
   - More conservative scaling for small reductions
   - Increased time limits for large meshes

## Next Steps

1. **Test with 499K face mesh:**
   - Use "Iterative Optimize" with 1% step
   - Verify it reduces to ~494k (not 10k)
   - Iterate multiple times to verify incremental reduction

2. **Verify Feature Angle:**
   - Check UI shows 30° (not 1719°)
   - Test with different values (25°, 45°)
   - Verify corner detection works correctly

3. **Test Step Range:**
   - Try 0.5% step (should work)
   - Try 1% step (should work)
   - Try 5% step (should work)
   - Verify actual reduction matches target
