"""Entry point.  python -m bot.main --type short|long [--no-upload] [--offline-test]"""
import argparse
import json
import random
import shutil
import time

from . import footage, render, upload, voice, writer
from .common import OUT, WORK, load_config, load_history, log, run, save_history


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
        out.append((wav, d))
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

    if offline:
        script = _offline_script(kind)
        vset = {"voice": "offline", "rate": "+0%", "pitch": "+0Hz"}
        voices = _offline_voice(script["scenes"], work)
        media = _offline_media(script["scenes"], work, kind)
    else:
        style = rng.choice(cfg["styles"])
        topic = writer.pick_topic(cfg, history, kind)
        script = writer.write_script(cfg, topic, kind, style)
        vset = voice.pick_voice(cfg)
        log("Voice:", vset)
        voices = voice.synth_scenes(cfg, script["scenes"], work, vset)

        orient = "portrait" if kind == "short" else "landscape"
        used = set(history["used_media"])
        media, cache = [], {}
        for i, sc in enumerate(script["scenes"]):
            need = 2 if kind == "short" else 3
            gk = script.get("global_keywords", [])
            items = footage.search(cfg, sc["keywords"] + rng.sample(gk, min(2, len(gk))), orient, used, need=need)
            if not items:
                items = footage.search(cfg, gk + ["futuristic technology"], orient, used, need=need)
            got = []
            for it in items:
                ext = ".mp4" if it["kind"] == "video" else ".jpg"
                p = work / "media" / f"{it['id']}{ext}"
                try:
                    footage.download(it, p)
                    got.append((p, it["kind"]))
                    used.add(it["id"])
                    history["used_media"].append(it["id"])
                except Exception as e:  # noqa: BLE001
                    log("Download failed:", str(e)[:100])
            if not got:  # reuse previous scene's footage
                got = media[-1] if media else []
            if not got:
                raise RuntimeError("Koi footage nahi mili - PEXELS_API_KEY / PIXABAY_API_KEY check karein")
            media.append(got)
            cache[i] = got
        # first scenes may have been empty and filled later: none left empty here

    slug = time.strftime("%Y%m%d_%H%M") + f"_{kind}"
    video = OUT / f"{slug}.mp4"
    timings, total = render.assemble(kind, cfg, script["scenes"], voices, media, work, video, rng,
                                     mood=script.get("mood", "suspense"), hook_text=script.get("hook_text", ""))

    thumb = None
    if kind == "long":
        thumb = render.thumbnail(work / "video_noaudio.mp4", script.get("thumbnail_text") or script["title"], OUT / f"{slug}_thumb.jpg", rng)

    chap = chapters(script["scenes"], timings, total) if kind == "long" else ""
    title = script["title"].strip()
    if kind == "short" and "#shorts" not in title.lower():
        title = f"{title[:88]} #shorts"
    meta = {"title": title, "description": build_description(cfg, kind, script, chap, history),
            "tags": script.get("tags", []), "topic": script["topic"], "style": script["style"],
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
                              "topic": script["topic"], "style": script["style"], "youtube_id": yt_id})
    save_history(history) if not offline else None
    shutil.rmtree(work, ignore_errors=True)
    return video


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=["short", "long"], default="short")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--offline-test", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
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
