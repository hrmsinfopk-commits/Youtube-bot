"""Video assembly with ffmpeg: footage cuts with motion, voice + ducked music, animated captions."""
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import audiofx
from .common import FONTS, MUSIC, duration, log, run

FPS = 30
SIZES = {"short": (1080, 1920), "long": (1920, 1080)}
PALETTES = [  # (highlight, outline) in RGB, chosen randomly per video
    ((255, 214, 0), (0, 0, 0)), ((0, 229, 255), (0, 0, 0)), ((57, 255, 20), (0, 0, 0)),
    ((255, 72, 120), (0, 0, 0)), ((255, 145, 0), (0, 0, 0)), ((180, 120, 255), (0, 0, 0)),
]


# ---------------------------------------------------------------- footage clips
HORROR_PALETTES = [((215, 25, 35), (0, 0, 0)), ((240, 60, 50), (0, 0, 0)), ((180, 15, 20), (0, 0, 0))]


def _palettes(cfg):
    vis = cfg.get("visual", {})
    if vis.get("palette") == "horror":
        return HORROR_PALETTES
    if vis.get("brand_color"):   # one fixed channel colour = recognisable look
        return [(tuple(vis["brand_color"]), (0, 0, 0))]
    return PALETTES


def _clip_filter(W, H, seg, rng, grade=None):
    z = rng.uniform(1.06, 1.16)
    sw, sh = int(W * z) // 2 * 2, int(H * z) // 2 * 2
    mode = rng.choice(["lr", "rl", "tb", "bt", "c"])
    dx, dy = f"(iw-{W})", f"(ih-{H})"
    x = {"lr": f"{dx}*t/{seg:.3f}", "rl": f"{dx}*(1-t/{seg:.3f})"}.get(mode, f"{dx}/2")
    y = {"tb": f"{dy}*t/{seg:.3f}", "bt": f"{dy}*(1-t/{seg:.3f})"}.get(mode, f"{dy}/2")
    if grade == "dark":
        z = rng.uniform(1.04, 1.09)                       # slow, creeping movement
        sw, sh = int(W * z) // 2 * 2, int(H * z) // 2 * 2
        sat, con, bri = rng.uniform(0.35, 0.6), rng.uniform(1.1, 1.2), rng.uniform(-0.10, -0.06)
        extra = ",vignette=PI/4,colorbalance=bs=0.06:bm=0.04:rs=-0.03"
    else:
        sat, con, bri = rng.uniform(1.0, 1.18), rng.uniform(1.0, 1.08), rng.uniform(-0.03, 0.02)
        extra = ""
    return (f"scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={W}:{H}:{x}:{y},"
            f"setsar=1,fps={FPS},eq=saturation={sat:.2f}:contrast={con:.2f}:brightness={bri:.3f}"
            f"{extra},format=yuv420p")


def make_clip(src, kind, seg, W, H, out, rng, grade=None):
    enc = ["-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-r", str(FPS),
           "-pix_fmt", "yuv420p", str(out)]
    if kind == "graphic":   # our own animated graphic: play from the start, hold the last frame
        run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-t", f"{seg:.3f}",
             "-vf", f"scale={W}:{H},tpad=stop_mode=clone:stop_duration=30,fps={FPS},format=yuv420p"] + enc)
        return
    if kind == "photo":
        frames = int(seg * FPS) + 1
        zs = rng.uniform(0.0005, 0.0010)
        mode = rng.choice(["in", "out", "pan"])
        if mode == "in":
            zexpr, xexpr = f"min(zoom+{zs:.5f},1.25)", "iw/2-(iw/zoom/2)"
        elif mode == "out":
            zexpr, xexpr = f"if(eq(on,0),1.2,max(zoom-{zs:.5f},1.0))", "iw/2-(iw/zoom/2)"
        else:
            zexpr = "1.15"
            xexpr = f"(iw-iw/zoom)*on/{frames}" if rng.random() < 0.5 else f"(iw-iw/zoom)*(1-on/{frames})"
        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan=z='{zexpr}':x='{xexpr}':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={W}x{H}:fps={FPS},setsar=1"
              + (",eq=saturation=0.55:contrast=1.12:brightness=-0.07,vignette=PI/4" if grade == "dark" else "")
              + ",format=yuv420p")
        run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(src), "-t", f"{seg:.3f}",
             "-vf", vf] + enc)
        return
    try:
        cd = duration(src)
    except Exception:  # noqa: BLE001
        cd = seg
    pre = []
    if cd > seg + 0.5:
        pre = ["-ss", f"{rng.uniform(0, cd - seg - 0.3):.2f}"]
    else:
        pre = ["-stream_loop", "-1"]
    run(["ffmpeg", "-y", "-v", "error"] + pre + ["-i", str(src), "-t", f"{seg:.3f}",
         "-vf", _clip_filter(W, H, seg, rng, grade)] + enc)


