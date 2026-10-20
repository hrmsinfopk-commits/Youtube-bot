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
def _clip_filter(W, H, seg, rng):
    z = rng.uniform(1.06, 1.16)
    sw, sh = int(W * z) // 2 * 2, int(H * z) // 2 * 2
    mode = rng.choice(["lr", "rl", "tb", "bt", "c"])
    dx, dy = f"(iw-{W})", f"(ih-{H})"
    x = {"lr": f"{dx}*t/{seg:.3f}", "rl": f"{dx}*(1-t/{seg:.3f})"}.get(mode, f"{dx}/2")
    y = {"tb": f"{dy}*t/{seg:.3f}", "bt": f"{dy}*(1-t/{seg:.3f})"}.get(mode, f"{dy}/2")
    sat, con, bri = rng.uniform(1.0, 1.18), rng.uniform(1.0, 1.08), rng.uniform(-0.03, 0.02)
    return (f"scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={W}:{H}:{x}:{y},"
            f"setsar=1,fps={FPS},eq=saturation={sat:.2f}:contrast={con:.2f}:brightness={bri:.3f},"
            f"format=yuv420p")


def make_clip(src, kind, seg, W, H, out, rng):
    enc = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS),
           "-pix_fmt", "yuv420p", str(out)]
    if kind == "photo":
        frames = int(seg * FPS) + 1
        zs = rng.uniform(0.0006, 0.0012)
        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan=z='min(zoom+{zs:.5f},1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={W}x{H}:fps={FPS},setsar=1,format=yuv420p")
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
         "-vf", _clip_filter(W, H, seg, rng)] + enc)


# ---------------------------------------------------------------- captions (ASS)
def _ass_color(rgb):
    r, g, b = rgb
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _ass_time(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def build_ass(kind, cfg, scenes, timings, path, rng, hook_text=""):
    W, H = SIZES[kind]
    native = cfg["channel"]["captions"] == "native" and cfg["channel"]["language"] != "english"
    lang = cfg["channel"]["language"]
    if native and lang == "urdu":
        font, size = "Noto Nastaliq Urdu", (96 if kind == "short" else 66)
    elif native and lang == "hindi":
        font, size = "Noto Sans Devanagari", (108 if kind == "short" else 68)
    else:
        font, size = "Anton", (150 if kind == "short" else 84)
    hi, _ = rng.choice(PALETTES)
    white = (255, 255, 255)
    if kind == "short":
        align, marginv = 5, 0
        pos = f"\\pos({W // 2},{int(H * rng.uniform(0.62, 0.70))})"
        words_per = (2, 3)
    else:
        align, marginv, pos = 2, 70, ""
        words_per = (4, 7)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},{_ass_color(white)},&H000000FF,&H00000000,&H64000000,1,0,0,0,100,100,1,0,1,{7 if kind == 'short' else 5},3,{align},60,60,{marginv},1
Style: Hook,Anton,{150 if kind == 'short' else 110},&H00000000,&H000000FF,{_ass_color(hi)},{_ass_color(hi)},1,0,0,0,100,100,2,0,3,22,0,8,60,60,{int(H * 0.16)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    hook = re.sub(r"[{}\\]", "", hook_text or "").upper().strip()
    if hook:
        hook_anim = "{\\fscx40\\fscy40\\t(0,160,\\fscx108\\fscy108)\\t(160,260,\\fscx100\\fscy100)\\fad(0,200)}"
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(2.3)},Hook,,0,0,0,,{hook_anim}{hook}")
    for sc, (t0, dur) in zip(scenes, timings):
        text = (sc["text"] if native else sc["caption"]).strip()
        text = re.sub(r"[{}\\]", "", text)
        words = text.split()
        if not words:
            continue
        chunks, i = [], 0
        while i < len(words):
            n = rng.randint(*words_per)
            chunks.append(words[i:i + n])
            i += n
        total = sum(len(" ".join(c)) for c in chunks) or 1
        t = t0
        for c in chunks:
            d = dur * len(" ".join(c)) / total
            if kind == "short" and not native:
                c = [w.upper() for w in c]
            # highlight the longest word of each chunk
            k = max(range(len(c)), key=lambda j: len(c[j]))
            parts = [(f"{{\\c{_ass_color(hi)}}}{w}{{\\c{_ass_color(white)}}}" if j == k else w)
                     for j, w in enumerate(c)]
            anim = "{\\fscx82\\fscy82\\t(0,110,\\fscx104\\fscy104)\\t(110,180,\\fscx100\\fscy100)}"
            lines.append(f"Dialogue: 0,{_ass_time(t)},{_ass_time(t + d)},Cap,,0,0,0,,"
                         f"{{{pos}}}{anim}{' '.join(parts)}")
            t += d
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
    fs = audiofx.freesound_music(work / "music_fs.mp3", total, mood)
    if fs:
        return fs
    return audiofx.make_music(work / "music_gen.wav", total, mood, seed=rng.random())


