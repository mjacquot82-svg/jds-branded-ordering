"""Generate the JDS illustrated starter image pack (placeholder artwork, v1).

Usage (from backend/):  python scripts/generate_starter_media.py [--out DIR] [--only key,key]

Output: <out>/cafe-restaurant/<key>-v1.webp at 1200×1200. All artwork is drawn
procedurally here — no photos, stock, scraped, or third-party assets — so it is
original to JDS and safe to ship. These are clearly-identified PLACEHOLDERS; see
docs/STARTER_MEDIA_ASSET_MANIFEST.md for the licensed photography still required.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from starter_art import (  # noqa: E402
    S, background, blank_mask, blur, ellipse_mask, finish, intersect, linear_alpha, mix, paint,
    paint_gradient, poly_mask, ring, rounded_rect_mask, shade, shadow, speckles, steam, stroke,
    subtract, union, vessel_mask, vessel_rx_at,
)
from PIL import Image, ImageDraw  # noqa: E402

CX = S / 2
FRAME = (330, 420, 2070, 2160)
PALETTES = {
    "coffee": dict(bg_top="#f4e9dd", bg_bottom="#e8d3bf", halo="#fbf3ea", surface="#dcc2a8"),
    "tea": dict(bg_top="#f1ece0", bg_bottom="#e2d6bf", halo="#faf6ec", surface="#d6c7a7"),
    "cold": dict(bg_top="#e6f2ec", bg_bottom="#cfe3d8", halo="#f4faf6", surface="#b9d4c5"),
    "bakery": dict(bg_top="#f8ebdc", bg_bottom="#efd6bd", halo="#fdf5ec", surface="#e2c19f"),
    "breakfast": dict(bg_top="#f6eedb", bg_bottom="#e9dbbd", halo="#fcf8ee", surface="#d9c59c"),
    "lunch": dict(bg_top="#ebf0e1", bg_bottom="#d7e1c9", halo="#f6f9f0", surface="#c2cfae"),
    "sweet": dict(bg_top="#f8e9e6", bg_bottom="#edd2cd", halo="#fdf4f2", surface="#e0bab3"),
}
CERAMIC = ("#ffffff", "#e9e3da")
ESPRESSO, CREMA, MILK, FOAM = "#3a2418", "#b8773f", "#f6ead9", "#fbf5ec"


# ---------------------------------------------------------------- vessels
def plate(base, cx, cy, rx, color="#fbfaf7", rim_color="#e7e1d7"):
    ry = rx * 0.27
    shadow(base, cx, cy + ry * 0.35, rx * 1.02, ry * 1.1, 0.25, 36)
    paint(base, ellipse_mask(cx, cy, rx, ry), rim_color)
    paint(base, ellipse_mask(cx, cy - ry * 0.06, rx * 0.98, ry * 0.92), color)
    paint(base, ellipse_mask(cx, cy, rx * 0.66, ry * 0.62), mix(color, rim_color, 0.45))
    paint(base, ellipse_mask(cx, cy - ry * 0.04, rx * 0.63, ry * 0.57), color)


def cup(base, *, top_y, bot_y, top_rx, bot_rx, body=CERAMIC, liquid=None, surface=None, saucer=True, handle=True, curve=1.4, mug=False):
    rim = 0.26
    if saucer:
        plate(base, CX, bot_y + 30, top_rx * 1.55)
    else:
        shadow(base, CX, bot_y + 25, bot_rx * 1.25, bot_rx * 0.3, 0.3, 30)
    if handle:
        hy = top_y + (bot_y - top_y) * (0.42 if not mug else 0.45)
        hx = CX + vessel_rx_at(hy, top_y, bot_y, top_rx, bot_rx, curve) + (40 if not mug else 60)
        hrx, hry = (130, 150) if not mug else (150, 200)
        ring(base, hx, hy, hrx, hry, body[1], 64 if not mug else 76)
        ring(base, hx - 6, hy - 6, hrx - 6, hry - 6, body[0], 40 if not mug else 50)
    m = vessel_mask(CX, top_y, bot_y, top_rx, bot_rx, curve, rim)
    box = (CX - top_rx, top_y, CX + top_rx, bot_y)
    paint_gradient(base, m, body[0], body[1], box, "h")
    shade(base, m, box, "#000000", 0.0, 0.14, "h")
    # glossy highlight
    hl = poly_mask([(CX - top_rx * 0.72, top_y + 60), (CX - top_rx * 0.55, top_y + 60), (CX - bot_rx * 0.62, bot_y - 50), (CX - bot_rx * 0.78, bot_y - 60)])
    paint(base, blur(hl, 18), "#ffffff", 0.55)
    # rim + interior
    paint(base, ellipse_mask(CX, top_y, top_rx, top_rx * rim), mix(body[1], "#ffffff", 0.3))
    inner_rx = top_rx - 26
    paint(base, ellipse_mask(CX, top_y + 4, inner_rx, inner_rx * rim), mix(body[1], "#000000", 0.08))
    if liquid:
        lrx = inner_rx - 18
        paint(base, ellipse_mask(CX, top_y + 18, lrx, lrx * rim * 0.95), liquid)
        if surface:
            surface(base, CX, top_y + 18, lrx, lrx * rim * 0.95)
    return m


def glass(base, *, top_y, bot_y, top_rx, bot_rx, fill_y, liquid_top, liquid_bottom, ice=0, straw=None, garnish=None, curve=1.0, layers=None):
    rim = 0.24
    shadow(base, CX, bot_y + 18, bot_rx * 1.3, bot_rx * 0.3, 0.26, 30)
    body = vessel_mask(CX, top_y, bot_y, top_rx, bot_rx, curve, rim)
    box = (CX - top_rx, top_y, CX + top_rx, bot_y)
    paint(base, body, "#ffffff", 0.28)
    frx = vessel_rx_at(fill_y, top_y, bot_y, top_rx, bot_rx, curve) - 14
    liquid = intersect(vessel_mask(CX, fill_y, bot_y - 22, frx, bot_rx - 16, curve, rim), body)
    paint_gradient(base, liquid, liquid_top, liquid_bottom, (0, fill_y, S, bot_y), "v")
    shade(base, liquid, box, "#000000", 0.0, 0.18, "h")
    paint(base, ellipse_mask(CX, fill_y, frx, frx * rim), mix(liquid_top, "#ffffff", 0.18))
    if ice:
        rnd = random.Random(ice)
        for i in range(ice):
            size = rnd.uniform(150, 200)
            x = CX + rnd.uniform(-frx * 0.55, frx * 0.55)
            y = fill_y + rnd.uniform(-40, 260) + i * 40
            cube = intersect(rounded_rect_mask(x - size / 2, y - size / 2, x + size / 2, y + size / 2, 36, rnd.uniform(-25, 25)), body)
            paint(base, cube, "#ffffff", 0.42)
            edge = subtract(cube, rounded_rect_mask(x - size / 2 + 22, y - size / 2 + 22, x + size / 2 - 10, y + size / 2 - 10, 26))
            paint(base, edge, "#ffffff", 0.5)
    if layers:
        layers(base, liquid)
    if garnish:
        garnish(base)
    if straw:
        color, stripe = straw
        sm = rounded_rect_mask(CX + 40, top_y - 420, CX + 100, fill_y + 400, 30, -12, (CX + 70, top_y))
        paint(base, sm, color)
        if stripe:
            for k in range(8):
                y0 = top_y - 400 + k * 110
                band = intersect(sm, poly_mask([(0, y0), (S, y0 - 60), (S, y0 - 20), (0, y0 + 40)]))
                paint(base, band, stripe)
        shade(base, sm, (CX + 40, 0, CX + 110, S), "#000000", 0.0, 0.25, "h")
    # glass edges + highlight
    edge = subtract(body, vessel_mask(CX, top_y + 8, bot_y - 14, top_rx - 18, bot_rx - 18, curve, rim))
    paint(base, edge, "#ffffff", 0.75)
    ring(base, CX, top_y, top_rx, top_rx * rim, "#ffffff", 14, 0.9)
    hl = poly_mask([(CX - top_rx * 0.78, top_y + 80), (CX - top_rx * 0.66, top_y + 80), (CX - bot_rx * 0.64, bot_y - 80), (CX - bot_rx * 0.74, bot_y - 80)])
    paint(base, blur(hl, 10), "#ffffff", 0.6)
    return body


def bowl(base, *, rim_y, rx, depth, color=("#ffffff", "#e6ded2"), accent=None):
    rim = 0.3
    shadow(base, CX, rim_y + depth + 10, rx * 0.8, rx * 0.2, 0.28, 34)
    body = union(poly_mask([(CX - rx, rim_y)] + [(CX + rx * math.cos(a), rim_y + depth * math.sin(a)) for a in [math.pi * k / 60 for k in range(60, -1, -1)]] + [(CX + rx, rim_y)]),
                 ellipse_mask(CX, rim_y, rx, rx * rim))
    paint_gradient(base, body, color[0], color[1], (CX - rx, 0, CX + rx, S), "h")
    shade(base, body, (0, rim_y, S, rim_y + depth), "#000000", 0.0, 0.12, "v")
    if accent:
        band = intersect(body, poly_mask([(0, rim_y + depth * 0.18), (S, rim_y + depth * 0.18), (S, rim_y + depth * 0.3), (0, rim_y + depth * 0.3)]))
        paint(base, band, accent)
    paint(base, blur(poly_mask([(CX - rx * 0.8, rim_y + 60), (CX - rx * 0.68, rim_y + 60), (CX - rx * 0.45, rim_y + depth * 0.75), (CX - rx * 0.58, rim_y + depth * 0.7)]), 16), "#ffffff", 0.5)
    paint(base, ellipse_mask(CX, rim_y, rx, rx * rim), mix(color[1], "#ffffff", 0.4))
    return rx - 30, rx * rim - 12


# ------------------------------------------------------------ latte art
def heart(base, cx, cy, rx, ry, color=MILK, scale=0.52):
    m = blank_mask(); d = ImageDraw.Draw(m)
    w, h = rx * scale, ry * scale * 1.1
    d.ellipse((cx - w * 1.0, cy - h * 0.9, cx + w * 0.08, cy + h * 0.3), fill=255)
    d.ellipse((cx - w * 0.08, cy - h * 0.9, cx + w * 1.0, cy + h * 0.3), fill=255)
    d.polygon([(cx - w * 0.97, cy - h * 0.15), (cx + w * 0.97, cy - h * 0.15), (cx, cy + h * 1.15)], fill=255)
    paint(base, blur(m, 6), color)


def rosetta(base, cx, cy, rx, ry):
    for i, s in enumerate([0.74, 0.62, 0.5, 0.39, 0.29]):
        y = cy - ry * 0.55 + i * ry * 0.26
        paint(base, blur(ellipse_mask(cx, y, rx * s, ry * s * 0.62), 5), MILK)
        paint(base, blur(ellipse_mask(cx, y + ry * 0.06, rx * s * 0.82, ry * s * 0.42), 5), CREMA, 0.9)
    paint(base, blur(ellipse_mask(cx, cy + ry * 0.6, rx * 0.2, ry * 0.2), 4), MILK)
    stroke(base, [(cx, cy - ry * 0.75), (cx, cy + ry * 0.75)], CREMA, 14)


def crema_surface(base, cx, cy, rx, ry):
    paint(base, blur(ellipse_mask(cx, cy, rx * 0.98, ry * 0.95), 10), CREMA)
    paint(base, blur(ellipse_mask(cx - rx * 0.1, cy - ry * 0.1, rx * 0.6, ry * 0.5), 26), "#d4955a", 0.8)


# -------------------------------------------------------------- drinks
def art_brewed_coffee(base):
    steam(base, CX, 900)
    cup(base, top_y=1000, bot_y=1720, top_rx=330, bot_rx=300, body=("#5f7a68", "#3f5647"), liquid=ESPRESSO, saucer=False, mug=True, curve=1.0,
        surface=lambda b, x, y, rx, ry: paint(b, blur(ellipse_mask(x - rx * 0.2, y - ry * 0.2, rx * 0.5, ry * 0.4), 20), "#6a4330", 0.9))


def art_espresso(base):
    steam(base, CX, 1080, count=2, height=300)
    cup(base, top_y=1250, bot_y=1640, top_rx=250, bot_rx=170, liquid=ESPRESSO, surface=crema_surface, curve=1.6)
    for dx, dy, rot in ((-520, 1790, 30), (560, 1760, -20)):
        bean = rounded_rect_mask(CX + dx - 48, dy - 32, CX + dx + 48, dy + 32, 32, rot)
        paint(base, bean, "#4a2c1d"); stroke(base, [(CX + dx - 30, dy + 8), (CX + dx + 30, dy - 8)], "#2b170e", 8)


def art_latte(base):
    cup(base, top_y=1080, bot_y=1650, top_rx=420, bot_rx=250, liquid=CREMA, curve=1.8,
        surface=lambda b, x, y, rx, ry: (paint(b, ellipse_mask(x, y, rx, ry), "#c58a52"), rosetta(b, x, y, rx, ry)))


def art_cappuccino(base):
    def foam(b, x, y, rx, ry):
        paint(b, blur(ellipse_mask(x, y - 10, rx, ry * 1.05), 6), FOAM)
        paint(b, blur(ellipse_mask(x, y - 12, rx * 0.72, ry * 0.7), 30), "#b98056", 0.55)
        speckles(b, ellipse_mask(x, y - 12, rx * 0.72, ry * 0.7), "#6e4128", 160, (4, 9), 7, 0.7)
        heart(b, x, y - 10, rx, ry, FOAM, 0.34)
    steam(base, CX, 900, count=2, height=260)
    cup(base, top_y=1100, bot_y=1650, top_rx=380, bot_rx=240, liquid=FOAM, surface=foam, curve=1.7, body=("#fbf7f1", "#e6d9c8"))


def art_iced_latte(base):
    glass(base, top_y=820, bot_y=1760, top_rx=330, bot_rx=270, fill_y=930, liquid_top="#efe1cc", liquid_bottom="#8a5634", ice=5, straw=("#e9e1d3", "#b5835a"))


def art_iced_coffee(base):
    glass(base, top_y=820, bot_y=1760, top_rx=330, bot_rx=270, fill_y=930, liquid_top="#6b3f24", liquid_bottom="#2d1a10", ice=5, straw=("#2f3b33", None))


def art_hot_tea(base):
    steam(base, CX - 40, 1000, count=2, height=300)
    cup(base, top_y=1150, bot_y=1650, top_rx=360, bot_rx=230, liquid="#b5652a", curve=1.8, body=("#fdfbf7", "#e5dccd"),
        surface=lambda b, x, y, rx, ry: paint(b, blur(ellipse_mask(x - rx * 0.2, y - ry * 0.2, rx * 0.55, ry * 0.45), 24), "#d98f4c", 0.8))
    stroke(base, [(CX + 120, 1180), (CX + 250, 1120), (CX + 400, 1210), (CX + 470, 1330)], "#f3efe6", 8)
    tag = rounded_rect_mask(CX + 420, 1330, CX + 540, 1470, 14, 8)
    paint(base, tag, "#e8b44d"); paint(base, rounded_rect_mask(CX + 445, 1360, CX + 515, 1440, 8, 8), "#f6d98f")
    lemon(base, CX - 470, 1760, 110, flat=True)


def lemon(base, cx, cy, r, flat=False, color="#f2c230", pith="#fbeea6"):
    ry = r * (0.35 if flat else 1)
    paint(base, ellipse_mask(cx, cy, r, ry), color)
    paint(base, ellipse_mask(cx, cy, r * 0.86, ry * 0.86), pith)
    for k in range(8):
        a = k * math.pi / 4
        seg = poly_mask([(cx, cy), (cx + r * 0.8 * math.cos(a + 0.33), cy + ry * 0.8 * math.sin(a + 0.33)), (cx + r * 0.8 * math.cos(a - 0.33), cy + ry * 0.8 * math.sin(a - 0.33))])
        paint(base, blur(seg, 3), mix(color, "#ffffff", 0.25))


def art_hot_chocolate(base):
    def cream(b, x, y, rx, ry):
        for i, (dy, s) in enumerate(((0, 1.0), (-70, 0.78), (-135, 0.56), (-190, 0.34))):
            paint(b, blur(ellipse_mask(x, y + dy - 30, rx * s, ry * s * 1.9), 4), "#fffaf3")
            shade(b, ellipse_mask(x, y + dy - 30, rx * s, ry * s * 1.9), (x - rx, 0, x + rx, S), "#b39b86", 0.0, 0.35, "h")
        speckles(b, ellipse_mask(x, y - 120, rx * 0.8, ry * 2.2), "#5a3423", 140, (5, 10), 3, 0.85)
        for mx, my in ((-150, -40), (140, -10), (30, 30)):
            paint(b, rounded_rect_mask(x + mx - 38, y + my - 30, x + mx + 38, y + my + 30, 14, 20), "#fdf1f4")
    cup(base, top_y=1150, bot_y=1760, top_rx=320, bot_rx=290, body=("#c9573f", "#9a3d2c"), liquid="#5b3322", surface=cream, saucer=False, mug=True, curve=1.0)


def art_iced_tea(base):
    def garnish(b):
        lemon(b, CX - 220, 1010, 150, flat=False)
        for dx, rot in ((150, 30), (230, -10)):
            paint(b, rounded_rect_mask(CX + dx - 40, 840, CX + dx + 40, 980, 40, rot), "#4f8a4b")
    glass(base, top_y=860, bot_y=1760, top_rx=320, bot_rx=260, fill_y=960, liquid_top="#d98a35", liquid_bottom="#8b3f15", ice=4, garnish=garnish)


def art_lemonade(base):
    def garnish(b):
        lemon(b, CX - 90, 1300, 120); lemon(b, CX + 120, 1480, 105)
        lemon(b, CX + 250, 860, 150)
    glass(base, top_y=860, bot_y=1760, top_rx=320, bot_rx=260, fill_y=960, liquid_top="#fbeaa0", liquid_bottom="#f2cf55", ice=3, straw=("#f6f1e3", "#e0a22c"), garnish=garnish)


def art_smoothie(base):
    def garnish(b):
        for x, y, r, c in ((CX - 150, 900, 70, "#b32645"), (CX - 40, 870, 60, "#3a2d6b"), (CX + 70, 905, 64, "#b32645")):
            paint(b, ellipse_mask(x, y, r, r), c); paint(b, ellipse_mask(x - r * 0.3, y - r * 0.3, r * 0.25, r * 0.2), "#ffffff", 0.6)
    glass(base, top_y=860, bot_y=1760, top_rx=320, bot_rx=240, fill_y=920, liquid_top="#e17aa0", liquid_bottom="#a8336a", straw=("#f4e7ee", "#c9477a"), garnish=garnish, curve=1.2)


# ------------------------------------------------------------- bakery
def croissant(base, cx, cy, scale=1.0, color=("#f2b866", "#b0632a")):
    """Crescent body (outer ellipse minus offset ellipse) with layered ridges."""
    rx, ry = 560 * scale, 300 * scale
    outer = ellipse_mask(cx, cy, rx, ry)
    inner = ellipse_mask(cx, cy + 330 * scale, rx * 0.5, ry * 0.8)
    body = subtract(outer, inner)
    body = blur(body, int(30 * scale)).point(lambda v: 255 if v > 128 else 0)
    shadow(base, cx, cy + ry * 0.7, rx * 0.9, ry * 0.25, 0.3, 30)
    paint_gradient(base, body, color[0], color[1], (0, cy - ry, S, cy + ry), "v")
    shade(base, body, (cx - rx, 0, cx + rx, S), "#6b3514", 0.25, 0.0, "h")
    shade(base, body, (cx - rx, 0, cx + rx, S), "#6b3514", 0.0, 0.25, "h")
    for k in range(-4, 5):
        ang = math.pi / 2 + k * 0.3
        x0 = cx + rx * 1.05 * math.cos(ang - math.pi) * -1
        ox, oy = cx - rx * math.cos(ang) * 1.02, cy - ry * math.sin(ang) * 1.02
        ix, iy = cx - rx * 0.5 * math.cos(ang) * 0.95, cy + 330 * scale - ry * 0.8 * math.sin(ang) * 0.95
        mx, my = (ox + ix) / 2 + 30 * scale * (1 if k > 0 else -1 if k < 0 else 0), (oy + iy) / 2
        line = blank_mask(); ImageDraw.Draw(line).line([(ox, oy), (mx, my), (ix, iy)], fill=255, width=int(20 * scale), joint="curve")
        paint(base, intersect(blur(line, 6), body), "#7e3f16", 0.55)
        hl = blank_mask(); ImageDraw.Draw(hl).line([(ox + 26 * scale, oy + 10), (mx + 24 * scale, my)], fill=255, width=int(24 * scale))
        paint(base, intersect(blur(hl, 10), body), "#ffe2a6", 0.55)
    paint(base, intersect(blur(ellipse_mask(cx - rx * 0.15, cy - ry * 0.62, rx * 0.45, ry * 0.18), 26), body), "#fff0c9", 0.6)


def art_plain_croissant(base):
    plate(base, CX, 1580, 720)
    croissant(base, CX, 1420)


def art_filled_croissant_danish(base):
    plate(base, CX, 1570, 700)
    for dx, dy, s in ((-260, 1330, 0.95), (280, 1400, 1.0)):
        r = 250 * s
        paint_gradient(base, ellipse_mask(CX + dx, dy, r, r * 0.62), "#efb462", "#b86b2c", (0, dy - r, S, dy + r), "v")
        for k in range(3):
            ring(base, CX + dx, dy, r * (0.85 - k * 0.22), r * 0.62 * (0.85 - k * 0.22), "#a45e27", 10, 0.6)
        paint(base, ellipse_mask(CX + dx, dy - 10, r * 0.4, r * 0.25), "#b52a3a" if dx < 0 else "#e7a72c")
        paint(base, ellipse_mask(CX + dx - r * 0.12, dy - 24, r * 0.14, r * 0.07), "#ffffff", 0.5)
        for k in range(4):
            y = dy - r * 0.4 + k * r * 0.22
            stroke(base, [(CX + dx - r * 0.7, y), (CX + dx - r * 0.2, y + 30), (CX + dx + r * 0.3, y - 10), (CX + dx + r * 0.7, y + 20)], "#fff8ec", 14, 0.9)


def art_muffin(base):
    shadow(base, CX, 1760, 330, 70, 0.3, 30)
    wrap = poly_mask([(CX - 330, 1230), (CX + 330, 1230), (CX + 250, 1760), (CX - 250, 1760)])
    paint_gradient(base, wrap, "#9fb7c9", "#6c8ba3", (CX - 330, 0, CX + 330, S), "h")
    for k in range(-6, 7):
        stroke(base, [(CX + k * 52, 1240), (CX + k * 40, 1750)], "#58748b", 8, 0.55)
    top = union(ellipse_mask(CX, 1210, 400, 220), ellipse_mask(CX - 230, 1150, 170, 150), ellipse_mask(CX + 220, 1140, 180, 160), ellipse_mask(CX, 1060, 260, 190))
    paint_gradient(base, top, "#e6a55a", "#a8612b", (0, 900, S, 1400), "v")
    paint(base, blur(ellipse_mask(CX - 90, 1030, 220, 90), 30), "#fbd497", 0.6)
    rnd = random.Random(11)
    for _ in range(14):
        x, y = CX + rnd.uniform(-330, 330), 1000 + rnd.uniform(0, 330)
        if top.getpixel((int(x), int(y))) > 200:
            r = rnd.uniform(26, 40)
            paint(base, ellipse_mask(x, y, r, r * 0.9), "#3e3a73"); paint(base, ellipse_mask(x - r * 0.3, y - r * 0.3, r * 0.3, r * 0.25), "#9c9ad6", 0.8)


def cookie(base, cx, cy, r, seed):
    shadow(base, cx, cy + r * 0.2, r * 1.02, r * 0.4, 0.25, 26)
    m = ellipse_mask(cx, cy, r, r * 0.42)
    side = union(m, ellipse_mask(cx, cy + 36, r, r * 0.42))
    paint(base, side, "#a86a2f")
    paint_gradient(base, m, "#e9b471", "#c98642", (cx - r, 0, cx + r, S), "h")
    rnd = random.Random(seed)
    for _ in range(9):
        x, y = cx + rnd.uniform(-r * 0.7, r * 0.7), cy + rnd.uniform(-r * 0.28, r * 0.28)
        if m.getpixel((int(x), int(y))) > 200:
            w = rnd.uniform(30, 52)
            pts = [(x + w * math.cos(a) * rnd.uniform(0.7, 1.2), y + w * 0.6 * math.sin(a) * rnd.uniform(0.7, 1.2)) for a in [k * math.pi / 3 for k in range(6)]]
            paint(base, poly_mask(pts), "#4a2616")
    speckles(base, m, "#b37436", 60, (4, 8), seed + 1, 0.8)


def art_cookie(base):
    cookie(base, CX - 60, 1560, 440, 4)
    cookie(base, CX + 40, 1330, 420, 5)
    cookie(base, CX - 20, 1110, 400, 6)


def art_donut(base):
    plate(base, CX, 1560, 720)
    for dx, dy, glaze in ((-60, 1400, "#f19bb4"), (120, 1180, "#6b3b2a")):
        body = subtract(ellipse_mask(CX + dx, dy, 380, 190), ellipse_mask(CX + dx, dy - 10, 110, 50))
        side = subtract(ellipse_mask(CX + dx, dy + 50, 380, 190), ellipse_mask(CX + dx, dy - 10, 110, 50))
        paint(base, union(side, body), "#c98845")
        pts = [(CX + dx + 330 * math.cos(a) + 14 * math.sin(a * 7), dy - 8 + 160 * math.sin(a) + 12 * math.cos(a * 9)) for a in [k * math.pi / 60 for k in range(120)]]
        g = subtract(poly_mask(pts), ellipse_mask(CX + dx, dy - 12, 135, 64))
        paint(base, g, glaze)
        paint(base, blur(intersect(g, ellipse_mask(CX + dx - 110, dy - 90, 170, 50)), 12), "#ffffff", 0.45)
        if dx < 0:
            rnd = random.Random(9)
            for _ in range(40):
                x, y = CX + dx + rnd.uniform(-300, 300), dy + rnd.uniform(-140, 140)
                if g.getpixel((int(x), int(y))) > 200:
                    paint(base, rounded_rect_mask(x - 20, y - 7, x + 20, y + 7, 7, rnd.uniform(0, 180)), rnd.choice(["#ffffff", "#f7d048", "#6cc3c9", "#7b5bd6"]))


def art_brownie(base):
    plate(base, CX, 1600, 700)
    for dx, dy in ((-210, 1450), (200, 1400), (0, 1180)):
        w, d, h = 300, 120, 170
        top = poly_mask([(CX + dx - w / 2, dy - h), (CX + dx + w / 2 - 60, dy - h - d / 2), (CX + dx + w / 2 + 40, dy - h + d / 3), (CX + dx - w / 2 + 100, dy - h + d)])
        front = poly_mask([(CX + dx - w / 2, dy - h), (CX + dx - w / 2 + 100, dy - h + d), (CX + dx - w / 2 + 100, dy + d), (CX + dx - w / 2, dy)])
        side = poly_mask([(CX + dx - w / 2 + 100, dy - h + d), (CX + dx + w / 2 + 40, dy - h + d / 3), (CX + dx + w / 2 + 40, dy + d / 3), (CX + dx - w / 2 + 100, dy + d)])
        paint(base, front, "#4b2a1a"); paint(base, side, "#3a2014"); paint(base, top, "#6a3d26")
        speckles(base, top, "#8d5a3b", 40, (5, 12), dx + 3, 0.9)
        speckles(base, union(front, side), "#2a150c", 50, (4, 9), dx + 5, 0.8)


def art_scone(base):
    plate(base, CX, 1580, 680)
    for dx, dy, flip in ((-200, 1420, 1), (230, 1330, -1)):
        pts = [(CX + dx - 260 * flip, dy + 60), (CX + dx + 230 * flip, dy - 20), (CX + dx + 20 * flip, dy - 250)]
        top = poly_mask(pts)
        top = blur(top, 26).point(lambda v: 255 if v > 110 else 0)
        side = poly_mask([(CX + dx - 260 * flip, dy + 60), (CX + dx + 230 * flip, dy - 20), (CX + dx + 230 * flip, dy + 120), (CX + dx - 260 * flip, dy + 190)])
        side = blur(side, 20).point(lambda v: 255 if v > 110 else 0)
        paint(base, side, "#c98a49"); paint_gradient(base, top, "#f2c689", "#d69a55", (0, dy - 250, S, dy + 60), "v")
        speckles(base, union(top, side), "#5d2a52", 12, (14, 22), dx, 1.0)


def art_loaf_slice(base):
    plate(base, CX, 1580, 680)
    for dx, dy in ((-150, 1440), (150, 1340)):
        crust = union(rounded_rect_mask(CX + dx - 250, dy - 260, CX + dx + 250, dy + 120, 50), ellipse_mask(CX + dx, dy - 250, 262, 130))
        crumb = union(rounded_rect_mask(CX + dx - 222, dy - 240, CX + dx + 222, dy + 95, 40), ellipse_mask(CX + dx, dy - 242, 232, 104))
        side = crust.transform(crust.size, 0, (1, 0, -34, 0, 1, -18))
        paint(base, side, "#7a4320"); paint(base, crust, "#96552a")
        paint_gradient(base, crumb, "#dca56a", "#c38748", (0, dy - 340, S, dy + 95), "v")
        speckles(base, crumb, "#9a6232", 80, (5, 10), dx + 40, 0.7)
        speckles(base, crumb, "#6d3c1b", 14, (10, 16), dx + 41, 0.9)


# ------------------------------------------------------ breakfast & lunch
def art_breakfast_sandwich(base):
    plate(base, CX, 1620, 700)
    y = 1470
    paint_gradient(base, union(ellipse_mask(CX, y, 360, 110), ellipse_mask(CX, y + 60, 360, 110)), "#e6bb7d", "#b87d3f", (0, y - 110, S, y + 170), "v")
    paint(base, ellipse_mask(CX - 20, y - 60, 380, 110), "#f7f1e3")
    paint(base, ellipse_mask(CX - 20, y - 70, 170, 70), "#f4b632")
    paint(base, poly_mask([(CX - 300, y - 150), (CX + 320, y - 120), (CX + 360, y - 40), (CX + 380, y + 20), (CX - 340, y - 40)]), "#f29d2a")
    paint(base, ellipse_mask(CX + 10, y - 170, 350, 100), "#b45a3c")
    dome = union(ellipse_mask(CX, y - 270, 370, 180), poly_mask([(CX - 370, y - 270), (CX + 370, y - 270), (CX + 360, y - 200), (CX - 360, y - 200)]), ellipse_mask(CX, y - 200, 360, 70))
    dome = subtract(dome, poly_mask([(0, 0), (S, 0), (S, y - 420), (0, y - 420)])) if False else dome
    paint_gradient(base, dome, "#edc488", "#c08545", (0, y - 450, S, y - 150), "v")
    paint(base, blur(ellipse_mask(CX - 90, y - 360, 200, 60), 20), "#fff1d0", 0.7)
    speckles(base, ellipse_mask(CX, y - 290, 330, 140), "#f7e8c9", 70, (5, 9), 21, 0.9)


def art_deli_sandwich(base):
    plate(base, CX, 1620, 720)
    for dx, dy, flip in ((200, 1500, -1), (-190, 1640, 1)):
        shadow(base, CX + dx, dy + 30, 300, 60, 0.3, 24)
        tip_x = CX + dx + 300 * flip
        layers = [("#e9c58f", 70), ("#6fae4a", 34), ("#e25b4a", 34), ("#f2cf5a", 26), ("#eaa3a0", 44), ("#6fae4a", 30), ("#e9c58f", 70)]
        y = dy
        for color, th in layers:
            m = poly_mask([(CX + dx - 280 * flip, y - th), (tip_x, y - th + 40), (tip_x, y + 40), (CX + dx - 280 * flip, y)])
            if color == "#6fae4a":
                pts = [(CX + dx - 300 * flip + k * 30 * flip, y - th + (18 if k % 2 else -6)) for k in range(21)]
                m = union(m, poly_mask(pts + [(tip_x, y + 40), (CX + dx - 300 * flip, y)]))
            paint(base, m, color)
            y -= th
        crust = poly_mask([(CX + dx - 290 * flip, y), (CX + dx - 280 * flip, y - 30), (tip_x + 10 * flip, y + 10), (tip_x, y + 40)])
        paint(base, crust, "#b77a3a")


def art_wrap(base):
    plate(base, CX, 1620, 720)
    for dx, dy, rot in ((210, 1500, -24), (-210, 1570, 24)):
        shadow(base, CX + dx, dy + 150, 200, 50, 0.3, 24)
        tube = rounded_rect_mask(CX + dx - 150, dy - 330, CX + dx + 150, dy + 150, 140, rot, (CX + dx, dy))
        paint_gradient(base, tube, "#f4dfb3", "#d9b97c", (CX + dx - 160, 0, CX + dx + 160, S), "h")
        speckles(base, tube, "#c49a58", 30, (6, 12), dx, 0.8)
        top = ellipse_mask(CX + dx, dy - 300, 150, 95).rotate(rot, center=(CX + dx, dy))
        paint(base, top, "#f7ecd2")
        for i, (color, s) in enumerate((("#6aa84f", 0.86), ("#f3f0e6", 0.68), ("#e0584a", 0.5), ("#e9c07c", 0.34))):
            paint(base, ellipse_mask(CX + dx + (i % 2) * 10, dy - 300, 150 * s, 95 * s).rotate(rot, center=(CX + dx, dy)), color)


def art_creamy_soup(base):
    rx, ry = bowl(base, rim_y=1230, rx=520, depth=430, color=("#fbfaf6", "#e2dace"), accent="#5f7a68")
    paint(base, ellipse_mask(CX, 1240, rx, ry), "#e0843c")
    paint(base, blur(ellipse_mask(CX - 60, 1225, rx * 0.6, ry * 0.5), 30), "#f0a45b", 0.8)
    stroke(base, [(CX - 160, 1230), (CX - 40, 1200), (CX + 90, 1250), (CX + 200, 1215)], "#fbf1e2", 22, 0.95)
    speckles(base, ellipse_mask(CX + 60, 1225, 140, 40), "#3f7a3a", 18, (8, 14), 5, 1.0)
    bread = rounded_rect_mask(CX + 330, 1560, CX + 700, 1780, 60, -12)
    paint(base, bread, "#c98b4a"); paint(base, rounded_rect_mask(CX + 350, 1580, CX + 680, 1760, 50, -12), "#efd3a0")


def art_green_salad(base):
    rx, ry = bowl(base, rim_y=1280, rx=540, depth=380, color=("#fdfcf9", "#e3dccf"))
    rnd = random.Random(14)
    mound = ellipse_mask(CX, 1180, rx * 0.95, 240)
    for _ in range(46):
        x, y = CX + rnd.uniform(-rx * 0.85, rx * 0.85), 1100 + rnd.uniform(-110, 190)
        if mound.getpixel((int(x), int(y))) < 200:
            continue
        leaf = ellipse_mask(x, y, rnd.uniform(90, 140), rnd.uniform(45, 70)).rotate(rnd.uniform(0, 180), center=(x, y))
        paint(base, leaf, rnd.choice(["#5f9e45", "#7dbb55", "#4b8a3a", "#9bcf6b"]))
        paint(base, blur(leaf, 2).point(lambda v: 255 if 60 < v < 200 else 0), "#3d6e2e", 0.5)
    for x, y in ((CX - 220, 1080), (CX + 180, 1130), (CX + 20, 1000)):
        paint(base, ellipse_mask(x, y, 62, 58), "#d83b32"); paint(base, ellipse_mask(x - 18, y - 18, 16, 12), "#ffffff", 0.6)
    for x, y in ((CX - 60, 1160), (CX + 280, 1030)):
        paint(base, ellipse_mask(x, y, 70, 40), "#cfe6a8"); ring(base, x, y, 70, 40, "#4f8a3a", 10)


def art_toast(base):
    board = rounded_rect_mask(CX - 700, 1360, CX + 700, 1760, 80)
    shadow(base, CX, 1760, 700, 80, 0.25, 30)
    paint_gradient(base, board, "#d6a56c", "#a8733f", (0, 1360, S, 1760), "v")
    for dx, dy in ((-280, 1340), (300, 1300)):
        crust = union(rounded_rect_mask(CX + dx - 280, dy - 250, CX + dx + 280, dy + 170, 60), ellipse_mask(CX + dx - 150, dy - 250, 150, 90), ellipse_mask(CX + dx + 150, dy - 250, 150, 90))
        crumb = union(rounded_rect_mask(CX + dx - 250, dy - 225, CX + dx + 250, dy + 145, 50), ellipse_mask(CX + dx - 140, dy - 240, 125, 70), ellipse_mask(CX + dx + 140, dy - 240, 125, 70))
        paint(base, crust, "#b87534"); paint(base, crumb, "#e8c28a")
        avo = blur(ellipse_mask(CX + dx, dy - 50, 220, 160), 20).point(lambda v: 255 if v > 120 else 0)
        paint(base, avo, "#8fb54c"); paint(base, blur(ellipse_mask(CX + dx - 40, dy - 90, 140, 80), 20), "#b8d46e", 0.8)
        speckles(base, avo, "#c8352b", 30, (6, 10), dx, 1.0)


def art_yogurt_granola(base):
    def garnish(b):
        for x, y, r, c in ((CX - 120, 900, 60, "#b32645"), (CX + 30, 880, 55, "#3a2d6b"), (CX + 140, 905, 58, "#e8a93a")):
            paint(b, ellipse_mask(x, y, r, r * 0.9), c); paint(b, ellipse_mask(x - r * 0.3, y - r * 0.3, r * 0.25, r * 0.2), "#ffffff", 0.6)

    def layers(b, liquid):
        for y0, y1, color in ((1120, 1270, "#c98e4a"), (1270, 1380, "#b1284a"), (1560, 1740, "#c98e4a")):
            wave = [(x, y0 + 16 * math.sin(x / 90)) for x in range(0, S + 1, 40)] + [(S, y1), (0, y1)]
            band = intersect(liquid, poly_mask(wave))
            paint(b, band, color)
            if color == "#c98e4a":
                speckles(b, band, "#8a5a28", 70, (8, 14), y0, 0.9)
                speckles(b, band, "#e7bd7c", 50, (6, 10), y0 + 1, 0.9)
    glass(base, top_y=860, bot_y=1760, top_rx=320, bot_rx=250, fill_y=930, liquid_top="#fbf7ef", liquid_bottom="#f1e9da", garnish=garnish, curve=1.1, layers=layers)


# name -> (palette, painter)
ARTWORK = {
    "brewed-coffee": ("coffee", art_brewed_coffee),
    "espresso": ("coffee", art_espresso),
    "latte": ("coffee", art_latte),
    "cappuccino": ("coffee", art_cappuccino),
    "iced-latte": ("cold", art_iced_latte),
    "iced-coffee": ("cold", art_iced_coffee),
    "hot-tea": ("tea", art_hot_tea),
    "hot-chocolate": ("tea", art_hot_chocolate),
    "iced-tea": ("cold", art_iced_tea),
    "lemonade-fruit-cooler": ("cold", art_lemonade),
    "smoothie": ("cold", art_smoothie),
    "plain-croissant": ("bakery", art_plain_croissant),
    "filled-croissant-danish": ("bakery", art_filled_croissant_danish),
    "muffin": ("bakery", art_muffin),
    "cookie": ("bakery", art_cookie),
    "donut": ("sweet", art_donut),
    "brownie-dessert-square": ("sweet", art_brownie),
    "scone": ("bakery", art_scone),
    "loaf-slice": ("bakery", art_loaf_slice),
    "breakfast-sandwich": ("breakfast", art_breakfast_sandwich),
    "toast": ("breakfast", art_toast),
    "yogurt-granola": ("breakfast", art_yogurt_granola),
    "deli-sandwich": ("lunch", art_deli_sandwich),
    "wrap": ("lunch", art_wrap),
    "creamy-soup": ("lunch", art_creamy_soup),
    "green-salad": ("lunch", art_green_salad),
}


def render(key: str):
    palette, painter = ARTWORK[key]
    base = background(PALETTES[palette])
    painter(base)
    # frame the subject tighter so it reads well in small product cards
    return finish(base.crop(FRAME).resize((S, S), Image.Resampling.LANCZOS))


def main() -> None:
    parser = argparse.ArgumentParser()
    default_out = Path(__file__).resolve().parents[1] / "app" / "platform" / "starter-media"
    parser.add_argument("--out", default=str(default_out))
    parser.add_argument("--only", default="")
    parser.add_argument("--version", type=int, default=1)
    args = parser.parse_args()
    keys = [k for k in args.only.split(",") if k] or list(ARTWORK)
    out = Path(args.out) / "cafe-restaurant"
    out.mkdir(parents=True, exist_ok=True)
    for key in keys:
        image = render(key)
        image.save(out / f"{key}-v{args.version}.webp", "WEBP", quality=84, method=6)
        print("wrote", out / f"{key}-v{args.version}.webp")


if __name__ == "__main__":
    main()
