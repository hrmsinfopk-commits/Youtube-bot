"""Free, licensed stock footage from Pexels and Pixabay (videos first, photos as fallback)."""
import random
import re

import requests

from .common import log, secret

UA = {"User-Agent": "yt-bot/1.0"}


def _pexels_videos(q, orient):
    key = secret("PEXELS_API_KEY")
    if not key:
        return []
    r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": key, **UA},
                     params={"query": q, "orientation": orient, "per_page": 20, "size": "medium"},
                     timeout=30)
    if r.status_code != 200:
        log("Pexels", r.status_code)
        return []
    res = []
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"
                 and f.get("width") and f.get("height")]
        # smallest file that is still >= 720p on its short side
        good = sorted([f for f in files if min(f["width"], f["height"]) >= 720],
                      key=lambda f: f["width"] * f["height"])
        if good:
            res.append({"id": f"pexels-v-{v['id']}", "url": good[0]["link"], "kind": "video",
                        "dur": v.get("duration", 10), "desc": v.get("url", ""), "thumb": v.get("image")})
    return res


def _pixabay_videos(q, orient):
    key = secret("PIXABAY_API_KEY")
    if not key:
        return []
    r = requests.get("https://pixabay.com/api/videos/", headers=UA,
                     params={"key": key, "q": q[:100], "per_page": 20, "safesearch": "true"}, timeout=30)
    if r.status_code != 200:
        return []
    res = []
    for h in r.json().get("hits", []):
        vids = h.get("videos", {})
        for size in ("medium", "large", "small"):
            f = vids.get(size) or {}
            if f.get("url") and min(f.get("width", 0), f.get("height", 0)) >= 720:
                res.append({"id": f"pixabay-v-{h['id']}", "url": f["url"], "kind": "video",
                            "dur": h.get("duration", 10), "desc": h.get("tags", ""), "thumb": f.get("thumbnail")})
                break
    return res


NASA_API = "https://images-api.nasa.gov/search"


def _nasa_assets(href):
    try:
        files = requests.get(href, headers=UA, timeout=20).json()
    except Exception:  # noqa: BLE001
        return []
    return [f.replace("http://", "https://") for f in files if isinstance(f, str)]


def _nasa_videos(q, orient, limit=6):
    """NASA Image & Video Library: real mission footage (generally not copyrighted; no NASA logo use/endorsement)."""
    try:
        r = requests.get(NASA_API, params={"q": q, "media_type": "video"}, headers=UA, timeout=25)
        items = r.json().get("collection", {}).get("items", []) if r.status_code == 200 else []
    except Exception:  # noqa: BLE001
        return []
    res = []
    for it in items[:limit]:
        d = (it.get("data") or [{}])[0]
        files = _nasa_assets(it.get("href", ""))
        mp4 = [f for f in files if f.endswith(".mp4")]
        pick = next((f for f in mp4 if "~medium" in f), None) or next((f for f in mp4 if "~mobile" in f), None)
        if pick:
            res.append({"id": f"nasa-v-{d.get('nasa_id', pick)}", "url": pick, "kind": "video", "dur": 20,
                        "desc": f"{d.get('title', '')} {' '.join(d.get('keywords') or [])}",
                        "thumb": ((it.get("links") or [{}])[0].get("href") or "").replace("http://", "https://") or None})
    return res


def _nasa_photos(q, orient, limit=8):
    try:
        r = requests.get(NASA_API, params={"q": q, "media_type": "image"}, headers=UA, timeout=25)
        items = r.json().get("collection", {}).get("items", []) if r.status_code == 200 else []
    except Exception:  # noqa: BLE001
        return []
    res = []
    for it in items[:limit]:
        d = (it.get("data") or [{}])[0]
        files = _nasa_assets(it.get("href", ""))
        pick = next((f for f in files if "~large.jpg" in f), None) or next((f for f in files if "~orig.jpg" in f), None)
        if pick:
            res.append({"id": f"nasa-p-{d.get('nasa_id', pick)}", "url": pick, "kind": "photo", "dur": 5,
                        "desc": f"{d.get('title', '')} {' '.join(d.get('keywords') or [])}",
                        "thumb": ((it.get("links") or [{}])[0].get("href") or "").replace("http://", "https://") or None})
    return res


