# Quick Installation Guide - Pet Model Optimizer

## 🚀 Quick Start (5 Minutes)

### Step 1: Find Your Blender Addons Folder

**Windows:**
1. Press `Win + R` (Windows key + R)
2. Type: `%APPDATA%\Blender Foundation\Blender`
3. Press Enter
4. Open the folder for your Blender version (e.g., `4.0`, `3.6`, etc.)
5. Navigate to: `scripts\addons\`

**macOS:**
1. Open Finder
2. Press `Cmd + Shift + G`
3. Paste: `~/Library/Application Support/Blender/`
4. Open your Blender version folder
5. Navigate to: `scripts/addons/`

**Linux:**
```bash
cd ~/.config/blender/<version>/scripts/addons/
```
(Replace `<version>` with your Blender version number)

### Step 2: Copy the Plugin

1. **From this repository**, copy the entire `blender_pet_optimizer` folder
2. **Paste it** into your Blender addons directory
3. **Important**: The folder structure should look like this:
   ```
   addons/blender_pet_optimizer/
   ├── __init__.py
   ├── bl_info.json
   ├── operators/
   ├── ui/
   ├── utils/
   ├── config/
   └── data/
   ```

### Step 3: Enable in Blender

1. **Open Blender** (version 3.0 or later)
2. **Open Preferences**: 
   - `Edit` → `Preferences` 
   - Or press `Ctrl + ,` (Windows/Linux) or `Cmd + ,` (macOS)
3. **Go to Add-ons tab** (left sidebar)
4. **Search for**: `Pet Model Optimizer`
5. **Check the checkbox** to enable it
6. **Verify**: You should see a green checkmark ✓

### Step 4: Access the Plugin

1. **Open a 3D Viewport** (the main window where you see models)
2. **Press `N`** to open the N-panel (Properties panel on the right)
3. **Look for the `Pet Optimizer` tab** at the bottom of the panel tabs
4. **Click it** - You should see:
   - "Pet Model Optimizer" header
   - "Workflow: Segment → Optimize → Rig → Export"
   - Multiple collapsible sections

## ✅ Verification Checklist

- [ ] Plugin folder copied to correct location
- [ ] `__init__.py` exists in `blender_pet_optimizer/` folder
- [ ] Plugin enabled in Blender Preferences → Add-ons
- [ ] No errors in Blender's console (Window → Toggle System Console)
- [ ] "Pet Optimizer" tab visible in N-panel (press `N` in 3D Viewport)

## 🎯 First Use - Test Run

1. **Create or import a test mesh**:
   - `File` → `Import` → Choose your format
   - Or create a basic mesh: `Add` → `Mesh` → `Monkey` (Suzanne)

2. **Select the mesh** (click on it in viewport or outliner)

3. **Open Segmentation panel**:
   - Press `N` in 3D Viewport
   - Click `Pet Optimizer` tab
   - Expand "Segmentation" section

4. **Try segmentation**:
   - Choose pet type (Quadruped/Biped/Flying)
   - Click "Segment Model"
   - Check the Results box for parts detected

## 🐛 Troubleshooting

**Plugin not showing in Add-ons list?**
- Check folder name is exactly `blender_pet_optimizer` (not `blender_pet_model_optimizer`)
- Verify `__init__.py` is in the root of the plugin folder
- Make sure you're looking in the correct Blender version folder
- Try restarting Blender completely

**Plugin shows but won't enable?**
- Check Blender Console for errors (Window → Toggle System Console)
- Ensure Blender version is 3.0 or later
- Verify all Python files are present (check `operators/`, `ui/`, `utils/` folders)

**Can't find N-panel?**
- Press `N` in the 3D Viewport (not in other editors)
- Look for `Pet Optimizer` tab at the bottom of panel tabs
- Make sure you're in Object Mode (not Edit Mode)

**"Select a mesh object" error?**
- Make sure you have a mesh selected (not camera, light, or empty)
- Click on the mesh in the 3D Viewport or Outliner

## 📋 System Requirements

- **Blender**: Version 3.0 or later
- **Python**: Included with Blender (no separate installation needed)
- **OS**: Windows, macOS, or Linux

## 🎓 Next Steps

Once installed, see the main [README.md](README.md) for:
- Detailed usage guide
- Complete workflow examples
- Advanced features
- Troubleshooting tips

---

**Ready to go!** Open Blender and start segmenting! 🚀