# ---------------------------------------------------------------- captions (ASS)
def _ass_color(rgb):
    r, g, b = rgb
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _ass_time(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _chunk_times(t0, dur, n_words, chunks, word_times):
    """Start/end time for each caption chunk. Uses real word timings from the TTS when available,
    so each chunk appears exactly when its first word is spoken and stays until the next one."""
    nu = len(word_times)
    starts, a = [], 0
    for c in chunks:
        if nu and n_words:
            starts.append(t0 + word_times[min(nu - 1, round(a * nu / n_words))][0])
        else:
            starts = None
            break
        a += len(c)
    if starts is None:  # proportional fallback (no word timings)
        total = sum(len(" ".join(c)) for c in chunks) or 1
        starts, t = [], t0
        for c in chunks:
            starts.append(t)
            t += dur * len(" ".join(c)) / total
    starts[0] = t0
    for i in range(1, len(starts)):  # keep order strictly increasing
        starts[i] = max(starts[i], starts[i - 1] + 0.25)
    ends = starts[1:] + [max(starts[-1] + 0.3, t0 + dur)]
    return [[st, en] for st, en in zip(starts, ends)]


def build_ass(kind, cfg, scenes, timings, path, rng, hook_text="", word_times=None, concept_scenes=()):
    W, H = SIZES[kind]
    word_times = word_times or [[] for _ in scenes]
    story = cfg.get("visual", {}).get("caption_style") == "story"
    native = cfg["channel"]["captions"] == "native" and cfg["channel"]["language"] != "english"
    lang = cfg["channel"]["language"]
    if native and lang == "urdu":
        font, size = "Noto Nastaliq Urdu", (96 if kind == "short" else 66)
    elif native and lang == "hindi":
        font, size = "Noto Sans Devanagari", (108 if kind == "short" else 68)
    elif story:
        font, size = "Special Elite", (90 if kind == "short" else 64)
    else:
        font, size = "Anton", (150 if kind == "short" else 84)
    hi, _ = rng.choice(_palettes(cfg))
    white = (255, 255, 255)
    if kind == "short":
        align, marginv = 5, 0
        pos = f"\\pos({W // 2},{int(H * (0.70 if story else rng.uniform(0.62, 0.70)))})"
        words_per = (4, 6) if story else (2, 3)
    else:
        align, marginv, pos = 2, 70, ""
        words_per = (6, 9) if story else (4, 7)
    if story:
        hook_style = (f"Style: Hook,Special Elite,{120 if kind == 'short' else 96},{_ass_color((215, 25, 35))},"
                      f"&H000000FF,&H00000000,&H96000000,1,0,0,0,100,100,2,0,1,5,3,8,60,60,{int(H * 0.17)},1")
        cap_outline, cap_shadow = 4, 3
    else:
        hook_style = (f"Style: Hook,Anton,{150 if kind == 'short' else 110},&H00000000,&H000000FF,"
                      f"{_ass_color(hi)},{_ass_color(hi)},1,0,0,0,100,100,2,0,3,22,0,8,60,60,{int(H * 0.16)},1")
        cap_outline, cap_shadow = (7 if kind == "short" else 5), 3
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},{_ass_color(white)},&H000000FF,&H00000000,&H64000000,{0 if story else 1},0,0,0,100,100,1,0,1,{cap_outline},{cap_shadow},{align},70,70,{marginv},1
{hook_style}
Style: Card,Anton,{130 if kind == 'short' else 110},&H00FFFFFF,&H000000FF,&H00000000,{_ass_color(hi)},1,0,0,0,100,100,2,0,3,26,0,5,80,80,0,1
Style: Label,Anton,{34 if kind == 'short' else 30},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,3,8,0,9,30,30,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    hook = re.sub(r"[{}\\]", "", hook_text or "").upper().strip()
    if hook:
        if story:
            hook_anim = "{\\fad(400,300)}"
            hook_end = 2.8
        else:
            hook_anim = "{\\fscx40\\fscy40\\t(0,160,\\fscx108\\fscy108)\\t(160,260,\\fscx100\\fscy100)\\fad(0,200)}"
            hook_end = 2.3
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(hook_end)},Hook,,0,0,0,,{hook_anim}{hook}")
    for i, (sc, (t0, dur)) in enumerate(zip(scenes, timings)):
        card = "" if sc.get("graphic") else re.sub(r"[{}\\]", "", str(sc.get("on_screen") or "")).strip().upper()
        if card:   # big fact/number on screen for ~2.5 s
            cy = int(H * (0.38 if kind == "short" else 0.42))
            anim = "{\\pos(%d,%d)\\fscx60\\fscy60\\t(0,150,\\fscx105\\fscy105)\\t(150,230,\\fscx100\\fscy100)\\fad(0,250)}" % (W // 2, cy)
            lines.append(f"Dialogue: 2,{_ass_time(t0 + 0.1)},{_ass_time(t0 + min(dur, 2.6))},Card,,0,0,0,,{anim}{card}")
        if i in set(concept_scenes or ()):
            lines.append(f"Dialogue: 3,{_ass_time(t0)},{_ass_time(t0 + dur + 0.3)},Label,,0,0,0,,Concept illustration")
    for sc, (t0, dur), wt in zip(scenes, timings, word_times):
        text = (sc["text"] if native else sc["caption"]).strip()
        text = re.sub(r"[{}\\]", "", text)
        words = text.split()
        if not words:
            continue
        chunks, i = [], 0
        while i < len(words):
            n = rng.randint(*words_per)
            if len(words) - (i + n) == 1:  # never leave a single orphan word
                n += 1
            chunks.append(words[i:i + n])
            i += n
        for c, (st, en) in zip(chunks, _chunk_times(t0, dur, len(words), chunks, wt)):
            if story:
                col = f"{{\\c{_ass_color(hi)}}}" if sc.get("reveal") else ""
                lines.append(f"Dialogue: 0,{_ass_time(st)},{_ass_time(en)},Cap,,0,0,0,,"
                             f"{{{pos}\\fad(180,150)}}{col}{' '.join(c)}")
                continue
            if kind == "short" and not native:
                c = [w.upper() for w in c]
            k = max(range(len(c)), key=lambda j: len(c[j]))  # highlight the longest word
            parts = [(f"{{\\c{_ass_color(hi)}}}{w}{{\\c{_ass_color(white)}}}" if j == k else w)
                     for j, w in enumerate(c)]
            anim = "{\\fscx82\\fscy82\\t(0,110,\\fscx104\\fscy104)\\t(110,180,\\fscx100\\fscy100)}"
            lines.append(f"Dialogue: 0,{_ass_time(st)},{_ass_time(en)},Cap,,0,0,0,,"
                         f"{{{pos}}}{anim}{' '.join(parts)}")
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return hi


# ---------------------------------------------------------------- audio
def pick_music(work, total, mood, rng):
    """1) your own files in music/  2) Freesound CC0 (if key)  3) generated original music."""
    tracks = sorted([p for p in MUSIC.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")])
    if tracks:
        m = rng.choice(tracks)
        log("Music (own file):", m.name)
        return m
    fs = audiofx.freesound_music(work / "music_fs.mp3", total, mood, scary_ok=(mood == "horror"))
    if fs:
        return fs
    return audiofx.make_music(work / "music_gen.wav", total, mood, seed=rng.random())


def build_audio(voice, gaps, work, total, cfg, rng, mood="suspense", sfx_events=()):
    """Concatenate scene voices with gaps, mix in ducked background music and sound effects."""
    silence = {}
    lst = work / "audio_list.txt"
    with open(lst, "w") as f:
        for (wav, *_), g in zip(voice, gaps):
            f.write(f"file '{wav.resolve()}'\n")
            key = f"{g:.2f}"
            if key not in silence:
                sp = work / f"sil_{key}.wav"
                run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                     "anullsrc=r=44100:cl=stereo", "-t", key, "-c:a", "pcm_s16le", str(sp)])
                silence[key] = sp
            f.write(f"file '{silence[key].resolve()}'\n")
    narr = work / "narration.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:a", "pcm_s16le", str(narr)])
    music = pick_music(work, total, mood, rng)
    sfx = audiofx.make_sfx_track(work / "sfx.wav", total, list(sfx_events), seed=rng.randint(0, 10**6))
    vol = cfg["footage"].get("music_volume", 0.22)
    sfx_vol = cfg["footage"].get("sfx_volume", 0.6)
    mixed = work / "mixed.wav"
    fc = (f"[1:a]loudnorm=I=-18:TP=-2,aresample=44100,volume={vol:.3f},afade=t=in:d=1.0,afade=t=out:st={max(total - 2.5, 0):.2f}:d=2.5[m];"
          f"[0:a]asplit=2[v][sc];"
          f"[m][sc]sidechaincompress=threshold=0.04:ratio=6:attack=30:release=500[duck];"
          f"[2:a]volume={sfx_vol}[fx];"
          f"[v][duck][fx]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.95[a]")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(narr), "-stream_loop", "-1", "-i", str(music),
         "-i", str(sfx), "-filter_complex", fc, "-map", "[a]", "-t", f"{total:.2f}",
         "-c:a", "pcm_s16le", str(mixed)])
    return mixed