def _pexels_photos(q, orient):
    key = secret("PEXELS_API_KEY")
    if not key:
        return []
    r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": key, **UA},
                     params={"query": q, "orientation": orient, "per_page": 15}, timeout=30)
    if r.status_code != 200:
        return []
    return [{"id": f"pexels-p-{p['id']}", "url": p["src"]["large2x"], "kind": "photo", "dur": 5,
             "desc": (p.get("alt") or "") + " " + p.get("url", ""), "thumb": p["src"].get("medium")}
            for p in r.json().get("photos", [])]


def _pixabay_photos(q, orient):
    key = secret("PIXABAY_API_KEY")
    if not key:
        return []
    r = requests.get("https://pixabay.com/api/", headers=UA,
                     params={"key": key, "q": q[:100], "per_page": 15, "safesearch": "true",
                             "orientation": "vertical" if orient == "portrait" else "horizontal",
                             "image_type": "photo"}, timeout=30)
    if r.status_code != 200:
        return []
    return [{"id": f"pixabay-p-{h['id']}", "url": h["largeImageURL"], "kind": "photo", "dur": 5,
             "desc": h.get("tags", ""), "thumb": h.get("webformatURL")} for h in r.json().get("hits", [])]


# ------------------------------------------------------------------ licensed photos of REAL things (with credit)
OK_LICENSES = ("cc0", "pdm", "public domain", "cc by", "cc-by", "by", "by-sa", "cc by-sa", "cc-by-sa")


def _wikimedia_photos(q, limit=8):
    """Wikimedia Commons: real photos (cars at shows, rockets, buildings...). Only licenses that allow commercial use + edits."""
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=25, params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
            "gsrsearch": f"{q} filetype:bitmap", "gsrlimit": limit, "prop": "imageinfo",
            "iiprop": "url|extmetadata|size", "iiurlwidth": 1920})
        pages = (r.json().get("query") or {}).get("pages", {}) if r.status_code == 200 else {}
    except Exception:  # noqa: BLE001
        return []
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        lic = re.sub(r"<[^>]+>", "", (meta.get("LicenseShortName") or {}).get("value", "")).strip()
        lic_l = lic.lower()
        if not lic or "nc" in lic_l.split("-") or " nc" in lic_l or "nd" in lic_l.replace("-", " ").split() \
                or not any(lic_l.startswith(x) or x in lic_l for x in ("cc0", "public domain", "cc by", "cc-by", "pd")):
            continue
        if min(ii.get("width", 0), ii.get("height", 0)) < 700:
            continue
        artist = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip()[:60] or "Unknown"
        desc = re.sub(r"<[^>]+>", " ", (meta.get("ImageDescription") or {}).get("value", ""))[:200]
        out.append({"id": f"wm-{p.get('pageid')}", "url": ii.get("thumburl") or ii.get("url"), "kind": "photo", "dur": 5,
                    "thumb": (ii.get("thumburl") or "").replace("/1920px-", "/320px-") or None,
                    "desc": f"{p.get('title', '')} {desc}", "credit": f"{artist} / Wikimedia Commons, {lic}"})
    return out


def _openverse_photos(q, limit=10):
    """Openverse (Flickr etc.): only licenses that allow commercial use AND modification."""
    try:
        r = requests.get("https://api.openverse.org/v1/images/", headers=UA, timeout=25, params={
            "q": q, "license_type": "commercial,modification", "page_size": limit, "mature": "false"})
        res = r.json().get("results", []) if r.status_code == 200 else []
    except Exception:  # noqa: BLE001
        return []
    out = []
    for x in res:
        if min(x.get("width") or 0, x.get("height") or 0) < 700:
            continue
        lic = f"CC {x.get('license', '').upper()} {x.get('license_version') or ''}".strip()
        out.append({"id": f"ov-{x.get('id')}", "url": x.get("url"), "kind": "photo", "dur": 5, "thumb": x.get("thumbnail"),
                    "desc": f"{x.get('title', '')} {' '.join(t.get('name', '') for t in (x.get('tags') or [])[:10])}",
                    "credit": f"{(x.get('creator') or 'Unknown')[:50]} / {x.get('source', 'Openverse')}, {lic}"})
    return out


