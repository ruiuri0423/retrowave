# -*- coding: utf-8 -*-
"""Generate assets/banner.png: hand-drawn light-blue circuit/waveform motifs
scattered on a dark-blue background, with a centered cyber 'RetroWave' wordmark.
Run once: python assets/_make_banner.py  (kept for reproducibility, not imported)."""
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

random.seed(7)
W, H = 1280, 360
S = 2                       # supersample factor for crisp edges
w, h = W * S, H * S

# ---- background: dark-blue vertical gradient ----
top, bot = (12, 20, 48), (20, 34, 74)
bg = Image.new("RGB", (w, h))
px = bg.load()
for y in range(h):
    t = y / (h - 1)
    c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    for x in range(w):
        px[x, y] = c
draw = ImageDraw.Draw(bg, "RGBA")

LIGHT = (138, 198, 246)
LIGHT2 = (96, 160, 220)
wd = 3 * S
def J(a):                   # hand-drawn jitter
    return a + random.uniform(-2.2, 2.2) * S


def clk(x, y, periods, pw, amp, col):
    pts, level, xx = [], y + amp, x
    for _ in range(periods * 2):
        pts.append((J(xx), level))
        pts.append((J(xx + pw / 2), level))
        level = (y - amp) if level == y + amp else (y + amp)
        xx += pw / 2
    draw.line(pts, fill=col, width=wd, joint="curve")


def bus(x, y, segs, sw, amp, col):
    yhi, ylo, r, xx = y - amp, y + amp, amp * 0.7, x
    for _ in range(segs):
        draw.line([(J(xx), y), (J(xx + r), yhi), (J(xx + sw - r), yhi), (J(xx + sw), y)],
                  fill=col, width=wd, joint="curve")
        draw.line([(J(xx), y), (J(xx + r), ylo), (J(xx + sw - r), ylo), (J(xx + sw), y)],
                  fill=col, width=wd, joint="curve")
        xx += sw


def pulse(x, y, amp, col):
    draw.line([(J(x), y), (J(x + 18 * S), y), (J(x + 18 * S), y - amp),
               (J(x + 34 * S), y - amp), (J(x + 34 * S), y), (J(x + 60 * S), y)],
              fill=col, width=wd, joint="curve")


def resistor(x, y, col):
    pts, zz = [(x, y)], 10 * S
    for i in range(6):
        pts.append((x + (i + 1) * zz, y + (zz if i % 2 else -zz)))
    pts.append((pts[-1][0] + zz, y))
    draw.line(pts, fill=col, width=wd, joint="curve")


def cap(x, y, col):
    draw.line([(x, y - 14 * S), (x, y + 14 * S)], fill=col, width=wd)
    draw.line([(x + 10 * S, y - 14 * S), (x + 10 * S, y + 14 * S)], fill=col, width=wd)


def node(x, y, col):
    r = 5 * S
    draw.ellipse([x - r, y - r, x + r, y + r], outline=col, width=wd)


motifs = [
    lambda x, y: clk(x, y, 3, 46 * S, 16 * S, (*LIGHT2, 150)),
    lambda x, y: bus(x, y, 3, 60 * S, 16 * S, (*LIGHT2, 150)),
    lambda x, y: pulse(x, y, 28 * S, (*LIGHT2, 150)),
    lambda x, y: resistor(x, y, (*LIGHT2, 140)),
    lambda x, y: cap(x, y, (*LIGHT2, 140)),
    lambda x, y: node(x, y, (*LIGHT2, 150)),
]
positions = [(80, 70), (360, 60), (700, 80), (1000, 60), (1140, 120), (150, 300),
             (430, 310), (760, 300), (1030, 300), (560, 150), (900, 180),
             (250, 180), (1180, 250), (40, 200)]
for (mx, my) in positions:
    random.choice(motifs)(mx * S, my * S)
clk(60 * S, 52 * S, 6, 64 * S, 18 * S, (*LIGHT, 210))     # brighter feature bands
bus(700 * S, 312 * S, 4, 90 * S, 18 * S, (*LIGHT, 210))


def load_font(size):
    for c in ["C:/Windows/Fonts/Bahnschrift.ttf", "C:/Windows/Fonts/consolab.ttf",
              "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            pass
    return ImageFont.load_default()


font = load_font(150 * S)
text = "RetroWave"
bb = draw.textbbox((0, 0), text, font=font)
tw, th = bb[2] - bb[0], bb[3] - bb[1]
tx = (w - tw) // 2 - bb[0]; ty = (h - th) // 2 - bb[1]

glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
ImageDraw.Draw(glow).text((tx, ty), text, font=font, fill=(80, 200, 255, 255))
glow = glow.filter(ImageFilter.GaussianBlur(10 * S))
bg = Image.alpha_composite(bg.convert("RGBA"), glow)
draw = ImageDraw.Draw(bg, "RGBA")
draw.text((tx + 4 * S, ty + 4 * S), text, font=font, fill=(20, 120, 170, 180))  # cyber shadow
draw.text((tx, ty), text, font=font, fill=(224, 248, 255, 255),
          stroke_width=2 * S, stroke_fill=(60, 200, 255, 255))
for y in range(0, h, 4 * S):                                  # retro scanlines
    draw.line([(0, y), (w, y)], fill=(0, 0, 0, 26), width=S)

out = bg.convert("RGB").resize((W, H), Image.LANCZOS)
out.save(os.path.join(os.path.dirname(__file__), "banner.png"))
print("banner.png done", out.size)
