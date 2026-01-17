"""
Package Blender Pet Model Optimizer addon for installation
Creates a zip file ready for Blender's Install Add-on feature
"""

import os
import sys
import zipfile
import shutil
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

def package_addon():
    """Create a zip file of the blender_pet_optimizer folder"""
    
    # Get the script directory (repository root)
    script_dir = Path(__file__).parent.absolute()
    addon_folder = script_dir / "blender_pet_optimizer"
    output_zip = script_dir / "blender_pet_optimizer.zip"
    
    # Check if addon folder exists
    if not addon_folder.exists():
        print(f"ERROR: Addon folder not found: {addon_folder}")
        print("Make sure this script is in the repository root directory.")
        return False
    
    # Check for required files
    required_files = ["__init__.py", "bl_info.json"]
    for req_file in required_files:
        if not (addon_folder / req_file).exists():
            print(f"ERROR: Required file not found: {req_file}")
            return False
    
    # Remove existing zip if it exists
    if output_zip.exists():
        print(f"Removing existing zip file: {output_zip}")
        try:
            output_zip.unlink()
        except PermissionError:
            print(f"WARNING: Could not delete existing zip (file may be open in Blender)")
            print(f"  Please close Blender or delete {output_zip.name} manually, then try again.")
            return False
    
    # Create zip file
    print(f"Creating zip file: {output_zip}")
    print(f"Packaging folder: {addon_folder}")
    
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Walk through the addon folder
        for root, dirs, files in os.walk(addon_folder):
            # Skip hidden files and __pycache__ directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            for file in files:
                # Skip hidden files and .pyc files
                if file.startswith('.') or file.endswith('.pyc'):
                    continue
                
                file_path = Path(root) / file
                # Get relative path from addon folder
                arcname = file_path.relative_to(addon_folder.parent)
                
                zipf.write(file_path, arcname)
                print(f"  Added: {arcname}")
    
    # Verify zip file
    zip_size = output_zip.stat().st_size
    print(f"\n[SUCCESS] Created: {output_zip}")
    print(f"  Size: {zip_size / 1024:.2f} KB")
    print(f"\nReady to install in Blender:")
    print(f"  1. Open Blender")
    print(f"  2. Edit → Preferences → Add-ons")
    print(f"  3. Click 'Install...' button")
    print(f"  4. Select: {output_zip.name}")
    print(f"  5. Enable 'Pet Model Optimizer' in the list")
    
    return True

if __name__ == "__main__":
    try:
        success = package_addon()
        if not success:
            input("\nPress Enter to exit...")
            exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        exit(1)
