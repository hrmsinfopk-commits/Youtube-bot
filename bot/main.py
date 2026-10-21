"""Entry point.  python -m bot.main --type short|long [--no-upload] [--offline-test]"""
import argparse
import json
import random
import shutil
import time

from . import audiofx, curate, footage, graphics, images, render, trends, upload, voice, writer
from .common import CHANNEL, DATA, OUT, WORK, load_config, load_history, log, run, save_history


def load_learning():
    p = DATA / f"learning_{CHANNEL['id']}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def load_memory():
    """What we said before: openings, endings, full scripts, signatures (to never repeat ourselves)."""
    p = DATA / f"memory_{CHANNEL['id']}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"openings": [], "endings": [], "scripts": [], "recent_signatures": [], "recent_styles": []}


def save_memory(mem, script, style):
    sc = script.get("scenes") or [{}]
    mem.setdefault("openings", []).append(sc[0].get("text", "")[:160])
    mem.setdefault("endings", []).append(sc[-1].get("text", "")[:160])
    mem.setdefault("scripts", []).append(writer.script_text(script)[:6000])
    mem.setdefault("recent_signatures", []).append(script.get("signature", ""))
    mem.setdefault("recent_styles", []).append(style)
    for k, n in (("openings", 80), ("endings", 80), ("scripts", 60), ("recent_signatures", 20), ("recent_styles", 20)):
        mem[k] = mem[k][-n:]
    DATA.mkdir(exist_ok=True)
    (DATA / f"memory_{CHANNEL['id']}.json").write_text(json.dumps(mem, ensure_ascii=False, indent=1), encoding="utf-8")


def pick_style(cfg, learning, rng):
    """Mostly pick styles that performed well on our channel, but keep exploring (25%) so we keep learning."""
    last = (load_memory().get("recent_styles") or [None])[-1]
    styles = [x for x in cfg["styles"] if x != last] or cfg["styles"]
    scores = (learning or {}).get("style_scores", {})
    if not scores or rng.random() < 0.25:
        return rng.choice(styles)
    weights = [max(0.2, scores.get(s, 1.0)) for s in styles]
    return rng.choices(styles, weights=weights, k=1)[0]


def fmt_ts(t):
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def chapters(scenes, timings, total):
    ch = [(t0, s["chapter"].strip()) for s, (t0, _) in zip(scenes, timings) if s.get("chapter", "").strip()]
    if not ch:
        return ""
    if ch[0][0] > 0.5:
        ch.insert(0, (0.0, "Shuruaat"))
    else:
        ch[0] = (0.0, ch[0][1])
    clean = [c for i, c in enumerate(ch) if i == 0 or c[0] - ch[i - 1][0] >= 10]
    if len(clean) < 3:
        return ""
    return "\n".join(f"{fmt_ts(t)} {name}" for t, name in clean)


def build_description(cfg, kind, script, chap, history):
    parts = [script.get("description", "").strip()]
    if kind == "short" and cfg["upload"].get("link_long_video_in_shorts"):
        longs = [v for v in history["videos"] if v.get("type") == "long" and v.get("youtube_id")]
        if longs:
            parts.append(f"Poori video dekhein: https://youtu.be/{longs[-1]['youtube_id']}")
    if chap:
        parts.append("Chapters:\n" + chap)
    if cfg["channel"].get("mode") == "stories":
        parts.append("Yeh kahani fiction hai. Tamam kirdaar aur waqiat farzi hain.")
    parts.append(" ".join(script.get("hashtags", [])[:5]))
    parts.append("Footage: Pexels / Pixabay")
    return "\n\n".join(p for p in parts if p)