SPACE_WORDS = ("space", "rocket", "nasa", "moon", "mars", "astronaut", "satellite", "planet", "galaxy", "star", "orbit",
               "launch", "earth from space", "telescope", "iss", "spacecraft", "nebula", "solar", "asteroid", "comet")


def candidates(cfg, keywords, orient, used, subject=None, per_kw=4):
    """Many options for one scene (not downloaded yet). A relevance check picks the right ones afterwards."""
    sources = cfg["footage"]["sources"]
    spacey = any(w in " ".join(keywords).lower() for w in SPACE_WORDS)
    out, seen = [], set(used)
    def add(items, n):
        k = 0
        for c in items:
            if c["id"] in seen or not c.get("url") or not _allowed(cfg, c):
                continue
            seen.add(c["id"])
            out.append(c)
            k += 1
            if k >= n:
                break
    if subject:   # a real, named thing -> licensed real photos first (marked: they may carry a name tag)
        add([{**c, "subject_match": True} for c in _wikimedia_photos(subject)], 3)
        add([{**c, "subject_match": True} for c in _openverse_photos(subject)], 3)
    for kw in keywords[:3]:
        if "nasa" in sources and spacey:
            add(_nasa_videos(kw, orient), 2)
        if "pexels" in sources:
            add(_pexels_videos(kw, orient), per_kw)
        if "pixabay" in sources:
            add(_pixabay_videos(kw, orient), per_kw)
    if len(out) < 4:
        for kw in keywords[:2]:
            if "nasa" in sources and spacey:
                add(_nasa_photos(kw, orient), 2)
            add(_pixabay_photos(kw, orient) if "pixabay" in sources else [], 3)
    return out[:14]


def _allowed(cfg, item):
    """Drop clips whose tags/description clash with the channel mood (e.g. smiling people in horror)."""
    bad = cfg["footage"].get("exclude_tags") or []
    desc = item.get("desc", "").lower().replace("-", " ")
    return not any(f" {b} " in f" {desc} " or desc.startswith(b + " ") for b in bad)


def search(cfg, keywords, orient, used, need=3):
    """Return up to `need` unused media items for a scene."""
    sources = cfg["footage"]["sources"]
    found = []
    for kw in keywords:
        cands = []
        if "nasa" in sources:
            cands += _nasa_videos(kw, orient)
        if "pexels" in sources:
            cands += _pexels_videos(kw, orient)
        if "pixabay" in sources:
            cands += _pixabay_videos(kw, orient)
        # keep search-relevance order; only mix the top results a little for variety
        cands = [c for c in cands if _allowed(cfg, c)]
        top, rest = cands[:6], cands[6:]
        random.shuffle(top)
        for c in top + rest:
            if c["id"] not in used and c["id"] not in {f["id"] for f in found}:
                found.append(c)
            if len(found) >= need:
                return found
    if len(found) < 2:  # photo fallback
        for kw in keywords:
            cands = (_nasa_photos(kw, orient) if "nasa" in sources else []) + \
                    (_pexels_photos(kw, orient) if "pexels" in sources else []) + \
                    (_pixabay_photos(kw, orient) if "pixabay" in sources else [])
            for c in [c for c in cands if _allowed(cfg, c)][:8]:
                if c["id"] not in used and c["id"] not in {f["id"] for f in found}:
                    found.append(c)
                if len(found) >= need:
                    return found
    return found


MAX_BYTES = 70 * 1024 * 1024   # skip huge files (some NASA originals are several GB)


def download(item, path):
    with requests.get(item["url"], headers=UA, stream=True, timeout=(15, 60)) as r:
        r.raise_for_status()
        size = int(r.headers.get("content-length") or 0)
        if size > MAX_BYTES:
            raise RuntimeError(f"file too big ({size // 1_000_000} MB)")
        got = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                got += len(chunk)
                if got > MAX_BYTES:
                    raise RuntimeError("file too big")
                f.write(chunk)
    return path


