"""
Generates the Vyntra application icons (assets/icon.png and assets/icon.ico).
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw

def create_icon():
    assets_dir = Path(__file__).parent.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    # Base size 512x512 for smooth rendering
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 1. Background rounded container
    # Rounded rectangle with soft gradient / border
    margin = 32
    bg_box = [margin, margin, size - margin, size - margin]
    radius = 96
    
    # Dark modern slate background
    draw.rounded_rectangle(bg_box, radius=radius, fill=(15, 23, 42, 255), outline=(99, 102, 241, 230), width=8)
    
    # 2. Inner glow / decorative accent
    inner_box = [margin + 12, margin + 12, size - margin - 12, size - margin - 12]
    draw.rounded_rectangle(inner_box, radius=radius - 8, outline=(6, 182, 212, 120), width=4)
    
    # 3. Modern Stylized V / Play Mark
    # Let's draw an elegant play arrow merged with a modern 'V'
    # Coordinates centered
    # Left stroke of V
    left_points = [
        (160, 160),
        (205, 160),
        (256, 310),
        (256, 360),
        (210, 360),
    ]
    draw.polygon(left_points, fill=(6, 182, 212, 255)) # Cyan
    
    # Right stroke of V / Play triangle accent
    right_points = [
        (352, 160),
        (307, 160),
        (256, 310),
        (256, 360),
        (302, 360),
    ]
    draw.polygon(right_points, fill=(99, 102, 241, 255)) # Indigo
    
    # Center Play Symbol overlaid in pure white / accent
    play_arrow = [
        (230, 200),
        (320, 256),
        (230, 312),
    ]
    draw.polygon(play_arrow, fill=(248, 250, 252, 255)) # Pure crisp white
    
    # Audio waves on right
    wave_accent = [
        (340, 235),
        (346, 235),
        (346, 277),
        (340, 277),
    ]
    draw.rounded_rectangle([344, 236, 350, 276], radius=3, fill=(6, 182, 212, 220))
    draw.rounded_rectangle([360, 224, 366, 288], radius=3, fill=(99, 102, 241, 220))

    # Save PNG
    png_path = assets_dir / "icon.png"
    img.save(png_path, "PNG")
    print(f"Saved PNG to {png_path}")
    
    # Save multi-size ICO (Windows)
    ico_path = assets_dir / "icon.ico"
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(ico_path, format="ICO", sizes=sizes)
    print(f"Saved ICO to {ico_path}")

    # Save Apple macOS ICNS
    icns_path = assets_dir / "icon.icns"
    try:
        img.save(icns_path, format="ICNS")
        print(f"Saved macOS ICNS to {icns_path}")
    except Exception as e:
        print(f"Note: ICNS generation skipped: {e}")

if __name__ == "__main__":
    create_icon()
