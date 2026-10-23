"""AI-generated scene images (Pollinations, free). Every scene gets its own picture in one consistent style.
Prompts are always original scenes: no real people, no known characters, no logos, no text."""
import random
import time
import urllib.parse

import requests
from PIL import Image

from .common import log, secret

SAFE = ("original scene, no text, no letters, no watermark, no logo, no real person, no celebrity, "
        "no famous character, no gore")
_last = [0.0]


def _wait():
    # anonymous use is limited to ~1 request / 15 s; a free token removes the limit
    gap = 2 if secret("POLLINATIONS_TOKEN") else 16
    d = time.time() - _last[0]
    if d < gap:
        time.sleep(gap - d)
    _last[0] = time.time()


def _watermarked(path):
    """True if the picture carries a service watermark (e.g. 'pollinations.ai'). Corners are enlarged and read with OCR."""
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("tesseract"):
        return False
    im = Image.open(path).convert("L")
    w, h = im.size
    strips = [(0, int(h * 0.92), w, h), (0, 0, w, int(h * 0.08))]      # full-width bottom and top strips
    with tempfile.TemporaryDirectory() as td:
        for k, b in enumerate(strips):
            c = im.crop(b)
            c = c.resize((c.width * 3, c.height * 3))
            for j, img in enumerate((c.point(lambda v: 0 if v > 200 else 255), c)):
                f = f"{td}/c{k}{j}.png"
                img.save(f)
                for psm in ("11", "6"):
                    txt = subprocess.run(["tesseract", f, "stdout", "--psm", psm], capture_output=True, text=True).stdout.lower()
                    if any(x in txt for x in ("pollin", "linati", "nations.a")):
                        return True
    return False


def generate(prompt, style, W, H, path, seed=None):
    full = f"{prompt}. {style}. {SAFE}"
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(full[:900])
    H0 = H
    H = int(H * 1.12) // 8 * 8          # extra strip at the bottom (where a watermark sits) is cut off afterwards
    params = {"width": W, "height": H, "seed": seed or random.randint(1, 10**8), "nologo": "true",
              "model": "flux", "private": "true", "enhance": "false"}
    headers = {"User-Agent": "yt-bot/1.0"}
    if secret("POLLINATIONS_TOKEN"):
        headers["Authorization"] = f"Bearer {secret('POLLINATIONS_TOKEN')}"
    for attempt in range(3):
        _wait()
        try:
            r = requests.get(url, params=params, headers=headers, timeout=150)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                with open(path, "wb") as f:
                    f.write(r.content)
                im = Image.open(path).convert("RGB")
                if min(im.size) >= 400:
                    keep = int(im.height * H0 / H)          # same aspect as asked, bottom strip removed
                    im.crop((0, 0, im.width, keep)).save(path, quality=95)
                    if _watermarked(path):
                        log("Image has a watermark - trying another one")
                        params["seed"] = random.randint(1, 10**8)
                        continue
                    return path
            log(f"Image HTTP {r.status_code} (try {attempt + 1})")
        except Exception as e:  # noqa: BLE001
            log("Image error:", str(e)[:120])
        time.sleep(10)
    return None
