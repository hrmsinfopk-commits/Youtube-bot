"""Tomorrowly's own animated graphics (100% original, drawn in code): counters, bar comparisons, timelines,
the HYPE METER gauge, the TOMORROW TEST card, and the channel logo."""
import math
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .common import FONTS, log, run

BG_TOP, BG_BOT = (9, 13, 28), (17, 24, 39)
ACCENT = (34, 211, 238)      # Tomorrowly cyan
ACCENT2 = (251, 191, 36)     # amber
WHITE, GREY = (245, 247, 250), (148, 163, 184)
FPS_DRAW = 15


def _font(size, bold=True):
    for p in [FONTS / "Anton-Regular.ttf", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]:
        if p.exists() and (bold or "DejaVu" in str(p)):
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def _label_font(size):
    for p in [Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"), FONTS / "Anton-Regular.ttf"]:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def _ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _background(W, H):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(BG_TOP, BG_BOT)))
    step = max(40, W // 24)
    for x in range(0, W, step):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 10) if False else (22, 30, 48))
    for y in range(0, H, step):
        d.line([(0, y), (W, y)], fill=(22, 30, 48))
    return img


def logo(size=160):
    """Original channel mark: a 'T' inside a ring with an orbit arc and a small 'planet'."""
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([s * .06, s * .06, s * .94, s * .94], fill=(12, 18, 36, 235), outline=ACCENT + (255,), width=int(s * .045))
    d.arc([s * .14, s * .30, s * .86, s * .70], start=200, end=520, fill=ACCENT2 + (255,), width=int(s * .035))
    d.rectangle([s * .30, s * .30, s * .70, s * .40], fill=WHITE + (255,))
    d.rectangle([s * .45, s * .30, s * .55, s * .74], fill=WHITE + (255,))
    d.ellipse([s * .74, s * .55, s * .84, s * .65], fill=ACCENT2 + (255,))
    return img.resize((size, size), Image.LANCZOS)


def _center_text(d, cx, y, text, font, fill):
    w = d.textlength(text, font=font)
    d.text((cx - w / 2, y), text, font=font, fill=fill)


