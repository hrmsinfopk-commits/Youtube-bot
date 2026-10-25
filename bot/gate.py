"""Quality gate - the channel's monetization protocol.

Every video must show clear own work (not "AI voice over stock footage"): own graphics, own analysis, checked facts,
own wording, fitting pictures, honest AI labelling. The gate fixes what it can and reports the rest; a video that still
fails a hard rule is not uploaded.
"""
import json
import re

from .common import log
from .llm import ask

MIN_GRAPHICS = {"short": 1, "long": 4}
MIN_OWN_SHARE = {"short": 0.10, "long": 0.22}   # share of the narration that runs over our own graphics
MAX_CONCEPT_SHARE = 0.20                         # AI concept images: at most 20 % of scenes
MIN_FIT_SHARE = 0.80                             # scenes whose picture really fits the words

GRAPHIC_SCHEMA = (
    '- {"type": "counter", "value": 250000, "prefix": "$", "suffix": "", "label": "starting price"}\n'
    '- {"type": "bars", "title": "Top speed", "labels": ["Car", "Jet"], "values": [300, 900], "unit": "km/h"}\n'
    '- {"type": "timeline", "items": [{"year": "2024", "text": "First test"}, {"year": "2027", "text": "Planned launch"}]}\n'
    '- {"type": "flow", "title": "How it works", "steps": ["Reactor", "Electricity", "Ion engine", "Thrust"]}\n')
TYPES = {"counter", "bars", "timeline", "flow", "hype_meter", "tomorrow_test"}


def clean_line(t):
    """Remove stage notes that must never be spoken: (on screen: ...), (graphic: ...), [..]."""
    t = re.sub(r"\((?:on[ -]?screen|graphic|visual|sfx|sound|music)[^)]*\)?", "", str(t or ""), flags=re.I)
    t = re.sub(r"\[[^\]]*\]", "", t)
    return " ".join(t.split()).strip()


def _words(s):
    return len(str(s.get("text", "")).split())


def own_share(scenes):
    tot = sum(_words(s) for s in scenes) or 1
    return sum(_words(s) for s in scenes if s.get("graphic")) / tot


def _shingles(text, n=6):
    w = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def _lines(scenes):
    return "\n".join(f"[{i}] {s.get('text', '')}" + (f"  (on screen: {s['on_screen']})" if s.get("on_screen") else "")
                     + (f"  (graphic: {s['graphic'].get('type')})" if s.get("graphic") else "")
                     for i, s in enumerate(scenes))


def _facts(brief):
    return "\n".join(f"- {f}" for f in (brief or {}).get("facts", [])[:40]) or "(no fact sheet - only well-established knowledge)"


def _add_graphics(cfg, script, kind, brief):
    scenes = script["scenes"]
    need = max(MIN_GRAPHICS[kind] - sum(1 for s in scenes if s.get("graphic")), 1)
    prompt = f"""You are the graphics editor of a {kind} YouTube video. Our channel must show clear OWN work, so add our own
animated graphics to scenes where they truly help the viewer: numbers -> counter or bars (a comparison), a process or
"how it works" -> flow, history/plans -> timeline. Add at least {need} graphic(s){', and enough that graphic scenes carry about a quarter of the narration' if kind == 'long' else ''}.
Numbers must come from the fact sheet or the script itself - never invent. Never on the first scene{', never on the last scene' if kind == 'short' else ''}.
Graphic formats:
{GRAPHIC_SCHEMA}
FACT SHEET:
{_facts(brief)}
SCENES:
{_lines(scenes)}
Return ONLY JSON {{"add": [{{"scene": 3, "graphic": {{...}}}}]}}"""
    try:
        res = ask(cfg, prompt, json_mode=True, temperature=0.3)
    except Exception as e:  # noqa: BLE001
        log("Gate: graphics editor failed:", str(e)[:100])
        return 0
    if isinstance(res, list):
        res = {"add": res}
    added = 0
    for a in res.get("add", []):
        i, g = a.get("scene"), a.get("graphic")
        if (isinstance(i, int) and 0 < i < len(scenes) - (1 if kind == "short" else 0) and isinstance(g, dict)
                and g.get("type") in TYPES and not scenes[i].get("graphic")):
            scenes[i]["graphic"] = g
            scenes[i]["on_screen"] = ""
            added += 1
    return added