def _frame_words(img_path):
    """Big, confidently-read words in one frame (tesseract). Small text (logos, tiny labels) is ignored."""
    import subprocess
    r = subprocess.run(["tesseract", str(img_path), "stdout", "--psm", "11", "tsv"], capture_output=True, text=True)
    rows = [ln.split("\t") for ln in r.stdout.splitlines()[1:]]
    page = next(((int(x[8]), int(x[9])) for x in rows if len(x) == 12 and x[0] == "1"), (1, 1))
    side = min(page) or 1      # text size relative to the short side (works for portrait and landscape)
    words = []
    for x in rows:
        if len(x) != 12 or x[0] != "5":
            continue
        txt, conf, h = x[11].strip(), float(x[10]), int(x[9])
        letters = "".join(ch for ch in txt if ch.isalpha())
        if (conf >= 70 and len(letters) >= 3 and len(letters) >= 0.8 * len(txt)
                and any(v in letters.lower() for v in "aeiouy") and h >= 0.022 * side):
            words.append(letters)
    return words


def has_text(path, kind):
    """True when a clip/photo carries burned-in subtitles or titles (e.g. another video's captions).
    Such text clashes with our own captions and looks like reused content, so the clip is skipped."""
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("tesseract"):
        if not getattr(has_text, "warned", False):
            log("Text check off: tesseract not installed")
            has_text.warned = True
        return False
    with tempfile.TemporaryDirectory() as td:
        shots = []
        if kind == "video":
            try:
                dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                            str(path)], capture_output=True, text=True).stdout.strip() or 0)
            except ValueError:
                dur = 0
            points = [dur * f for f in (0.15, 0.4, 0.65, 0.9)] if dur > 1 else [0]
        else:
            points = [None]
        # two looks at every frame: plain grey, and a mask of the brightest pixels (white/yellow subtitles)
        looks = ["format=gray", "lutyuv=y='if(gt(val,200),0,255)':u=128:v=128,format=gray"]
        for k, t in enumerate(points):
            for j, look in enumerate(looks):
                out = f"{td}/f{k}_{j}.png"
                cmd = ["ffmpeg", "-v", "error", "-y"] + (["-ss", f"{t:.2f}"] if t is not None else []) + \
                      ["-i", str(path), "-frames:v", "1", "-vf", f"scale='min(1280,iw)':-2,{look}", out]
                if subprocess.run(cmd, capture_output=True).returncode == 0:
                    shots.append(out)
        for s in shots:
            w = _frame_words(s)
            if len(w) >= 3:
                log(f"Skipping clip with burned-in text: {' '.join(w[:8])}")
                return True
    return False


def is_greenscreen(path, kind):
    """True for chroma-key footage (big flat green/blue screen areas) - it looks broken in a video."""
    import subprocess
    import numpy as np
    pts = [0.2, 0.5, 0.8] if kind == "video" else [None]
    try:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                   capture_output=True, text=True).stdout.strip() or 0) if kind == "video" else 0
    except ValueError:
        dur = 0
    hits = 0
    for f in pts:
        cmd = ["ffmpeg", "-v", "error"] + (["-ss", f"{dur * f:.2f}"] if f is not None and dur else []) + \
              ["-i", str(path), "-frames:v", "1", "-vf", "scale=160:90", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        raw = subprocess.run(cmd, capture_output=True).stdout
        if len(raw) < 160 * 90 * 3:
            continue
        a = np.frombuffer(raw[:160 * 90 * 3], np.uint8).reshape(90, 160, 3).astype(int)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        green = (g > 120) & (g > r * 1.5) & (g > b * 1.5)
        blue = (b > 120) & (b > r * 1.8) & (b > g * 1.3) & (g > 60)
        if green.mean() > 0.25 or (blue.mean() > 0.45 and (np.std(b[blue]) if blue.any() else 99) < 12):
            hits += 1
    if hits:
        log("Skipping chroma-key (green screen) clip")
    return hits > 0
