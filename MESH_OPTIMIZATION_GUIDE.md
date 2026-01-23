# Mesh Optimization Guide

Complete guide for mesh reduction in the Pet Model Optimizer addon.

## Table of Contents
1. [Overview](#overview)
2. [Mesh Cleaning](#mesh-cleaning-first-step)
3. [Feature Edge Detection](#feature-edge-detection)
4. [Pre-Segmentation Optimization](#pre-segmentation-optimization)
5. [Post-Split Optimization](#post-split-optimization)
6. [Edge Control](#edge-control)
7. [Troubleshooting](#troubleshooting)

---

## Overview

### What is Mesh Optimization?

Mesh optimization (also called decimation or polygon reduction) reduces the number of polygons in a 3D model while preserving its shape and visual quality. This is critical for:
- **Performance**: Lower polygon counts = faster rendering
- **File size**: Smaller models load faster
- **Roblox requirements**: Platform limits for polygon counts
- **Game optimization**: Maintain smooth framerates

### When to Use

**Pre-Segmentation Optimization** (Before splitting):
- Initial model has 500K+ vertices
- Need to reduce complexity before processing
- Want to preserve overall shape and features

**Post-Split Optimization** (After splitting):
- Individual parts still too dense
- Need to optimize each part independently  
- Want to preserve cut boundaries and pivot points

### Expected Results

With proper settings:
- **Sharp edges preserved**: Body part connections remain crisp
- **UV coordinates preserved**: Textures still map correctly
- **Materials preserved**: All material assignments intact
- **Controlled reduction**: Small steps allow quality monitoring
- **Iterative process**: Click, review, repeat until satisfied

---

## Mesh Cleaning (First Step)

### Why Clean First?

Holes appearing during decimation are almost always caused by **bad geometry** that exists before you start reducing. Common issues:

- **Overlapping vertices**: Two vertices at the same location (from imports)
- **Loose geometry**: Vertices/edges floating in space, not part of any face
- **Degenerate faces**: Triangles with zero area (collapsed faces)
- **Non-manifold edges**: Edges shared by more than 2 faces

**The Solution**: Always clean your mesh BEFORE any decimation. This prevents 90% of hole-related problems.

### How to Use

1. **Select your mesh** in Object mode
2. **Check the problem analysis** - the panel shows counts of each issue type:
   - Loose verts: Vertices not connected to anything
   - Loose edges: Edges not part of any face
   - Degenerate: Zero-area faces that cause issues
   - Non-manifold: Edges shared by 3+ faces (problematic topology)
3. **Adjust settings if needed**:
   - Merge Distance: How close vertices must be to merge (default 0.0001)
   - Delete Loose: Remove floating geometry (recommended: ON)
   - Dissolve Degenerate: Remove zero-area faces (recommended: ON)
4. **Click "Clean Mesh"** - fixes all issues in one click
5. **Proceed to Feature Detection** and decimation

### What Gets Cleaned

The cleaning process performs three operations in sequence:

**1. Merge by Distance** (remove overlapping vertices)
- Finds vertices closer than the merge distance
- Combines them into a single vertex
- Default 0.0001 units is very conservative (won't change shape)
- Fixes: Overlapping vertices from CAD imports, boolean operations

**2. Delete Loose Geometry** (remove disconnected elements)
- Removes vertices not connected to any edges
- Removes edges not connected to any faces
- Fixes: Leftover geometry from modeling, import artifacts

**3. Dissolve Degenerate** (remove zero-area faces)
- Removes faces with zero or near-zero area
- Removes edges with zero length
- Fixes: Collapsed triangles that cause decimation to fail

### Settings Explained

**Merge Distance** (default: 0.0001)
- Very small = only merge truly overlapping vertices (safe, recommended)
- Larger values = merge more aggressively (may change shape)
- **Recommendation**: Keep at 0.0001 unless you have specific issues
- If you're seeing "No issues detected" but still have problems, try 0.001

**Delete Loose Geometry** (default: ON)
- Removes vertices not connected to any edges
- Removes edges not connected to any faces
- **Safe to leave ON** - won't affect visible mesh
- Only removes floating/disconnected geometry

**Dissolve Degenerate** (default: ON)
- Removes faces with zero area (collapsed triangles)
- Removes edges with zero length
- **Safe to leave ON** - these are always problematic
- Essential for preventing holes during decimation

### When to Clean

**Always clean before decimation if**:
- **Importing from other software** (OBJ, FBX, STL, etc.)
- **After boolean operations** - often create non-manifold geometry
- **After manual modeling** - may have leftover vertices/edges
- **If you see holes during decimation** - go back, clean, try again
- **Working with scanned models** - often have duplicate vertices

**You can skip cleaning if**:
- Model created entirely in Blender with clean topology
- Already cleaned the mesh previously
- Panel shows "No obvious issues detected"

### Example Workflow

```
1. Import dog model from OBJ file
   → Panel shows: "22 issues found!"
   → Loose verts: 12  |  Loose edges: 5
   → Degenerate: 3    |  Non-manifold: 2

2. Click "Clean Mesh" with default settings
   → Result: "Cleaned: merged 12 overlapping verts, 
              removed 5 loose edges, dissolved 3 degenerate"
   → Panel now shows: "Mesh is clean ✓"

3. Proceed to Feature Detection
   → Click "Detect Features" (30° threshold)
   → Marked: 2,847 edges

4. Begin Decimation
   → Click "Reduce by 5%" repeatedly
   → NO HOLES appear because geometry is clean!
```

### Troubleshooting

**Problem**: "No issues detected" but still getting holes

**Solutions**:
- Try increasing merge distance to 0.001 (merge more aggressively)
- Check in Edit Mode for internal faces (select all, Mesh → Clean Up → Delete Loose)
- Look for non-planar faces (faces with vertices not in same plane)

**Problem**: Cleaning changed my model's shape

**Solutions**:
- Merge distance too high - use 0.0001 or lower
- Undo (Ctrl+Z) and adjust settings
- If shape change is minimal, it's fixing overlapping vertices (good thing)

**Problem**: Still seeing "X issues found" after cleaning

**Solutions**:
- Some non-manifold edges can't be auto-fixed
- Manual fix: Edit Mode → Select → Select All by Trait → Non-Manifold
- Delete or dissolve the problematic edges
- May need manual topology work for complex issues

---

## Feature Edge Detection

### What are Feature Edges?

Feature edges are **sharp edges** in the mesh where the surface changes direction significantly. In animal models, these are typically:
- **Leg-body connections**: Where legs attach to the body
- **Head-neck connection**: Where head meets body
- **Tail attachment**: Where tail connects to body
- **Wing attachments**: For flying animals
- **Facial features**: Ears, snout, eyes

### Why Detect Features?

When reducing polygons, you want to:
- **Preserve** sharp edges (keep the model's character)
- **Reduce** smooth surfaces (less visually important)

Without feature detection, the decimation algorithm treats all edges equally, potentially smoothing out important details.

### How to Use "Detect Features"

1. **Select your mesh** in Object mode
2. **Set Angle Threshold**:
   - Default: 30 degrees (good for most models)
   - Lower (15-25°): More edges marked as "sharp" (preserves more detail)
   - Higher (40-60°): Fewer edges marked (allows more reduction)
3. **Click "Detect Features"** button
4. **Review the count**: "Last detection marked: X edges"

### Angle Threshold Explained

The angle threshold determines how "sharp" an edge must be to be protected:

```
15° - Very sensitive (protects subtle curves)
30° - Balanced (recommended starting point)
45° - Moderate (only obvious corners)
60° - Aggressive (only very sharp edges)
```

**Example**: For a dog model:
- 30°: Preserves leg-body connections, ear edges, snout definition
- 45°: Preserves only obvious joints, may lose some facial detail
- 60°: Preserves only the sharpest edges, may round off legs

### Visual Indication

After detection, edges are marked in the mesh:
- In **Edit Mode**: Select → Select All by Trait → Sharp Edges
- The marked edges will be selected (you can see what's protected)

### When to Re-Detect

- After changing the angle threshold
- If reduction results are too aggressive
- If you manually edited the mesh

---

## Pre-Segmentation Optimization

### Workflow (Step-by-Step)

#### 1. Load and Inspect Your Model

```
Object: [your_model]
Vertices: 224,295  |  Faces: 448,590
```

Note the recommended step size. For this example: "Medium-large mesh: 3% recommended"

#### 2. Clean the Mesh (IMPORTANT - Do This First!)

```
[Step 1: Mesh Cleaning]
  Loose verts: 12   |  Loose edges: 5
  Degenerate: 3     |  Non-manifold: 2
  Total: 22 issues found!
  
  Merge Distance: [0.0001________]
  [x] Delete Loose Geometry
  [x] Dissolve Degenerate
  
  [Clean Mesh (22 issues)]
```

After clicking:
```
  Mesh is clean ✓
  Cleaned: merged 12 overlapping verts, removed 5 loose edges, dissolved 3 degenerate
```

**Why this matters**: Cleaning prevents holes during decimation. Always do this first!

#### 3. Detect Features

```
[Step 2: Feature Detection]
  Angle Threshold: [====30=====] degrees
  [Detect Features]
```

After clicking:
```
  Sharp: 1,247  |  Boundary: 340
  Last detection marked: 1,247 edges ✓
```

#### 4. Configure Reduction Settings

```
[Step 3: Iterative Reduction]
  Reduction Step:  [===5%======]  (11,200 verts/step)
  [x] Auto Step Size
  [x] Preserve Sharp Edges
  [x] Preserve UV Seams
```

**Settings Explained**:
- **Reduction Step**: How much to reduce per click (1-20%)
- **Auto Step Size**: Automatically calculate safe step (recommended)
- **Preserve Sharp Edges**: Respect marked feature edges
- **Preserve UV Seams**: Protect UV texture boundaries

#### 5. Click "Reduce by 5%" - ONE STEP

```
Will remove ~11,200 vertices per step
[Reduce by 5%]  <-- Click this
```

**What happens**:
- Removes approximately 5% of vertices
- Preserves marked sharp edges
- Updates progress display
- Can be undone with Ctrl+Z

#### 6. Review Results

After reduction:
```
[Optimization Progress]
  Original: 448,590 faces
  Current: 426,160 faces (5.0% reduced)
  Steps taken: 1
```

**Review checklist**:
- Are sharp edges still crisp?
- Are textures still aligned?
- Is overall shape preserved?
- Do body part connections look good?

#### 7. Repeat as Needed

Click "Reduce by 5%" again for another step:
```
Steps taken: 2
Current: 404,850 faces (9.8% reduced)
```

Continue until satisfied with the balance between:
- Polygon count (lower = better performance)
- Visual quality (higher = better appearance)

### Auto Step Size Explained

When **Auto Step Size** is enabled:

For large meshes (500K+ vertices):
- Automatically uses 1-2% reduction per step
- Prevents overwhelming changes
- Keeps reduction under 10K vertices per step

For smaller meshes (<100K vertices):
- Can use larger steps (10-20%)
- Faster workflow for simple models

**When to disable**: If you want manual control over exact percentage

### Target-Based Reduction (Advanced)

For automated reduction to a specific face count:

```
[Target-Based Reduction]
  Target Faces: [50000____]
  [Auto-Reduce to Target]
```

**What happens**:
- Runs MULTIPLE steps automatically
- Uses adaptive step sizes (larger when far, smaller when close)
- Respects feature preservation settings
- Stops at target or max 50 iterations

**Warning**: This is multi-step automation. Use for:
- Known target face counts
- Batch processing
- Rapid prototyping

**NOT recommended for**: Fine-tuning with quality review

---

## Post-Split Optimization

After splitting your model into parts (head, body, legs, tail), you can optimize each part independently while preserving cut boundaries.

### Workflow (Step-by-Step)

#### 1. Select Split Parts

Select the parts you want to optimize:
- Individual part: Select one (e.g., just the head)
- Batch: Select multiple (e.g., all four legs)
- All parts: Select everything

```
Selected Parts: head, body, leg_front_l (3)
  head: 2,450 faces
  body: 12,300 faces  
  leg_front_l: 1,200 faces
Total: 15,950 faces
```

#### 2. (Optional) Mark Boundaries for Protection

```
[Boundary Protection]
  [x] Preserve Boundaries
  [x] Preserve Pivots
  [Mark Boundaries]
```

**What this does**:
- Detects open edges (where parts were cut)
- Marks them as "sharp" to protect during reduction
- Prevents deformation at cut surfaces

After clicking:
```
Total boundary edges: 487
```

#### 3. Configure Reduction

```
[Per-Part Reduction]
  Reduction Step: [===5%======]
  Will remove ~798 faces total
```

#### 4. Click "Reduce All by 5%" - ONE STEP

```
[Reduce All by 5%]  <-- Click this
```

**What happens**:
- Each selected part reduced by 5%
- Boundary edges protected
- Parts optimized independently
- Can be undone with Ctrl+Z

#### 5. Review and Repeat

Check each part:
- Are cut boundaries still clean?
- Are shapes preserved?
- Do parts still fit together?

Repeat reduction as needed.

### Single Part vs Batch

**Single Part Reduction**:
```
[Single Part Reduction]
  Active: head
  [Reduce head]
```
- Optimizes only the active object
- Use for fine-tuning individual parts

**Batch Reduction**:
```
[Reduce All by 5%]
```
- Optimizes all selected parts at once
- Use for consistent reduction across multiple parts

---

## Edge Control

### Manual Edge Marking

You can manually mark edges for protection without using auto-detection:

#### Method 1: Mark Sharp in Edit Mode

1. Switch to **Edit Mode** (Tab)
2. Switch to **Edge Select** mode (2)
3. Select edges you want to protect
4. Press **Ctrl+E** → Mark Sharp
5. Return to Object Mode

These marked edges will be preserved during decimation.

#### Method 2: Mark Seams (Stronger Protection)

1. In Edit Mode, select edges
2. Press **Ctrl+E** → Mark Seam
3. Seams provide stronger protection than sharp marks

### Preserve Sharp vs Preserve Seams

| Setting | What It Does | When to Use |
|---------|--------------|-------------|
| **Preserve Sharp Edges** | Respects edges marked as "sharp" | Always recommended for character models |
| **Preserve UV Seams** | Respects UV texture boundaries | When model has UV unwrapping, prevents texture distortion |

Both can be enabled simultaneously (recommended).

### Feature Detection vs Manual Marking

**Feature Detection** (Automatic):
- Analyzes entire mesh
- Finds edges by angle threshold
- Fast and consistent
- Good for initial protection

**Manual Marking**:
- Full control over specific edges
- Can protect areas auto-detection missed
- Can refine auto-detection results
- Use for fine-tuning

**Best Practice**: Use auto-detection first, then manually mark additional edges if needed.

### How Blender's Decimate Respects Edges

The Decimate modifier (which we use internally):
1. Checks each edge before collapsing
2. Skips edges marked as "sharp"
3. Skips edges marked as "seam"
4. Skips boundary edges (open meshes)
5. Collapses remaining edges by visual importance

Result: Protected edges remain unchanged, smooth surfaces reduced.

---

## Expected Results

### With Feature Detection Enabled

**Before Reduction** (224K vertices):
- Leg-body connection: Sharp, defined edge
- Body surface: Smooth, detailed

**After 50% Reduction** (112K vertices):
- Leg-body connection: **Still sharp** ✓
- Body surface: Smoothed but shape preserved ✓

### Without Feature Detection

**After 50% Reduction**:
- Leg-body connection: **Rounded, softened** ✗
- Body surface: Over-smoothed ✗
- Model loses character and definition

### UV Preservation

**Always preserved** (with or without feature detection):
- UV coordinates interpolated correctly
- Textures remain aligned
- No stretching or distortion

### Material Preservation

**Always preserved**:
- Material assignments intact
- Face material indices maintained
- No material loss

---

## Troubleshooting

### Problem: Model Losing Too Much Detail

**Symptoms**: After reduction, model looks "blobby" or undefined

**Solutions**:
1. **Reduce step size**: Use 1-2% instead of 5%
2. **Detect features first**: Click "Detect Features" before reducing
3. **Lower angle threshold**: Use 20-25° to protect more edges
4. **Undo and retry**: Ctrl+Z, then use smaller steps

### Problem: Sharp Edges Not Being Preserved

**Symptoms**: Leg-body connections, facial features becoming smooth

**Solutions**:
1. **Verify feature detection ran**: Check "Last detection marked: X edges"
2. **Verify Preserve Sharp is enabled**: Check the checkbox
3. **Try lower angle threshold**: 20° instead of 30°
4. **Manually mark critical edges**: Use Edit Mode → Select Edges → Mark Sharp

### Problem: Reduction Too Slow

**Symptoms**: Each step takes too long, mesh barely changes

**Solutions**:
1. **Disable Auto Step Size**: Uncheck "Auto Step Size"
2. **Increase Reduction Step**: Try 10-15% for faster reduction
3. **Use Target-Based Reduction**: Set target and click "Auto-Reduce to Target"

### Problem: Reduction Too Aggressive

**Symptoms**: One click removes too much, model deformed

**Solutions**:
1. **Enable Auto Step Size**: Let system calculate safe steps
2. **Reduce step size**: Use 1-2% for large meshes
3. **Undo immediately**: Ctrl+Z to revert
4. **Detect features first**: Protect important edges before reducing

### Problem: Over-Reduced Model

**Symptoms**: Reduced too much, quality unacceptable

**Solutions**:
1. **Undo multiple times**: Ctrl+Z repeatedly to go back
2. **Reset stats**: Click "Reset Stats" to start fresh
3. **Use smaller steps**: 1-2% per click going forward

### Problem: UV Textures Distorted

**Symptoms**: After reduction, textures stretched or misaligned

**Solutions**:
1. **Verify Preserve UV Seams enabled**: Check the checkbox
2. **Detect features with higher threshold**: Use 40-45° to protect UV boundaries
3. **Check UV seams**: In Edit Mode, verify UV seams are marked
4. **Reduce more gradually**: Use 1-2% steps for texture-heavy models

### Problem: Post-Split Parts Don't Fit Together

**Symptoms**: After optimizing split parts, gaps or misalignment

**Solutions**:
1. **Mark boundaries BEFORE reducing**: Click "Mark Boundaries" first
2. **Verify Preserve Boundaries enabled**: Check the checkbox
3. **Reduce parts equally**: Use same percentage for all parts
4. **Don't optimize at cut edges**: Boundaries should be protected

---

## Best Practices

### For Large Meshes (500K+ vertices)

1. Always use Auto Step Size
2. Start with feature detection
3. Use 1-2% reduction steps
4. Monitor progress after each step
5. Expect 20-30 clicks to reach 50% reduction

### For Medium Meshes (100K-500K vertices)

1. Use Auto Step Size or manual 3-5%
2. Detect features first
3. Can use larger steps (5-10%)
4. Monitor every 2-3 steps

### For Small Meshes (<100K vertices)

1. Can use manual control
2. 10-20% steps acceptable
3. Feature detection still recommended
4. Fewer iterations needed

### For Character/Organic Models

1. **Always detect features** (preserve character)
2. Use 30° angle threshold
3. Enable both Preserve Sharp and Preserve Seams
4. Reduce gradually (5% steps)
5. Check silhouette after each reduction

### For Mechanical/Hard-Surface Models

1. Detect features with lower threshold (20-25°)
2. Critical: Preserve sharp edges
3. Can use larger reduction steps
4. Focus on edge preservation over smoothness

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Ctrl+Z** | Undo last reduction step |
| **Ctrl+Shift+Z** | Redo |
| **Tab** | Toggle Edit/Object mode |
| **2** | Edge select mode (Edit mode) |
| **Ctrl+E** | Edge menu (Mark Sharp, Mark Seam) |

---

## Workflow Examples

### Example 1: Large Dog Model (500K vertices → 50K)

**Goal**: Reduce by 90% while preserving shape

**Steps**:
1. Select dog model (500K vertices, 1M faces)
2. Click "Detect Features" with 30° threshold
   - Result: "Marked: 2,847 edges"
3. Click "Reduce by 5%" (Auto Step Size enabled)
   - Auto-calculated to 1% for safety (~5K vertices removed)
   - Result: 495K vertices (1% reduced)
4. Review: Looks good, edges preserved
5. Click "Reduce by 5%" again x 10 times
   - Each click: ~1% reduction
   - After 10 clicks: ~450K vertices (10% reduced)
6. Continue clicking until reaching 50K vertices
   - Total clicks: ~90 (1% per click)
   - Time: 5-10 minutes of clicking/reviewing
7. Final result: 50K vertices, all features preserved

### Example 2: Split Head Optimization

**Goal**: Optimize head part after splitting

**Steps**:
1. Select head object (12K faces)
2. Click "Mark Boundaries" to protect cut edge
   - Result: "Protected 127 boundary edges"
3. Set Reduction Step to 10% (smaller part, can be aggressive)
4. Click "Reduce head" 
   - Result: 10.8K faces (10% reduced)
5. Review: Cut boundary intact, shape preserved
6. Click "Reduce head" again
   - Result: 9.7K faces (19% total reduced)
7. Continue until satisfied

### Example 3: Batch Leg Optimization

**Goal**: Optimize all 4 legs at once

**Steps**:
1. Select all 4 leg objects
2. Click "Mark Boundaries" on all
   - Result: "Protected 487 boundary edges on 4 parts"
3. Set Reduction Step to 5%
4. Click "Reduce All by 5%"
   - Result: "Optimized 4 parts: 18,500 → 17,575 faces"
5. Review: All legs optimized equally, boundaries intact
6. Repeat as needed

---

## Technical Details

### How It Works

The Pet Model Optimizer uses **Blender's built-in Decimate modifier** internally. Here's what happens when you click a reduction button:

1. **Add Decimate Modifier** to object
2. **Set ratio**: `1.0 - reduction_percent` (e.g., 0.95 for 5% reduction)
3. **Configure options**:
   - Respect sharp edges: Yes (if enabled)
   - Respect UV seams: Yes (if enabled)
   - Triangulate: No (preserves quad faces)
4. **Apply modifier**: Make changes permanent
5. **Update stats**: Track cumulative reduction

This approach leverages Blender's battle-tested algorithm for reliable results.

### Vertex vs Face Count

- **Vertices**: Points in 3D space (corners of polygons)
- **Faces**: Polygons (usually triangles or quads)

Typical relationship: `Faces ≈ 2 × Vertices` (for triangulated meshes)

When we say "5% reduction":
- 5% of **faces** removed
- Usually ~5% of **vertices** removed
- Display shows both counts

### Performance Notes

**Single Step Performance**:
- <100K vertices: Instant (<0.1 seconds)
- 100K-500K vertices: Fast (0.1-0.5 seconds)
- 500K+ vertices: Moderate (0.5-2 seconds)

**Why iterative is better than one-shot**:
- Can monitor quality after each step
- Can stop when satisfied
- Can undo specific steps
- Less risk of over-reduction

---

## FAQ

**Q: How many vertices should my final model have?**
A: Depends on use case:
- Roblox pets: 5K-20K vertices (platform optimized)
- Game characters: 10K-50K vertices (performance balanced)
- Hero characters: 50K-100K vertices (quality focused)
- Background NPCs: 2K-10K vertices (performance critical)

**Q: Can I reduce by more than 20% per step?**
A: The UI limits to 20% to prevent accidents. For aggressive reduction, use "Auto-Reduce to Target" instead.

**Q: What if feature detection marks too many edges?**
A: Increase angle threshold (try 40-45°) to be more selective.

**Q: What if feature detection marks too few edges?**
A: Decrease angle threshold (try 20-25°) or manually mark additional edges.

**Q: Can I undo after multiple steps?**
A: Yes! Ctrl+Z repeatedly to go back through the history.

**Q: Does this affect my original file?**
A: No, reductions are applied to the active Blender session. Save only when satisfied.

**Q: Can I compare before/after?**
A: Yes! Before starting, duplicate your object (Shift+D) to keep an original reference.

**Q: What's the difference between this and Blender's Decimate modifier?**
A: We use Blender's Decimate internally but add:
- Automatic feature detection
- Safe step size calculation
- Progress tracking
- Batch optimization for split parts
- Boundary protection for split meshes

---

## Quick Reference Card

### Pre-Segmentation Workflow
```
1. Select mesh
2. [Clean Mesh] (ALWAYS DO THIS FIRST!)
3. [Detect Features] (30° threshold)
4. Set reduction % (5% recommended)
5. [Reduce by X%] <-- Click repeatedly
6. Review after each click
7. Repeat until satisfied
8. Ctrl+Z to undo if needed
```

### Post-Split Workflow
```
1. Select split part(s)
2. [Mark Boundaries]
3. Set reduction % (3-5% recommended)
4. [Reduce All by X%] <-- Click repeatedly
5. Review after each click
6. Repeat until satisfied
```

### Settings Quick Guide
- **Angle Threshold**: 20° (strict) to 45° (lenient)
- **Reduction Step**: 1% (safe) to 20% (aggressive)
- **Auto Step Size**: ON for large meshes, OFF for manual control
- **Preserve Sharp**: Always ON for character models
- **Preserve Seams**: ON if model has UV textures
- **Preserve Boundaries**: Always ON for split parts

---

## Additional Resources

- **Blender Decimate Modifier Docs**: https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/decimate.html
- **Complete Workflow Guide**: See `COMPLETE_WORKFLOW_GUIDE.md` for full pipeline
- **Plugin Documentation**: See `PLUGIN_DOCUMENTATION.md` for all features

---

**Last Updated**: January 2026
**Plugin Version**: 1.0.0