def _fact_check(cfg, script, brief):
    scenes = script["scenes"]
    prompt = f"""You are the fact-checker of a science/tech YouTube channel. Check every line of this script against the FACT SHEET
and well-established knowledge. Flag ONLY real problems: an invented or wrong number, a claim not supported by the fact sheet,
something only announced/planned/claimed presented as done, or an exaggeration that is not true. Style is not your job.
For each problem give a corrected line of about the same length (same meaning where possible, honest wording).
new_text is SPOKEN NARRATION ONLY: never include "(on screen: ...)", "(graphic: ...)", brackets or stage notes.
FACT SHEET:
{_facts(brief)}
SCRIPT:
{_lines(scenes)}
Return ONLY JSON {{"fixes": [{{"scene": 2, "problem": "...", "new_text": "...", "new_on_screen": ""}}]}} (empty list if all fine)"""
    try:
        res = ask(cfg, prompt, json_mode=True, temperature=0.1)
    except Exception as e:  # noqa: BLE001
        log("Gate: fact check failed:", str(e)[:100])
        return None
    if isinstance(res, list):
        res = {"fixes": res}
    n = 0
    for f in res.get("fixes", []):
        i, t = f.get("scene"), clean_line(f.get("new_text"))
        if isinstance(i, int) and 0 <= i < len(scenes) and t:
            log(f"Gate fact fix [{i}]: {str(f.get('problem', ''))[:100]}")
            scenes[i]["text"] = t
            if cfg["channel"]["language"] == "english":
                scenes[i]["caption"] = t
            if "new_on_screen" in f and scenes[i].get("on_screen"):
                scenes[i]["on_screen"] = str(f.get("new_on_screen") or "")[:40]
            n += 1
    return n


def check_script(cfg, script, kind, brief=None):
    """Before voice/render: own graphics, own-content share, facts, copying. Fixes what it can."""
    scenes = script["scenes"]
    rep = {}
    if (sum(1 for s in scenes if s.get("graphic")) < MIN_GRAPHICS[kind] or own_share(scenes) < MIN_OWN_SHARE[kind]):
        rep["graphics_added"] = _add_graphics(cfg, script, kind, brief)
    rep["graphics"] = sum(1 for s in scenes if s.get("graphic"))
    rep["own_share"] = round(own_share(scenes), 2)
    if kind == "long":
        types = {s["graphic"].get("type") for s in scenes if s.get("graphic")}
        rep["own_math"] = bool(types & {"counter", "bars"})
    fixes = _fact_check(cfg, script, brief)
    rep["fact_fixes"] = fixes if fixes is not None else "skipped"
    src = " ".join([x.get("title", "") for x in (brief or {}).get("sources", [])])
    mine = _shingles(" ".join(s.get("text", "") for s in scenes))
    rep["source_overlap"] = round(len(mine & _shingles(src)) / (len(mine) or 1), 3)
    hard = []
    if rep["graphics"] < MIN_GRAPHICS[kind]:
        hard.append("too few own graphics")
    if rep["source_overlap"] > 0.10:
        hard.append("wording too close to the news source")
    rep["script_ok"] = not hard
    rep["problems"] = hard
    log(f"Gate (script): {json.dumps(rep)}")
    return rep


def check_visuals(rep, kinds, n_scenes):
    """kinds: per scene one of graphic / curated / concept / continued / fallback."""
    n = n_scenes or 1
    fit = sum(1 for k in kinds if k in ("graphic", "curated", "concept", "continued"))
    rep["fit_share"] = round(fit / n, 2)
    rep["concept_share"] = round(kinds.count("concept") / n, 2)
    rep["fallback_scenes"] = kinds.count("fallback")
    if rep["fit_share"] < MIN_FIT_SHARE:
        rep.setdefault("warnings", []).append(f"only {int(rep['fit_share'] * 100)}% of scenes have fitting pictures")
    log(f"Gate (visuals): fit {rep['fit_share']:.0%}, concept {rep['concept_share']:.0%}, fallback {rep['fallback_scenes']}")
    return rep