# ------------------------------------------------------------------ offline test data
def _offline_script(kind):
    n = 7 if kind == "short" else 10
    lines = [
        ("2040 tak har ghar mein ek robot hoga, aur woh sirf safai nahi karega.", "robot"),
        ("Woh aapka khana banayega, bachon ko parhayega, aur aapki sehat check karega.", "kitchen"),
        ("Lekin asal twist yeh hai ke yeh robot khud seekhega.", "ai brain"),
        ("Har din aapki aadat dekh kar woh behtar hota jayega.", "city night"),
        ("Japan aur Korea mein iske test abhi se shuru ho chuke hain.", "tokyo"),
        ("Socho zara, jab robot aapse behtar chai banane lage.", "tea"),
        ("Aur yahi wajah hai ke 2040 tak har ghar mein ek robot hoga.", "robot"),
    ]
    scenes = []
    for i in range(n):
        t, k = lines[i % len(lines)]
        scenes.append({"text": t, "caption": t, "keywords": [k], "pace": ["fast", "normal", "slow"][i % 3],
                       "reveal": i in (2, 6),
                       "chapter": (f"Hissa {i // 3 + 1}" if kind == "long" and i % 3 == 0 else "")})
    return {"title": "2040 Mein Har Ghar Mein Robot? Future Of AI Robots", "thumbnail_text": "ROBOT GHAR MEIN?",
            "description": "Test description.", "hook_text": "ROBOT GHAR MEIN?", "mood": "suspense", "tags": ["ai", "robot"], "hashtags": ["#AI", "#Future"],
            "scenes": scenes, "topic": "offline test", "style": "test"}


def _offline_voice(scenes, work):
    out = []
    for i, s in enumerate(scenes):
        d = max(1.5, len(s["caption"]) / 14)
        wav = work / f"voice_{i:03d}.wav"
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"sine=frequency={220 + 40 * (i % 5)}:sample_rate=44100", "-af", "volume=0.2",
             "-ac", "2", "-t", f"{d:.2f}", "-c:a", "pcm_s16le", str(wav)])
        out.append((wav, d, []))
    return out


def _offline_media(scenes, work, kind):
    W, H = render.SIZES[kind]
    media = []
    for i, _ in enumerate(scenes):
        p = work / f"media_{i}.mp4"
        src = random.choice(["testsrc2", "mandelbrot", "life=s=320x240:mold=10:r=30:ratio=0.5", "cellauto=rule=110"])
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"{src}", "-t", "6",
             "-vf", f"scale={W // 2}:{H // 2},format=yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(p)])
        media.append([(p, "video")])
    return media