def build_audio(voice, gaps, work, total, cfg, rng, mood="suspense", sfx_events=()):
    """Concatenate scene voices with gaps, mix in ducked background music and sound effects."""
    silence = {}
    lst = work / "audio_list.txt"
    with open(lst, "w") as f:
        for (wav, _), g in zip(voice, gaps):
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
    vol = cfg["footage"].get("music_volume", 0.1) * (1.6 if str(music).endswith("music_gen.wav") else 1.0)
    sfx_vol = cfg["footage"].get("sfx_volume", 0.6)
    mixed = work / "mixed.wav"
    fc = (f"[1:a]volume={vol:.3f},afade=t=in:d=1.0,afade=t=out:st={max(total - 2.5, 0):.2f}:d=2.5[m];"
          f"[0:a]asplit=2[v][sc];"
          f"[m][sc]sidechaincompress=threshold=0.04:ratio=6:attack=30:release=500[duck];"
          f"[2:a]volume={sfx_vol}[fx];"
          f"[v][duck][fx]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.95[a]")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(narr), "-stream_loop", "-1", "-i", str(music),
         "-i", str(sfx), "-filter_complex", fc, "-map", "[a]", "-t", f"{total:.2f}",
         "-c:a", "pcm_s16le", str(mixed)])
    return mixed


# ---------------------------------------------------------------- main assembly
def assemble(kind, cfg, scenes, voice, media, work, out_path, rng, mood="suspense", hook_text=""):
    """scenes: list; voice: [(wav, secs)]; media: per-scene list of (path, kind)."""
    W, H = SIZES[kind]
    gaps = [rng.uniform(0.18, 0.35) for _ in voice]
    for i in range(len(scenes) - 1):
        if scenes[i + 1].get("reveal"):
            gaps[i] = 0.75          # dramatic pause before a reveal
    gaps[-1] = 0.8
    timings, t = [], 0.0
    for (_, d), g in zip(voice, gaps):
        timings.append((t, d))
        t += d + g
    total = t
    seg_range = (1.8, 3.2) if kind == "short" else (3.0, 5.5)

    clips = []
    for si, ((t0, d), g) in enumerate(zip(timings, gaps)):
        items = media[si]
        remaining, k = d + g, 0
        while remaining > 0.05:
            seg = min(rng.uniform(*seg_range), remaining)
            if remaining - seg < 1.0:
                seg = remaining
            src, mkind = items[k % len(items)]
            out = work / f"clip_{len(clips):04d}.mp4"
            make_clip(src, mkind, seg, W, H, out, rng)
            clips.append(out)
            remaining -= seg
            k += 1
    log(f"{len(clips)} clips rendered")

    lst = work / "clips.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    silent = work / "video_noaudio.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)])

    # sound effects + zoom punches
    events, punches = [(0.0, "boom")], []
    for i, (sc, (t0, _)) in enumerate(zip(scenes, timings)):
        if i == 0:
            continue
        if sc.get("reveal"):
            events += [(max(0, t0 - 1.6), "riser"), (t0, "boom")]
            punches.append(t0)
        elif kind == "short" or sc.get("chapter"):
            events.append((max(0, t0 - 0.2), "whoosh"))
    audio = build_audio(voice, gaps, work, total, cfg, rng, mood, events)
    ass = work / "captions.ass"
    hi = build_ass(kind, cfg, scenes, timings, ass, rng, hook_text)

    chain = []
    if punches:
        z = "+".join(f"between(it\\,{p:.2f}\\,{p + 0.4:.2f})*(1-(it-{p:.2f})/0.4)" for p in punches[:12])
        chain.append(f"zoompan=z='1+0.08*({z})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                     f":d=1:s={W}x{H}:fps={FPS}")
    chain.append(f"subtitles={ass.resolve()}:fontsdir={FONTS.resolve()}")
    inputs = ["-i", str(silent), "-i", str(audio)]
    if kind == "short":   # progress bar keeps people watching to the end
        bar_h = 12
        r, g, b = hi
        inputs += ["-f", "lavfi", "-i", f"color=c=0x{r:02X}{g:02X}{b:02X}:s={W}x{bar_h}:r={FPS}"]
        fc = (f"[0:v]{','.join(chain)}[base];"
              f"[base][2:v]overlay=x='-w+w*t/{total:.2f}':y=H-{bar_h}:eval=frame:shortest=1,")
    else:
        fc = f"[0:v]{','.join(chain)},"
    fc += f"fade=t=in:st=0:d=0.2,fade=t=out:st={max(total - 0.6, 0):.2f}:d=0.6[v]"
    run(["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", fc,
         "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "fast", "-crf", "21",
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


def thumbnail(video, text, out, rng, at=None):
    frame = out.with_suffix(".frame.jpg")
    at = at if at is not None else min(3.0, duration(video) / 3)
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", str(frame)])
    img = Image.open(frame).convert("RGB").resize((1280, 720))
    img = Image.blend(img, img.filter(ImageFilter.GaussianBlur(2)), 0.3)
    shade = Image.new("L", (1280, 720))
    ImageDraw.Draw(shade).rectangle([0, 0, 1280, 720], fill=0)
    for x in range(1280):
        ImageDraw.Draw(shade).line([(x, 0), (x, 720)], fill=int(200 * max(0, 1 - x / 900)))
    img = Image.composite(Image.new("RGB", (1280, 720), (0, 0, 0)), img, shade)
    d = ImageDraw.Draw(img)
    hi, _ = rng.choice(PALETTES)
    words = text.upper().split()
    lines, cur = [], ""
    for w in words:
        if len(cur + " " + w) > 11 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    size = 150 if len(lines) <= 2 else 115
    f = _font(size)
    y = 360 - (len(lines) * size * 1.05) / 2
    for i, line in enumerate(lines[:4]):
        d.text((60, y), line, font=f, fill=hi if i == len(lines) - 1 else (255, 255, 255),
               stroke_width=8, stroke_fill=(0, 0, 0))
        y += size * 1.05
    img.save(out, quality=92)
    frame.unlink(missing_ok=True)
    return out
