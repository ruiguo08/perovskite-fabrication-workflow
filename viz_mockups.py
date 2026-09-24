"""Mockup renderings for data-visualization discussion (throwaway).

Uses the real 20260916.csv (GBK) via the app's parser-with-label-fix
transform, then renders figures with Pillow (no matplotlib installed).
"""
import re
import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from PIL import Image, ImageDraw, ImageFont

from web.jv_parser import parse_jv_analysis

RAW = Path(r"docs/test-data/20260916.csv")
OUT = Path(r"docs/test-data/viz-mockups")
OUT.mkdir(parents=True, exist_ok=True)

# ---- load & label-fix real data (same transform as before) ----
data = RAW.read_bytes().decode("gb18030")


def fix(m):
    g, s, d = m.group(1), int(m.group(2)), m.group(3)
    return f"20260915 (B{s:03d}-{g}-{s}-{d}.Channel{d}.CH_Ref"


text = re.sub(r"20260915 \(((?:Control\d|T\d))-(\d+)-(\d+)\.CH_Ref", fix, data)
analysis = parse_jv_analysis(text)
devices = analysis["devices"]

# parse group/substrate/device from labels: 20260915 (B001-Control1-1-1.Channel1)
# -> group key like "Control1" / "T1" / "T2" / "T3", substrate ordinal, device ordinal
DEV = []
for d in devices:
    m = re.search(r"\(([A-Z])(\d{3})-((?:Control\d|T\d))-(\d+)-(\d+)\.Channel(\d+)", d["label"])
    mark, group, sub, dev = m.group(1)+m.group(2), m.group(3), int(m.group(4)), int(m.group(5))
    if d["metrics"]:
        DEV.append(dict(
            id=d["device_id"], group=group, mark=mark, substrate=sub, pos=dev,
            voc=d["metrics"]["voc"], jsc=d["metrics"]["jsc"],
            ff=d["metrics"]["ff"], pce=d["metrics"]["pce"],
            traces=d["traces"],
        ))

print(f"parsed {len(DEV)} devices, groups: {sorted(set(x['group'] for x in DEV))}")

FONT = ImageFont.load_default(size=14)
FONT_S = ImageFont.load_default(size=11)
FONT_T = ImageFont.load_default(size=18)


def draw_text(dr, xy, s, font=FONT, fill=(30, 30, 30), anchor="la"):
    dr.text(xy, s, font=font, fill=fill, anchor=anchor)


# ============ FIGURE 1: substrate uniformity map (2x3 heat blocks) ============
def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def cmap_pce(v, vmin, vmax):
    """green=high, red=low diverging-ish map."""
    t = 0.5 if vmax == vmin else max(0.0, min(1.0, (v - vmin) / (vmax - vmin)))
    # red -> yellow -> green
    if t < 0.5:
        return lerp((214, 69, 65), (245, 220, 90), t * 2)
    return lerp((245, 220, 90), (46, 160, 90), (t - 0.5) * 2)


