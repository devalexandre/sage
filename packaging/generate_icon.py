#!/usr/bin/env python3
"""Generate assets/sage.png (512x512) and assets/sage.ico for packaging."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 512
OUT_DIR = Path(__file__).parent.parent / "assets"
OUT_DIR.mkdir(exist_ok=True)

# ── Draw purple circle with white "S" ─────────────────────────────────────────
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

draw.ellipse([0, 0, SIZE - 1, SIZE - 1], fill="#7C3AED")

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
]

font = None
for fp in FONT_PATHS:
    try:
        font = ImageFont.truetype(fp, 320)
        break
    except Exception:
        pass

if font is None:
    font = ImageFont.load_default()

bbox = draw.textbbox((0, 0), "S", font=font)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
x = (SIZE - tw) // 2 - bbox[0]
y = (SIZE - th) // 2 - bbox[1]
draw.text((x, y), "S", fill="white", font=font)

# ── PNG ───────────────────────────────────────────────────────────────────────
png_path = OUT_DIR / "sage.png"
img.save(png_path, "PNG")
print(f"✓ {png_path}")

# ── ICO (Windows — multiple sizes) ────────────────────────────────────────────
ico_sizes = [16, 32, 48, 64, 128, 256]
frames = [img.resize((s, s), Image.LANCZOS) for s in ico_sizes]
ico_path = OUT_DIR / "sage.ico"
frames[0].save(
    ico_path,
    format="ICO",
    sizes=[(s, s) for s in ico_sizes],
    append_images=frames[1:],
)
print(f"✓ {ico_path}")
