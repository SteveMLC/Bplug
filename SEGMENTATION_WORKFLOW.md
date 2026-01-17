# Segmentation Workflow Guide

## Proper Button Functionality

### 1. **Preview Button** (Eye Icon)
**Purpose**: Preview segmentation results BEFORE finalizing or splitting

**What it does**:
- Creates vertex groups based on current settings
- Switches to **Weight Paint mode** automatically
- Selects the first vertex group for visualization
- Shows vertex groups in the Results section
- Does NOT split the mesh (non-destructive)

**How to use**:
1. Adjust settings (Pet Type, Detection Method, Sensitivity, etc.)
2. Click **"Preview"**
3. View results in Weight Paint mode
4. Switch between vertex groups in the Properties panel (Object Data → Vertex Groups) to see each part highlighted
5. Adjust settings and preview again if needed

**Visualization Tips**:
- In Weight Paint mode, each vertex group shows as a colored overlay
- Switch vertex groups in Properties panel (Object Data Properties → Vertex Groups dropdown)
- Red = selected vertex group, Blue = other groups
- You can paint/adjust vertex groups directly in Weight Paint mode

---

### 2. **Segment Model Button** (Gear Icon)
**Purpose**: Finalize segmentation and optionally auto-split

**What it does**:
- Creates vertex groups (same as Preview)
- Stores metrics (parts detected, vertex counts, processing time)
- If "Auto Split" is enabled: Automatically splits mesh into separate objects
- If "Auto Split" is disabled: Only creates vertex groups (recommended workflow)

**Recommended Settings**:
- ✅ **Auto Split: OFF** (default) - Preview first, then split manually when satisfied
- ✅ **Clear Existing Groups: ON** - Start fresh each time

**How to use**:
1. Preview first to check results
2. Adjust settings if needed
3. Click **"Segment Model"** to finalize
4. Review results in the Results section
5. Use "Split Manually" button when ready to split

---

### 3. **Split Manually Button**
**Purpose**: Split the mesh into separate objects based on vertex groups

**What it does**:
- Creates separate mesh objects for each vertex group
- Preserves UVs, vertex colors, and materials
- Creates pivot points at connection boundaries (if enabled)
- Can keep or delete the original mesh

**Options**:
- **Keep Original**: Keep the original mesh (recommended: ON)
- **Verify Data**: Check that UVs/colors/materials were preserved (recommended: ON)
- **Create Pivots**: Create Empty objects at split boundaries (recommended: ON)

**When to use**:
- After you've previewed and are satisfied with segmentation
- When you're ready to work with separate parts
- Before rigging or exporting

---

## Complete Workflow

### Step-by-Step Process

1. **Select Your Model**
   - Make sure it's a mesh object
   - Check that it's properly oriented (head forward, legs down)

2. **Configure Settings**
   - Choose Pet Type (Quadruped/Biped/Flying)
   - Enable "Geometry-Based Detection" (recommended)
   - Adjust Sensitivity if needed
   - **Disable "Auto Split"** (important!)

3. **Preview Segmentation**
   - Click **"Preview"** button
   - Blender switches to Weight Paint mode
   - Check Results section for vertex counts
   - Switch vertex groups in Properties panel to see each part

4. **Adjust if Needed**
   - If results look wrong, adjust settings:
     - Try different Pet Type
     - Adjust Sensitivity slider
     - Toggle Geometry-Based vs Spatial-Only
   - Click Preview again to see changes

5. **Finalize Segmentation**
   - When satisfied, click **"Segment Model"**
   - Review Results section
   - Check that all parts have vertices (not 0)

6. **Manual Adjustments (Optional)**
   - Switch to Weight Paint mode
   - Select vertex group in Properties panel
   - Use Blender's paint tools to add/remove vertices
   - Or use Edit mode: Select → Select by Vertex Group

7. **Split When Ready**
   - Click **"Split Manually"** button
   - Configure options (keep original, create pivots)
   - Mesh is split into separate objects
   - Pivot points created at boundaries

---

## Troubleshooting

### "0 vertices" in Results
- **Cause**: Vertex groups were created but no vertices assigned
- **Solution**: 
  - Check model orientation (might be rotated wrong)
  - Try different Pet Type
  - Adjust Sensitivity
  - Try Spatial-Only mode if Geometry-Based fails

### Preview shows wrong parts
- **Cause**: Model doesn't match template assumptions
- **Solution**:
  - Try different Pet Type
  - Adjust Sensitivity (lower = stricter boundaries)
  - Manually adjust vertex groups in Weight Paint mode

### Can't see vertex groups in Preview
- **Solution**: 
  - Make sure you're in Weight Paint mode
  - Check Properties panel → Object Data → Vertex Groups
  - Select a vertex group from the dropdown
  - The selected group will be highlighted in red

### Want to start over
- Click "Clear Existing Groups" checkbox
- Click Preview or Segment Model again

---

## Tips

- **Always preview first** before splitting
- **Keep Auto Split OFF** until you're satisfied
- **Use Weight Paint mode** to visualize and adjust
- **Check vertex counts** - empty groups (0 vertices) won't split properly
- **Geometry-Based** works better for complex/non-standard models
- **Spatial-Only** is fallback for simple models or when geometry-based fails
