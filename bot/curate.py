"""Picture editor: for every scene Gemini LOOKS at small preview pictures of the candidate clips/photos (plus their
descriptions) and keeps only the ones that really show what the narration says. Falls back to descriptions only."""
import base64
import io
import json
from concurrent.futures import ThreadPoolExecutor

import requests

from .common import log
from .llm import ask

UA = {"User-Agent": "Mozilla/5.0 (yt-bot)"}
MAX_IMAGES_PER_CALL = 40

RULES = """Rules: choose options whose PICTURE clearly shows what the viewer should SEE while hearing the line.
Literal word matches are NOT enough (a car "deadline" must not get a clock). SAME WORD, DIFFERENT THING is WRONG:
a jet-engine "turbine" is not a wind turbine, a "ceramic coating" is not a coffee mug, a "cell" in biology is not a
prison cell or a phone, a "chip" is not a potato chip. Military jets only when the line is about military aircraft. Reject: unrelated places/people, stock actors
posing or reacting (yawning, smiling to camera, business people) unless the line is about people, green/blue screens,
pictures with text/logos/watermarks, birthdays/holidays, zodiac, anything that contradicts the line, talking heads,
labelled diagrams about another subject, cartoons/silhouettes when the line is about real hardware.
A generic but fitting shot is fine (a jet engine for a jet-engine line). For scene 0 pick the most dramatic fitting option.
If nothing fits, return an empty list for that scene - our own graphics or a still shot will be used instead."""


def _thumb(url):
    if not url:
        return None
    try:
        from PIL import Image
        r = requests.get(url, headers=UA, timeout=15)
        if r.status_code != 200:
            return None
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((320, 320))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001
        return None


def _text_pick(cfg, scenes, cands, per_scene, idx):
    rows = [{"scene": i, "line": scenes[i].get("caption") or scenes[i].get("text", ""),
             "options": [f"{j}: [{c['kind']}] {c.get('desc', '')[:110]}" for j, c in enumerate(cands[i])]} for i in idx]
    res = ask(cfg, f"You are the picture editor of a YouTube video about: {scenes[0].get('topic', '')}.\n{RULES}\n"
              f"Choose up to {per_scene} options per scene from the descriptions.\nSCENES:\n{json.dumps(rows, ensure_ascii=False)}\n"
              'Return ONLY JSON: {"picks": {"<scene number>": [option numbers]}}', json_mode=True, temperature=0.2)
    return res.get("picks", {})


def _visual_pick(cfg, scenes, cands, per_scene, idx, thumbs):
    parts = []
    for i in idx:
        parts.append({"text": f"\n=== SCENE {i}: \"{scenes[i].get('caption') or scenes[i].get('text', '')}\""})
        for j, c in enumerate(cands[i]):
            t = thumbs.get(c["id"])
            parts.append({"text": f"[{i}-{j}] {c['kind']}: {c.get('desc', '')[:90]}" + ("" if t else " (no preview)")})
            if t:
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": t}})
    prompt = (f"You are the picture editor of a YouTube video about: {scenes[0].get('topic', '')}.\n{RULES}\n"
              f"Below, every scene's narration line is followed by numbered options [scene-option] with a preview picture "
              f"(for videos: one frame). Look at the pictures. Choose up to {per_scene} options per scene.\n"
              'Return ONLY JSON: {"picks": {"<scene number>": [option numbers]}}')
    res = ask(cfg, prompt, json_mode=True, temperature=0.2, extra_parts=parts)
    return res.get("picks", {})


def pick(cfg, scenes, cands, per_scene=2):
    """cands: list (per scene) of candidate dicts. Returns list (per scene) of chosen candidate dicts."""
    idx_all = [i for i, cs in enumerate(cands) if cs]
    urls = {c["id"]: c.get("thumb") for i in idx_all for c in cands[i]}
    with ThreadPoolExecutor(8) as ex:
        thumbs = dict(zip(urls.keys(), ex.map(_thumb, urls.values())))
    seen = sum(1 for v in thumbs.values() if v)
    log(f"Picture editor: {seen}/{len(thumbs)} previews loaded")
    picks = {}
    # batches that stay under the image limit per request
    batch, n_img = [], 0
    batches = []
    for i in idx_all:
        k = sum(1 for c in cands[i] if thumbs.get(c["id"]))
        if batch and n_img + k > MAX_IMAGES_PER_CALL:
            batches.append(batch)
            batch, n_img = [], 0
        batch.append(i)
        n_img += k
    if batch:
        batches.append(batch)
    for b in batches:
        try:
            picks.update(_visual_pick(cfg, scenes, cands, per_scene, b, thumbs) if seen else
                         _text_pick(cfg, scenes, cands, per_scene, b))
        except Exception as e:  # noqa: BLE001
            log("Visual check failed for a batch, using descriptions:", str(e)[:100])
            try:
                picks.update(_text_pick(cfg, scenes, cands, per_scene, b))
            except Exception as e2:  # noqa: BLE001
                log("Footage check failed, using search order:", str(e2)[:100])
                for i in b:
                    picks[str(i)] = list(range(min(per_scene, len(cands[i]))))
    out = []
    for i, cs in enumerate(cands):
        idx = picks.get(str(i), picks.get(i, [])) or []
        chosen = [cs[j] for j in idx if isinstance(j, int) and 0 <= j < len(cs)][:per_scene]
        out.append(chosen)
    kept = sum(len(x) for x in out)
    log(f"Footage check: kept {kept} fitting clips, {sum(1 for i, x in enumerate(out) if not x and cands[i])} scenes had nothing fitting")
    return out