# ------------------------------------------------------------------ main pipeline
def make_one(cfg, kind, history, offline=False, do_upload=True):
    work = WORK / f"{kind}_{int(time.time())}"
    (work / "media").mkdir(parents=True, exist_ok=True)
    OUT.mkdir(exist_ok=True)
    rng = random.Random()

    credits, concept_scenes, footage_sources = [], [], []
    if offline:
        script = _offline_script(kind)
        vset = {"voice": "offline", "rate": "+0%", "pitch": "+0Hz"}
        voices = _offline_voice(script["scenes"], work)
        media = _offline_media(script["scenes"], work, kind)
    else:
        learning = load_learning()
        style = pick_style(cfg, learning, rng)
        brief = None
        if cfg.get("trends", {}).get("enabled") and cfg["channel"].get("mode") != "stories":
            queued = writer.queued_topic(kind, consume=do_upload)
            take = None
            if queued and " | " in queued:      # "topic | my take ..." in topics.txt
                queued, take = [x.strip() for x in queued.split(" | ", 1)]
            brief = trends.brief_for(cfg, queued, kind) if queued else trends.find_topic(cfg, history, kind, learning)
            if take:
                brief = brief or {}
                brief["owner_take"] = take
            topic = queued or (f"{brief['topic']} - {brief['angle']}" if brief and brief.get("angle") else
                               (brief or {}).get("topic"))
        else:
            topic = None
        topic = topic or writer.pick_topic(cfg, history, kind)
        memory = load_memory()
        script = writer.write_script(cfg, topic, kind, style, brief, memory)
        host = cfg.get("tts", {}).get("host_voice")
        vset = voice.pick_voice(cfg, None if host else script.get("narrator_gender"))
        if host and vset.get("engine") == "gemini":
            vset["voice"] = host      # one recognisable channel narrator
        log("Voice:", vset)
        voices = voice.synth_scenes(cfg, script["scenes"], work, vset)

        orient = "portrait" if kind == "short" else "landscape"
        used = set(history["used_media"])
        media, cache = [], {}
        vis = cfg.get("visual", {})
        if vis.get("images"):   # one original AI picture per scene, same art style for the whole video
            iw, ih = (768, 1344) if kind == "short" else (1344, 768)
            seed = rng.randint(1, 10**7)
            made = 0
            for i, sc in enumerate(script["scenes"]):
                p = work / "media" / f"img_{i:03d}.jpg"
                if sc.get("image") and images.generate(sc["image"], vis.get("art_style", ""), iw, ih, p, seed + i):
                    cache[i] = [(p, "photo")]
                    made += 1
            log(f"AI images: {made}/{len(script['scenes'])}")
        gw, gh = render.SIZES[kind]
        for i, sc in enumerate(script["scenes"]):
            if i not in cache and sc.get("graphic"):
                gp = work / "media" / f"graphic_{i:03d}.mp4"
                if graphics.render(sc["graphic"], gw, gh, voices[i][1] + 1.6, gp, kind == "short"):
                    cache[i] = [(gp, "graphic")]
        if any(v[0][1] == "graphic" for v in cache.values()):
            log(f"Own graphics: {sum(1 for v in cache.values() if v[0][1] == 'graphic')}")
        need = 3 if kind == "short" else 2   # long videos have many scenes; 2 clips each is plenty
        gk = script.get("global_keywords", [])
        picked = [None] * len(script["scenes"])
        if cfg["footage"].get("relevance_check", True):
            # gather options for every scene, then the picture editor (Gemini) keeps only the fitting ones
            opts = []
            for i, sc in enumerate(script["scenes"]):
                opts.append([] if i in cache else footage.candidates(
                    cfg, sc["keywords"] + rng.sample(gk, min(1, len(gk))), orient, used, subject=sc.get("subject")))
            for sc in script["scenes"]:
                sc["topic"] = script["topic"]
            picked = curate.pick(cfg, script["scenes"], opts, per_scene=need)
        for i, sc in enumerate(script["scenes"]):
            if i in cache:
                media.append(cache[i])
                continue
            if picked[i] is not None:
                items = picked[i]
            else:
                items = footage.search(cfg, sc["keywords"] + rng.sample(gk, min(2, len(gk))), orient, used, need=need)
            if not items and sc.get("image") and cfg["footage"].get("concept_images", True):
                # nothing real fits -> an original AI "concept illustration" (labelled on screen)
                iw, ih = (768, 1344) if kind == "short" else (1344, 768)
                p = work / "media" / f"concept_{i:03d}.jpg"
                style = cfg["footage"].get("concept_style", "realistic cinematic concept art")
                if images.generate(sc["image"], style, iw, ih, p):
                    media.append([(p, "photo")])
                    concept_scenes.append(i)
                    continue
            if not items:
                items = footage.search(cfg, gk + cfg["channel"].get("fallback_keywords", ["futuristic technology"]),
                                       orient, used, need=need)
            got, rejected = [], 0
            for rnd in range(2):
                if rnd == 1:             # every clip had burned-in text -> one more search for this scene
                    if got or not rejected:
                        break
                    items = footage.search(cfg, sc["keywords"] + rng.sample(gk, min(2, len(gk))), orient, used, need=need)
                for it in items:
                    ext = ".mp4" if it["kind"] == "video" else ".jpg"
                    p = work / "media" / f"{it['id']}{ext}"
                    try:
                        footage.download(it, p)
                        if cfg["footage"].get("reject_text", True) and footage.has_text(p, it["kind"]):
                            used.add(it["id"])               # burned-in subtitles/titles -> never use this clip
                            history["used_media"].append(it["id"])
                            p.unlink(missing_ok=True)
                            rejected += 1
                            continue
                        got.append((p, it["kind"]))
                        used.add(it["id"])
                        history["used_media"].append(it["id"])
                        if it.get("credit"):
                            credits.append(it["credit"])
                        src_name = {"nasa": "NASA", "pexels": "Pexels", "pixabay": "Pixabay", "wm": "Wikimedia Commons",
                                    "ov": "Openverse"}.get(it["id"].split("-")[0])
                        if src_name and src_name not in footage_sources:
                            footage_sources.append(src_name)
                    except Exception as e:  # noqa: BLE001
                        log("Download failed:", str(e)[:100])
            if not got:  # reuse previous scene's footage
                got = media[-1] if media else []
            if not got:
                raise RuntimeError("Koi footage nahi mili - PEXELS_API_KEY / PIXABAY_API_KEY check karein")
            media.append(got)
        log(f"Footage ready for {len(media)} scenes")
        # first scenes may have been empty and filled later: none left empty here

    scene_sounds, ambience = [None] * len(script["scenes"]), None
    if not offline and cfg.get("visual", {}).get("sound_design"):
        for i, sc in enumerate(script["scenes"]):
            if sc.get("sound"):
                scene_sounds[i] = audiofx.freesound_sfx(work / f"sfx_{i:03d}.wav", sc["sound"], max_dur=6)
        if script.get("ambience"):
            ambience = audiofx.freesound_sfx(work / "ambience.wav", script["ambience"], max_dur=90, min_dur=8)

    slug = time.strftime("%Y%m%d_%H%M") + f"_{CHANNEL['id']}_{kind}"
    video = OUT / f"{slug}.mp4"
    timings, total = render.assemble(kind, cfg, script["scenes"], voices, media, work, video, rng,
                                     mood=script.get("mood", "suspense"), hook_text=script.get("hook_text", ""),
                                     scene_sounds=scene_sounds, ambience=ambience,
                                     concept_scenes=concept_scenes)

    thumb = None
    if kind == "long":
        tag = next((sc.get("subject") for sc in script["scenes"] if sc.get("subject")), "")[:22]
        thumb = render.thumbnail(work / "video_noaudio.mp4", script.get("thumbnail_text") or script["title"],
                                 OUT / f"{slug}_thumb.jpg", rng, at=1.5, tag=tag)

    chap = chapters(script["scenes"], timings, total) if kind == "long" else ""
    title = script["title"].strip()
    if kind == "short" and "#shorts" not in title.lower():
        title = f"{title[:88]} #shorts"
    desc = build_description(cfg, kind, script, chap, history)
    if footage_sources:
        desc = desc.replace("Footage: Pexels / Pixabay", "Footage: " + ", ".join(footage_sources))
    elif any(sc.get("graphic") for sc in script.get("scenes", [])):
        desc = desc.replace("Footage: Pexels / Pixabay\n\n", "").replace("Footage: Pexels / Pixabay", "")
    if credits:
        desc += "\n\nImage credits: " + "; ".join(dict.fromkeys(credits))[:900]
    if concept_scenes:
        desc += "\nSome images are AI concept illustrations, not real photos."
    if not offline and brief and brief.get("sources"):
        outlets = sorted({x["source"] for x in brief["sources"] if x.get("source")})[:6]
        if outlets:
            desc += "\n\nBased on reporting from: " + ", ".join(outlets)
    meta = {"title": title, "description": desc,
            "tags": script.get("tags", []), "topic": script["topic"], "style": script["style"], "kind": kind,
            "voice": vset, "seconds": round(total, 1)}
    (OUT / f"{slug}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / f"{slug}_script.txt").write_text("\n\n".join(s["text"] for s in script["scenes"]), encoding="utf-8")

    yt_id = None
    if do_upload and cfg["upload"]["enabled"] and not offline:
        if upload.ready():
            yt_id = upload.upload(cfg, video, meta, thumb)
        else:
            log("YouTube secrets missing - video sirf GitHub artifact mein save hogi")

    history["videos"].append({"date": time.strftime("%Y-%m-%d %H:%M"), "type": kind, "title": title,
                              "topic": script["topic"], "style": script["style"], "youtube_id": yt_id,
                              "voice": vset.get("voice"), "seconds": round(total, 1),
                              "scene_times": [[round(t0, 1), sc.get("caption", "")[:90]]
                                              for sc, (t0, _) in zip(script["scenes"], timings)],
                              "format": (brief or {}).get("long_format") if not offline else None,
                              "why": (brief or {}).get("why", "") if not offline else ""})
    if not offline and do_upload:          # test runs are not remembered (their topic stays available)
        save_history(history)
        save_memory(load_memory(), script, script.get("style", ""))
    shutil.rmtree(work, ignore_errors=True)
    return video


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=["short", "long"], default="short")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--offline-test", action="store_true")
    ap.add_argument("--channel", default="future", help="future | kahani (channels/<name>.yaml)")
    a = ap.parse_args()
    cfg = load_config(a.channel)
    log(f"Channel: {cfg['channel']['name']} ({a.channel}, mode={cfg['channel']['mode']})")
    history = load_history()
    n = cfg["shorts"]["per_run"] if a.type == "short" else cfg["long"]["per_run"]
    fails = 0
    for i in range(n):
        try:
            make_one(cfg, a.type, history, offline=a.offline_test, do_upload=not a.no_upload)
        except Exception as e:  # noqa: BLE001
            fails += 1
            log(f"Video {i + 1} failed: {e}")
    if fails == n:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
