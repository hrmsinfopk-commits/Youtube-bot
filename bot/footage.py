"""Free, licensed stock footage from Pexels and Pixabay (videos first, photos as fallback)."""
import random

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
                        "dur": v.get("duration", 10), "desc": v.get("url", "")})
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
                            "dur": h.get("duration", 10), "desc": h.get("tags", "")})
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
        pick = next((f for f in mp4 if "~medium" in f), None) or next((f for f in mp4 if "~mobile" in f), None) \
            or next((f for f in mp4 if "~orig" in f), None)
        if pick:
            res.append({"id": f"nasa-v-{d.get('nasa_id', pick)}", "url": pick, "kind": "video", "dur": 20,
                        "desc": f"{d.get('title', '')} {' '.join(d.get('keywords') or [])}"})
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
                        "desc": f"{d.get('title', '')} {' '.join(d.get('keywords') or [])}"})
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
             "desc": (p.get("alt") or "") + " " + p.get("url", "")} for p in r.json().get("photos", [])]


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
             "desc": h.get("tags", "")} for h in r.json().get("hits", [])]


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


def download(item, path):
    with requests.get(item["url"], headers=UA, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return path