def _wrap(d, text, font, maxw):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fmt(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1e9:
        return f"{f / 1e9:.1f}B".replace(".0B", "B")
    if abs(f) >= 1e6:
        return f"{f / 1e6:.1f}M".replace(".0M", "M")
    if f == int(f):
        return f"{int(f):,}"
    return f"{f:,.1f}"


# ------------------------------------------------------------------ frame painters (t in seconds)
def _counter(g, W, H, t, short):
    img = _background(W, H)
    d = ImageDraw.Draw(img)
    cy = H * (0.30 if short else 0.40)
    try:
        val = float(g.get("value", 0))
        cur = val * _ease(t / 1.3)
        txt = f"{g.get('prefix', '')}{_fmt(round(cur) if val == int(val) else cur)}{g.get('suffix', '')}"
    except (TypeError, ValueError):
        txt = str(g.get("value", ""))
    f = _font(int(W * (0.19 if short else 0.13)))
    while d.textlength(txt, font=f) > W * 0.88 and f.size > 40:
        f = _font(f.size - 8)
    glow = Image.new("RGB", (W, H))
    ImageDraw.Draw(glow).text((W / 2 - d.textlength(txt, font=f) / 2, cy), txt, font=f, fill=ACCENT)
    img = Image.blend(img, Image.composite(glow, img, glow.convert("L")).filter(ImageFilter.GaussianBlur(18)), 0.5)
    d = ImageDraw.Draw(img)
    _center_text(d, W / 2, cy, txt, f, WHITE)
    lab = str(g.get("label", "")).upper()
    if lab:
        lf = _label_font(int(W * (0.045 if short else 0.03)))
        a = _ease((t - 0.6) / 0.6)
        _center_text(d, W / 2, cy + f.size * 1.25, lab, lf, tuple(int(c * a) for c in ACCENT))
    return img


def _bars(g, W, H, t, short):
    img = _background(W, H)
    d = ImageDraw.Draw(img)
    labels, values = list(g.get("labels", []))[:4], []
    for v in list(g.get("values", []))[:4]:
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            values.append(0.0)
    n = min(len(labels), len(values))
    if n == 0:
        return img
    top = H * (0.12 if short else 0.12)
    tf = _font(int(W * (0.07 if short else 0.05)))
    _center_text(d, W / 2, top, str(g.get("title", "")).upper(), tf, WHITE)
    area_top, area_bot = top + tf.size * 1.8, H * (0.56 if short else 0.78)
    lf, vf = _label_font(int(W * (0.042 if short else 0.026))), _font(int(W * (0.05 if short else 0.032)))
    left, right = W * 0.08, W * 0.92
    bh = (area_bot - area_top) / n
    mx = max(values[:n]) or 1
    for i in range(n):
        a = _ease((t - 0.25 * i) / 1.0)
        y = area_top + i * bh
        d.text((left, y), str(labels[i]), font=lf, fill=GREY)
        by = y + lf.size * 1.3
        full = (right - left) * values[i] / mx
        d.rounded_rectangle([left, by, right, by + bh * 0.38], radius=12, fill=(30, 41, 59))
        if full * a > 4:
            d.rounded_rectangle([left, by, left + full * a, by + bh * 0.38], radius=12,
                                fill=ACCENT if i % 2 == 0 else ACCENT2)
        if a > 0.2:
            vt = f"{_fmt(values[i] * a)} {g.get('unit', '')}".strip()
            ty = by + bh * 0.38 * 0.5 - vf.size * 0.6
            if d.textlength(vt, font=vf) + 28 < full * a:      # fits inside the bar
                d.text((left + 14, ty), vt, font=vf, fill=(9, 13, 28))
            else:                                               # short bar: write it next to the bar
                d.text((left + full * a + 14, ty), vt, font=vf, fill=WHITE)
    return img


def _timeline(g, W, H, t, short):
    img = _background(W, H)
    d = ImageDraw.Draw(img)
    items = list(g.get("items", []))[:4]
    if not items:
        return img
    yf, xf = _font(int(W * (0.07 if short else 0.045))), _label_font(int(W * (0.036 if short else 0.022)))
    if short:   # vertical timeline (top part of the frame, captions stay readable below)
        x, y0, y1 = W * 0.18, H * 0.10, H * 0.56
        d.line([(x, y0), (x, y0 + (y1 - y0) * _ease(t / 1.0))], fill=GREY, width=6)
        for i, it in enumerate(items):
            a = _ease((t - 0.4 - 0.45 * i) / 0.5)
            if a <= 0:
                continue
            y = y0 + (y1 - y0) * (i + 0.5) / len(items)
            r = 18
            d.ellipse([x - r, y - r, x + r, y + r], fill=ACCENT if i < len(items) - 1 else ACCENT2)
            d.text((x + 50, y - yf.size * 0.8), str(it.get("year", "")), font=yf, fill=tuple(int(c * a) for c in WHITE))
            for k, ln in enumerate(_wrap(d, it.get("text", ""), xf, W * 0.6)[:2]):
                d.text((x + 50, y + yf.size * 0.35 + k * xf.size * 1.2), ln, font=xf, fill=tuple(int(c * a) for c in GREY))
    else:
        y, x0, x1 = H * 0.42, W * 0.08, W * 0.92
        d.line([(x0, y), (x0 + (x1 - x0) * _ease(t / 1.0), y)], fill=GREY, width=6)
        for i, it in enumerate(items):
            a = _ease((t - 0.4 - 0.45 * i) / 0.5)
            if a <= 0:
                continue
            x = x0 + (x1 - x0) * (i + 0.5) / len(items)
            r = 16
            d.ellipse([x - r, y - r, x + r, y + r], fill=ACCENT if i < len(items) - 1 else ACCENT2)
            _center_text(d, x, y - yf.size * 1.6, str(it.get("year", "")), yf, tuple(int(c * a) for c in WHITE))
            for k, ln in enumerate(_wrap(d, it.get("text", ""), xf, (x1 - x0) / len(items) * 0.9)[:3]):
                _center_text(d, x, y + 34 + k * xf.size * 1.2, ln, xf, tuple(int(c * a) for c in GREY))
    return img


VERDICT = {1: "PURE HYPE", 2: "PURE HYPE", 3: "MOSTLY HYPE", 4: "PROMISING, BUT...", 5: "PROMISING, BUT...",
           6: "GETTING REAL", 7: "REAL & CLOSE", 8: "REAL & CLOSE", 9: "ALMOST HERE", 10: "ALREADY HERE"}


def _hype_meter(g, W, H, t, short):
    img = _background(W, H)
    d = ImageDraw.Draw(img)
    try:
        val = max(1, min(10, int(round(float(g.get("value", 5))))))
    except (TypeError, ValueError):
        val = 5
    tf = _font(int(W * (0.09 if short else 0.055)))
    cy = H * (0.36 if short else 0.50)      # keep the verdict above the captions
    _center_text(d, W / 2, H * (0.08 if short else 0.08), "HYPE METER", tf, WHITE)
    R = W * (0.36 if short else 0.18)
    cx = W / 2
    for i in range(10):   # 10 coloured segments from red (hype) to green (real)
        a0, a1 = 180 + i * 18 + 1, 180 + (i + 1) * 18 - 1
        col = (int(239 - 200 * i / 9), int(68 + 130 * i / 9), int(68 + 30 * i / 9))
        d.arc([cx - R, cy - R, cx + R, cy + R], start=a0, end=a1, fill=col, width=int(R * 0.18))
    cur = 1 + (val - 1) * _ease(t / 1.6)
    ang = math.radians(180 + (cur - 0.5) * 18)
    d.line([(cx, cy), (cx + R * 0.8 * math.cos(ang), cy + R * 0.8 * math.sin(ang))], fill=WHITE, width=int(R * 0.05))
    d.ellipse([cx - R * 0.07, cy - R * 0.07, cx + R * 0.07, cy + R * 0.07], fill=WHITE)
    nf = _font(int(W * (0.12 if short else 0.07)))
    _center_text(d, cx, cy + R * 0.12, f"{int(round(cur))}/10", nf, WHITE)
    if t > 1.6:
        vf = _font(int(W * (0.06 if short else 0.04)))
        _center_text(d, cx, cy + R * 0.12 + nf.size * 1.3, VERDICT[val], vf, ACCENT2)
    return img


def _tomorrow_test(g, W, H, t, short):
    img = _background(W, H)
    d = ImageDraw.Draw(img)
    ans = str(g.get("answer", "Maybe")).strip().lower()
    pick = 0 if ans.startswith("y") else 2 if ans.startswith("n") else 1
    tf = _font(int(W * (0.09 if short else 0.055)))
    _center_text(d, W / 2, H * (0.10 if short else 0.16), "TOMORROW TEST", tf, WHITE)
    sf = _label_font(int(W * (0.038 if short else 0.024)))
    _center_text(d, W / 2, H * (0.10 if short else 0.16) + tf.size * 1.35,
                 "WILL THIS CHANGE YOUR LIFE IN 5 YEARS?", sf, GREY)
    opts = ["YES", "MAYBE", "NOT YET"]
    pf = _font(int(W * (0.07 if short else 0.042)))
    y = H * (0.30 if short else 0.48)
    bw, bh = W * (0.62 if short else 0.24), pf.size * 1.7
    for i, o in enumerate(opts):
        if short:
            x0, y0 = W / 2 - bw / 2, y + i * bh * 1.35
        else:
            x0, y0 = W / 2 - 1.5 * bw - 40 + i * (bw + 40), y
        on = i == pick and t > 0.9 + 0.25 * (t % 0.5 < 0.25 and t < 1.5)
        fill = ACCENT if on else (30, 41, 59)
        d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=int(bh / 2), fill=fill)
        _center_text(d, x0 + bw / 2, y0 + bh / 2 - pf.size * 0.62, o, pf, (9, 13, 28) if on else GREY)
    return img


