import sys
import os
from PIL import Image

def create_assets(image_path, output_dir):
    try:
        img = Image.open(image_path)
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # 1. Create .ico file (multiple sizes for better scaling)
        icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        ico_path = os.path.join(output_dir, "icon.ico")
        img.save(ico_path, format="ICO", sizes=icon_sizes)
        print(f"Created {ico_path}")
        
        # 2. Create Wizard Image (.bmp) - Typically 164x314 for Inno Setup
        wizard_img = img.resize((164, 314), Image.Resampling.LANCZOS)
        wizard_path = os.path.join(output_dir, "wizard.bmp")
        wizard_img.save(wizard_path, format="BMP")
        print(f"Created {wizard_path}")
        
        # 3. Create Wizard Small Image (.bmp) - Typically 55x55 for Inno Setup
        wizard_small_img = img.resize((55, 55), Image.Resampling.LANCZOS)
        wizard_small_path = os.path.join(output_dir, "wizard_small.bmp")
        wizard_small_img.save(wizard_small_path, format="BMP")
        print(f"Created {wizard_small_path}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    image_path = sys.argv[1]
    output_dir = sys.argv[2]
    create_assets(image_path, output_dir)
