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


def generate(prompt, style, W, H, path, seed=None):
    full = f"{prompt}. {style}. {SAFE}"
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(full[:900])
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
                im = Image.open(path)
                if min(im.size) >= 400:
                    return path
            log(f"Image HTTP {r.status_code} (try {attempt + 1})")
        except Exception as e:  # noqa: BLE001
            log("Image error:", str(e)[:120])
        time.sleep(10)
    return None