def _flow(g, W, H, t, short):
    """How-it-works diagram: boxes connected by arrows, appearing one by one (e.g. Reactor -> Power -> Engine -> Thrust)."""
    img = _background(W, H)
    d = ImageDraw.Draw(img)
    steps = [str(x) for x in (g.get("steps") or [])][:5]
    if len(steps) < 2:
        return img
    tf = _font(int(W * (0.065 if short else 0.045)))
    title = str(g.get("title", "")).upper()
    if title:
        _center_text(d, W / 2, H * (0.07 if short else 0.10), title, tf, WHITE)
    bf = _label_font(int(W * (0.042 if short else 0.024)))
    n = len(steps)
    per = 0.55
    for i, st in enumerate(steps):
        a = _ease((t - 0.3 - per * i) / 0.4)
        if a <= 0:
            continue
        active = i == min(n - 1, int(max(0, t - 0.3) / per))
        if short:   # vertical chain in the upper 60% (captions stay readable)
            bw, bh = W * 0.70, H * 0.075
            x0 = W / 2 - bw / 2
            y0 = H * 0.17 + i * (H * 0.43 / n)
            box = [x0, y0, x0 + bw, y0 + bh]
            if i > 0:
                py = H * 0.17 + (i - 1) * (H * 0.43 / n) + bh
                d.line([(W / 2, py + 6), (W / 2, y0 - 10)], fill=GREY, width=6)
                d.polygon([(W / 2 - 16, y0 - 26), (W / 2 + 16, y0 - 26), (W / 2, y0 - 6)], fill=GREY)
        else:       # horizontal chain
            gap = W * 0.035
            bw = (W * 0.88 - gap * (n - 1)) / n
            bh = H * 0.22
            x0 = W * 0.06 + i * (bw + gap)
            y0 = H * 0.42
            box = [x0, y0, x0 + bw, y0 + bh]
            if i > 0:
                ax = x0 - gap
                d.line([(ax + 6, y0 + bh / 2), (x0 - 14, y0 + bh / 2)], fill=GREY, width=6)
                d.polygon([(x0 - 26, y0 + bh / 2 - 14), (x0 - 26, y0 + bh / 2 + 14), (x0 - 6, y0 + bh / 2)], fill=GREY)
        fill = ACCENT if active else (30, 41, 59)
        d.rounded_rectangle(box, radius=18, fill=fill, outline=ACCENT, width=3)
        lines = _wrap(d, st, bf, (box[2] - box[0]) * 0.86)[:3]
        ty = (box[1] + box[3]) / 2 - len(lines) * bf.size * 0.6
        for k, ln in enumerate(lines):
            _center_text(d, (box[0] + box[2]) / 2, ty + k * bf.size * 1.15, ln, bf, (9, 13, 28) if active else WHITE)
    return img


PAINTERS = {"counter": _counter, "bars": _bars, "timeline": _timeline, "hype_meter": _hype_meter,
            "tomorrow_test": _tomorrow_test, "flow": _flow}


def render(graphic, W, H, seconds, out_path, short):
    """Animated graphic clip (mp4) of `seconds` length. Returns path or None."""
    painter = PAINTERS.get((graphic or {}).get("type"))
    if not painter:
        return None
    tmp = Path(tempfile.mkdtemp(prefix="gfx_"))
    try:
        n = max(2, int(seconds * FPS_DRAW) + 2)
        for i in range(n):   # (the channel logo is added once for the whole video as a watermark)
            painter(graphic, W, H, i / FPS_DRAW, short).convert("RGB").save(tmp / f"f_{i:04d}.png")
        run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS_DRAW), "-i", str(tmp / "f_%04d.png"),
             "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
             "-t", f"{seconds:.3f}", str(out_path)])
        return out_path
    except Exception as e:  # noqa: BLE001
        log("Graphic failed:", str(e)[:120])
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