# ---------------------------------------------------------------- main assembly
def assemble(kind, cfg, scenes, voice, media, work, out_path, rng, mood="suspense", hook_text="",
             scene_sounds=None, ambience=None, concept_scenes=()):
    """scenes: list; voice: [(wav, secs, word_times)]; media: per-scene list of (path, kind)."""
    W, H = SIZES[kind]
    vis = cfg.get("visual", {})
    story = vis.get("caption_style") == "story"
    pmin, pmax = cfg.get("pauses", [0.18, 0.35])
    gaps = [rng.uniform(pmin, pmax) for _ in voice]
    for i in range(len(scenes) - 1):
        if scenes[i + 1].get("reveal"):
            gaps[i] = cfg.get("reveal_pause", 0.75)   # dramatic silence before a reveal
    gaps[-1] = 1.2 if story else 0.8
    timings, t = [], 0.0
    for (_, d, *_), g in zip(voice, gaps):
        timings.append((t, d))
        t += d + g
    total = t
    seg_range = vis.get("shot_seconds") or ((1.8, 3.2) if kind == "short" else (3.0, 5.5))

    clips = []
    for si, ((t0, d), g) in enumerate(zip(timings, gaps)):
        items = media[si]
        remaining, k = d + g, 0
        while remaining > 0.05:
            seg = min(rng.uniform(*seg_range), remaining)
            if remaining - seg < 1.0 or items[k % len(items)][1] == "graphic":
                seg = remaining
            src, mkind = items[k % len(items)]
            out = work / f"clip_{len(clips):04d}.mp4"
            make_clip(src, mkind, seg, W, H, out, rng, vis.get("grade"))
            clips.append(out)
            remaining -= seg
            k += 1
    log(f"{len(clips)} clips rendered")
    log("Final render started")

    lst = work / "clips.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    silent = work / "video_noaudio.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)])

    # sound effects + zoom punches
    punches = []
    if story:  # horror: no whooshes; low hits, heartbeat building to a sting on the reveal
        events = [(0.0, "thud")]
        for i, (sc, (t0, _)) in enumerate(zip(scenes, timings)):
            if i == 0:
                continue
            if sc.get("reveal"):
                events += [(max(0, t0 - 3.2), "heartbeat"), (max(0, t0 - 0.05), "sting")]
                punches.append(t0)
            elif sc.get("chapter") or (kind == "short" and i % 3 == 0):
                events.append((max(0, t0 - 0.1), "thud"))
    else:
        events = [(0.0, "boom")]
        for i, (sc, (t0, _)) in enumerate(zip(scenes, timings)):
            if i == 0:
                continue
            if sc.get("reveal"):
                events += [(max(0, t0 - 1.6), "riser"), (t0, "boom")]
                punches.append(t0)
            elif kind == "short" or sc.get("chapter"):
                events.append((max(0, t0 - 0.2), "whoosh"))
    for i, ((t0, _), snd) in enumerate(zip(timings, scene_sounds or [])):
        if snd:
            events.append((t0 + 0.15, "file", snd, 0.55))
    if ambience:
        events.append((0.0, "ambience", ambience, cfg.get("footage", {}).get("ambience_volume", 0.22)))
    audio = build_audio(voice, gaps, work, total, cfg, rng, mood, events)
    ass = work / "captions.ass"
    hi = build_ass(kind, cfg, scenes, timings, ass, rng, hook_text, [v[2] if len(v) > 2 else [] for v in voice],
                   concept_scenes)

    chain = []
    if punches and kind == "short":   # zoompan over a whole long video is far too slow
        z = "+".join(f"between(it\\,{p:.2f}\\,{p + 0.4:.2f})*(1-(it-{p:.2f})/0.4)" for p in punches[:12])
        chain.append(f"zoompan=z='1+{0.05 if story else 0.08}*({z})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                     f":d=1:s={W}x{H}:fps={FPS}")
    if story and punches:  # brief flash on each reveal
        fl = "+".join(f"between(t\\,{p:.2f}\\,{p + 0.12:.2f})" for p in punches[:12])
        chain.append(f"eq=brightness='0.25*({fl})':eval=frame")
    if vis.get("grain"):
        chain.append(f"noise=alls={int(vis['grain'])}:allf=t")
    chain.append(f"subtitles={ass.resolve()}:fontsdir={FONTS.resolve()}")
    inputs = ["-i", str(silent), "-i", str(audio)]
    nxt = 2
    if kind == "short" and vis.get("progress_bar", True):   # progress bar keeps people watching
        bar_h = 12
        r, g, b = hi
        inputs += ["-f", "lavfi", "-i", f"color=c=0x{r:02X}{g:02X}{b:02X}:s={W}x{bar_h}:r={FPS}"]
        fc = (f"[0:v]{','.join(chain)}[base];"
              f"[base][{nxt}:v]overlay=x='-w+w*t/{total:.2f}':y=H-{bar_h}:eval=frame:shortest=1[b2];")
        nxt += 1
    else:
        fc = f"[0:v]{','.join(chain)}[b2];"
    if vis.get("watermark"):   # small channel logo = brand recognition
        from . import graphics
        lp = work / "logo.png"
        graphics.logo(int(W * (0.075 if kind == "short" else 0.045))).save(lp)
        inputs += ["-i", str(lp)]
        mx = int(W * 0.03)
        fc += f"[{nxt}:v]format=rgba,colorchannelmixer=aa=0.75[lg];[b2][lg]overlay=x={mx}:y={mx},"
    else:
        fc += "[b2]null,"
    fc += f"fade=t=in:st=0:d=0.2,fade=t=out:st={max(total - 0.6, 0):.2f}:d=0.6[v]"
    run(["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", fc,
         "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "fast" if kind == "short" else "veryfast", "-crf", "22",
         "-maxrate", "8M" if kind == "short" else "6M", "-bufsize", "16M",   # keeps files small (grain!)
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
         "-t", f"{total:.2f}", str(out_path)])
    log(f"Video ready: {out_path.name} ({total:.1f}s)")
    return timings, total


# ---------------------------------------------------------------- thumbnail
def _font(size):
    for p in [FONTS / "Anton-Regular.ttf", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def thumbnail(video, text, out, rng, at=None, tag=""):
    """Tomorrowly-style thumbnail: dramatic frame, dark left side, 2-3 big lines (last one in brand colour), tag, logo."""
    from . import graphics
    frame = out.with_suffix(".frame.jpg")
    at = at if at is not None else min(3.0, duration(video) / 3)
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", str(frame)])
    img = Image.open(frame).convert("RGB").resize((1280, 720))
    img = Image.blend(img, img.filter(ImageFilter.GaussianBlur(1.5)), 0.2)
    shade = Image.new("L", (1280, 720))
    sd = ImageDraw.Draw(shade)
    for x in range(1280):
        sd.line([(x, 0), (x, 720)], fill=int(215 * max(0, 1 - x / 820)))
    img = Image.composite(Image.new("RGB", (1280, 720), (5, 8, 20)), img, shade)
    d = ImageDraw.Draw(img)
    words = text.upper().split()
    lines, cur = [], ""
    for w in words:
        if len(cur + " " + w) > 9 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    lines = lines[:3]
    size = 150 if len(lines) <= 2 else 128
    f = graphics._font(size)
    y = 360 - (len(lines) * size * 1.0) / 2 - (30 if tag else 0)
    for i, line in enumerate(lines):
        d.text((54, y), line, font=f, fill=graphics.ACCENT if i == len(lines) - 1 else (245, 247, 250),
               stroke_width=8, stroke_fill=(0, 0, 0))
        y += size * 1.0
    if tag:
        lf = graphics._label_font(40)
        tw = d.textlength(tag.upper(), font=lf)
        d.rounded_rectangle([58, y + 30, 58 + tw + 44, y + 100], radius=14, fill=graphics.ACCENT2)
        d.text((80, y + 39), tag.upper(), font=lf, fill=(9, 13, 28))
    img = img.convert("RGBA")
    img.alpha_composite(graphics.logo(110), (1280 - 140, 30))
    img.convert("RGB").save(out, quality=93)
    frame.unlink(missing_ok=True)
    return out
