"""Relevance check: for every scene, Gemini looks at the narration line and the descriptions/tags of the
candidate clips and picks only the ones that really fit what is being said (one call for the whole video)."""
import json

from .common import log
from .llm import ask


def pick(cfg, scenes, cands, per_scene=2):
    """cands: list (per scene) of candidate dicts. Returns list (per scene) of chosen candidate dicts."""
    rows = []
    for i, (sc, cs) in enumerate(zip(scenes, cands)):
        opts = [f"{j}: [{c['kind']}] {c.get('desc', '')[:110]}" for j, c in enumerate(cs)]
        rows.append({"scene": i, "line": sc.get("caption") or sc.get("text", ""), "options": opts})
    prompt = f"""You are the picture editor of a YouTube video about: {scenes[0].get('topic', '') if scenes else ''}.
For each scene you get the narration line and numbered stock/archive options (with their descriptions/tags).
Choose up to {per_scene} options whose content clearly matches what the viewer should SEE while hearing that line.
Rules: literal word matches are NOT enough (a line about a car "deadline" must not get a clock; "reservations" must not get coffee).
Reject: unrelated places/people, green screens, text/graphics with other words, birthdays/holidays, zodiac/astrology,
anything that contradicts the line. A generic but fitting shot (e.g. a sports car on a road for a car line) is fine.
If nothing fits, return an empty list for that scene.

SCENES:
{json.dumps(rows, ensure_ascii=False)}

Return ONLY JSON: {{"picks": [[indices for scene 0], [indices for scene 1], ...]}}"""
    try:
        res = ask(cfg, prompt, json_mode=True, temperature=0.2)
        picks = res.get("picks", [])
    except Exception as e:  # noqa: BLE001
        log("Footage check failed, using search order:", str(e)[:100])
        return [cs[:per_scene] for cs in cands]
    out = []
    for i, cs in enumerate(cands):
        idx = picks[i] if i < len(picks) and isinstance(picks[i], list) else []
        chosen = [cs[j] for j in idx if isinstance(j, int) and 0 <= j < len(cs)][:per_scene]
        out.append(chosen)
    kept = sum(len(x) for x in out)
    log(f"Footage check: kept {kept} fitting clips, {sum(1 for x in out if not x)} scenes had nothing fitting")
    return out