def fig_substrate_map():
    pces = [x["pce"] for x in DEV]
    vmin, vmax = min(pces), max(pces)
    groups = sorted(set(x["group"] for x in DEV))
    subs = sorted(set((x["group"], x["substrate"]) for x in DEV))
    cols = 5
    rows = math.ceil(len(subs) / cols)
    CW, CH, PAD, TITLE = 190, 170, 14, 70
    W = cols * (CW + PAD) + PAD
    H = TITLE + rows * (CH + PAD) + 90
    img = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(img)
    draw_text(dr, (W // 2, 22), "Substrate uniformity map — PCE (%) per device (2×3 layout)",
              FONT_T, anchor="ma")
    # color bar
    bx0, bx1, by = W - 260, W - 40, 30
    for i in range(bx1 - bx0):
        c = cmap_pce(vmin + (vmax - vmin) * i / (bx1 - bx0), vmin, vmax)
        dr.line([(bx0 + i, by), (bx0 + i, by + 14)], fill=c)
    draw_text(dr, (bx0, by + 18), f"{vmin:.1f}", FONT_S, anchor="ma")
    draw_text(dr, (bx1, by + 18), f"{vmin:.1f}" if False else f"{vmax:.1f}", FONT_S, anchor="ma")

    for idx, (grp, sub) in enumerate(subs):
        gx, gy = idx % cols, idx // cols
        x0 = PAD + gx * (CW + PAD)
        y0 = TITLE + gy * (CH + PAD)
        cells = [x for x in DEV if x["group"] == grp and x["substrate"] == sub]
        draw_text(dr, (x0 + CW // 2, y0), f"{grp}-{sub}", FONT, anchor="ma")
        bw, bh, gap = CW // 3 - 8, (CH - 40) // 2 - 6, 4
        # layout: positions 1-3 top row L->R, 4-6 bottom row L->R
        for c in cells:
            p = c["pos"]
            row = 0 if p <= 3 else 1
            col = (p - 1) % 3
            cx = x0 + 6 + col * (bw + gap)
            cy = y0 + 26 + row * (bh + gap)
            color = cmap_pce(c["pce"], vmin, vmax)
            dr.rectangle([cx, cy, cx + bw, cy + bh], fill=color, outline=(90, 90, 90))
            draw_text(dr, (cx + bw / 2, cy + bh / 2 - 8), f"{c['pce']:.1f}", FONT_S, (20, 20, 20), "mm")
            draw_text(dr, (cx + bw / 2, cy + bh - 4), f"#{p}", FONT_S, (60, 60, 60), "ms")
    img.save(OUT / "fig1_substrate_map.png")


# ============ FIGURE 2: distribution — box vs strip+errorbar ============
def stats(vals):
    n = len(vals)
    mean = sum(vals) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1)) if n > 1 else 0.0
    srt = sorted(vals)
    q1 = srt[n // 4]
    med = srt[n // 2]
    q3 = srt[(3 * n) // 4]
    return mean, sd, med, q1, q3, srt[0], srt[-1]


def fig_distribution_compare():
    groups = sorted(set(x["group"] for x in DEV))
    gdata = {g: [x["pce"] for x in DEV if x["group"] == g] for g in groups}
    W, H = 1000, 560
    img = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(img)
    draw_text(dr, (W // 2, 18), "PCE distribution per group — box plot (left) vs strip + mean±SD (right)",
              FONT_T, anchor="ma")
    allv = [v for vs in gdata.values() for v in vs]
    lo, hi = math.floor(min(allv)) - 1, math.ceil(max(allv)) + 1

    def panel(x0, x1, title, mode):
        top, bot = 70, H - 60
        y = lambda v: bot - (v - lo) / (hi - lo) * (bot - top)
        for gv in range(lo, hi + 1, 2):
            dr.line([(x0, y(gv)), (x1, y(gv))], fill=(235, 235, 235))
            draw_text(dr, (x0 - 6, y(gv)), str(gv), FONT_S, (120, 120, 120), "rm")
        draw_text(dr, ((x0 + x1) // 2, 46), title, FONT, anchor="ma")
        n = len(groups)
        pw = (x1 - x0) / n
        for i, g in enumerate(groups):
            cx = x0 + pw * (i + 0.5)
            vals = gdata[g]
            mean, sd, med, q1, q3, mn, mx = stats(vals)
            if mode == "box":
                bw = 34
                dr.rectangle([cx - bw, y(q3), cx + bw, y(q1)], fill=(200, 220, 240), outline=(60, 90, 130))
                dr.line([(cx - bw, y(med)), (cx + bw, y(med))], fill=(200, 40, 40), width=2)
                dr.line([(cx, y(mx)), (cx, y(q3))], fill=(60, 90, 130))
                dr.line([(cx, y(q1)), (cx, y(mn))], fill=(60, 90, 130))
                dr.line([(cx - 10, y(mx)), (cx + 10, y(mx))], fill=(60, 90, 130))
                dr.line([(cx - 10, y(mn)), (cx + 10, y(mn))], fill=(60, 90, 130))
            else:
                dr.line([(cx, y(mean - sd)), (cx, y(mean + sd))], fill=(30, 30, 30), width=2)
                dr.line([(cx - 9, y(mean + sd)), (cx + 9, y(mean + sd))], fill=(30, 30, 30), width=2)
                dr.line([(cx - 9, y(mean - sd)), (cx + 9, y(mean - sd))], fill=(30, 30, 30), width=2)
                dr.line([(cx - 14, y(mean)), (cx + 14, y(mean))], fill=(200, 40, 40), width=3)
                import random as R
                rng = R.Random(hash(g) & 0xFFFF)
                for v in vals:
                    jx = cx + rng.uniform(-pw * 0.16, pw * 0.16)
                    dr.ellipse([jx - 3.2, y(v) - 3.2, jx + 3.2, y(v) + 3.2],
                               fill=(46, 134, 193), outline=(255, 255, 255))
            draw_text(dr, (cx, bot + 12), g, FONT_S, anchor="ma")
            draw_text(dr, (cx, bot + 30), f"n={len(vals)}", FONT_S, (130, 130, 130), anchor="ma")

    panel(70, 520, "box plot (current)", "box")
    panel(560, 990, "strip + mean±SD (proposed)", "strip")
    img.save(OUT / "fig2_distribution_compare.png")


# ============ FIGURE 3: J-V overlay (few curves) ============
def fig_jv_overlay():
    # best device per group, forward+reverse
    groups = sorted(set(x["group"] for x in DEV))
    best = []
    for g in groups:
        cands = [x for x in DEV if x["group"] == g]
        best.append(max(cands, key=lambda x: x["pce"]))
    palette = [(41, 128, 185), (39, 174, 96), (211, 84, 0), (142, 68, 173),
               (192, 57, 43), (22, 160, 133), (243, 156, 18), (44, 62, 80)]
    W, H = 900, 560
    ml, mr, mt, mb = 90, 30, 56, 70
    img = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(img)
    draw_text(dr, (W // 2, 20), "J–V overlay — best device per group (solid=fwd, dashed=rev)",
              FONT_T, anchor="ma")
    pts = []
    for b in best:
        for t in b["traces"]:
            if t["valid"]:
                pts.extend([(p[0], p[1]) for p in t["points"]])
    xlo, xhi = 0.0, max(p[0] for p in pts) * 1.03
    ylo, yhi = 0.0, max(p[1] for p in pts) * 1.06
    X = lambda v: ml + (v - xlo) / (xhi - xlo) * (W - ml - mr)
    Y = lambda j: (H - mb) - (j - ylo) / (yhi - ylo) * (H - mt - mb)
    for i in range(6):
        xv = xlo + (xhi - xlo) * i / 5
        yv = ylo + (yhi - ylo) * i / 5
        dr.line([(X(xv), mt), (X(xv), H - mb)], fill=(240, 240, 240))
        dr.line([(ml, Y(yv)), (W - mr, Y(yv))], fill=(240, 240, 240))
        draw_text(dr, (X(xv), H - mb + 10), f"{xv:.2f}", FONT_S, (110, 110, 110), "ma")
        draw_text(dr, (ml - 8, Y(yv)), f"{yv:.0f}", FONT_S, (110, 110, 110), "rm")
    dr.line([(ml, mt), (ml, H - mb)], fill=(30, 30, 30))
    dr.line([(ml, H - mb), (W - mr, H - mb)], fill=(30, 30, 30))
    draw_text(dr, ((ml + W - mr) / 2, H - 24), "Voltage (V)", FONT, anchor="ma")
    draw_text(dr, (22, (mt + H - mb) / 2), "J (mA/cm²)", FONT, anchor="mm")

    for i, b in enumerate(best):
        col = palette[i % len(palette)]
        for t in b["traces"]:
            if not t["valid"]:
                continue
            pts2 = [(p[0], p[1]) for p in t["points"]]
            pts2.sort()
            if t["direction"] == "forward":
                dr.line([(X(v), Y(j)) for v, j in pts2], fill=col, width=2)
            else:
                # dashed reverse
                seg = [(X(v), Y(j)) for v, j in pts2]
                for k in range(0, len(seg) - 1, 6):
                    dr.line(seg[k:k + 5], fill=col, width=2)
        lx, ly = W - mr - 190, mt + 14 + i * 22
        dr.line([(lx, ly), (lx + 30, ly)], fill=col, width=3)
        draw_text(dr, (lx + 38, ly), f"{b['group']}  PCE={b['pce']:.1f}%", FONT_S, col, "lm")
    img.save(OUT / "fig3_jv_overlay.png")


fig_substrate_map()
fig_distribution_compare()
fig_jv_overlay()
print("saved to", OUT)
for p in sorted(OUT.glob("*.png")):
    print(" -", p)
