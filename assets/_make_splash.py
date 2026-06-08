# -*- coding: utf-8 -*-
"""Generate assets/splash.png: a small startup splash shown by the onefile exe
while it self-extracts. Run once: python assets/_make_splash.py."""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, S = 460, 220, 2
w, h = W * S, H * S
top, bot = (12, 20, 48), (20, 34, 74)
img = Image.new("RGB", (w, h))
px = img.load()
for y in range(h):
    t = y / (h - 1)
    c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    for x in range(w):
        px[x, y] = c
d = ImageDraw.Draw(img, "RGBA")

# a small clock motif as a flourish
LIGHT = (138, 198, 246, 230)
yb, amp, pw, x = h * 0.30, 14 * S, 40 * S, 60 * S
pts, lvl = [], yb + amp
for _ in range(8):
    pts.append((x, lvl)); pts.append((x + pw / 2, lvl))
    lvl = yb - amp if lvl == yb + amp else yb + amp
    x += pw / 2
d.line(pts, fill=LIGHT, width=3 * S, joint="curve")


def font(sz):
    for c in ["C:/Windows/Fonts/Bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf",
              "C:/Windows/Fonts/arialbd.ttf"]:
        try:
            return ImageFont.truetype(c, sz)
        except Exception:
            pass
    return ImageFont.load_default()


text = "RetroWave"
f = font(64 * S)
bb = d.textbbox((0, 0), text, font=f)
tx = (w - (bb[2] - bb[0])) // 2 - bb[0]; ty = int(h * 0.42)
glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
ImageDraw.Draw(glow).text((tx, ty), text, font=f, fill=(80, 200, 255, 255))
img = Image.alpha_composite(img.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(8 * S)))
d = ImageDraw.Draw(img, "RGBA")
d.text((tx, ty), text, font=f, fill=(224, 248, 255, 255),
       stroke_width=2 * S, stroke_fill=(60, 200, 255, 255))
fs = font(15 * S)
sub = "Loading..."
sb = d.textbbox((0, 0), sub, font=fs)
d.text(((w - (sb[2] - sb[0])) // 2, int(h * 0.78)), sub, font=fs, fill=(150, 180, 220, 255))

out = img.convert("RGB").resize((W, H), Image.LANCZOS)
out.save(os.path.join(os.path.dirname(__file__), "splash.png"))
print("splash.png done", out.size)
