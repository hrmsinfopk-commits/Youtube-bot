"""Original background music + sound effects, generated in code (no copyright),
plus optional CC0 music from Freesound.org (needs free FREESOUND_API_KEY)."""
import random
import wave

import numpy as np
import requests
from scipy.signal import butter, lfilter, sosfilt

from .common import log, secret

SR = 44100

# mood -> (scale, tempo range, brightness, layers)
MOODS = {
    "suspense":   ("minor", (70, 90), 900, ["pad", "sub", "pulse", "tick"]),
    "mysterious": ("minor", (60, 80), 1200, ["pad", "sub", "bell"]),
    "dark":       ("phrygian", (55, 75), 700, ["pad", "sub", "drone"]),
    "epic":       ("minor", (85, 105), 1600, ["pad", "sub", "pulse", "drum"]),
    "uplifting":  ("major", (90, 115), 2200, ["pad", "sub", "bell", "pulse"]),
    "calm":       ("major", (60, 75), 1400, ["pad", "bell"]),
    "horror":     ("phrygian", (50, 65), 550, ["pad", "sub", "drone", "tick", "bell"]),
}
SCALES = {"minor": [0, 2, 3, 5, 7, 8, 10], "major": [0, 2, 4, 5, 7, 9, 11],
          "phrygian": [0, 1, 3, 5, 7, 8, 10]}
PROGS = {"minor": [[0, 5, 2, 6], [0, 3, 5, 4], [0, 6, 5, 6], [0, 5, 3, 4], [0, 2, 5, 4]],
         "major": [[0, 4, 5, 3], [0, 5, 3, 4], [3, 4, 0, 5], [0, 3, 4, 4], [5, 3, 0, 4]],
         "phrygian": [[0, 1, 0, 6], [0, 1, 5, 1], [0, 6, 1, 0]]}


def _hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _saw(f, t, rng):
    ph = rng.random()
    return 2 * ((f * t + ph) % 1.0) - 1


def _lp(x, cutoff):
    sos = butter(2, min(cutoff, SR / 2 - 100) / (SR / 2), "low", output="sos")
    return sosfilt(sos, x)


def _chord_notes(root, scale, degree):
    sc = SCALES[scale]
    notes = []
    for k in (0, 2, 4):
        d = degree + k
        notes.append(root + sc[d % 7] + 12 * (d // 7))
    return notes


def make_music(path, seconds, mood="suspense", seed=None):
    """Write an original stereo WAV of `seconds` length."""
    rng = random.Random(seed)
    nrng = np.random.default_rng(rng.randint(0, 10**9))
    scale, (tlo, thi), bright, layers = MOODS.get(mood, MOODS["suspense"])
    tempo = rng.uniform(tlo, thi)
    beat = 60.0 / tempo
    bar = beat * 4
    root = rng.randint(45, 52)                       # A2..E3 area, random key
    prog = rng.choice(PROGS[scale])
    prog_b = rng.choice(PROGS[scale])
    seconds = max(5.0, seconds + 1.0)
    n_total = int(seconds * SR)
    out = wave.open(str(path), "wb")
    out.setnchannels(2)
    out.setsampwidth(2)
    out.setframerate(SR)
    written, ci, bars_per_chord = 0, 0, 2
    seg_len = bar * bars_per_chord
    while written < n_total:
        section = prog if (ci // 8) % 2 == 0 else prog_b
        deg = section[ci % len(section)]
        n = min(int(seg_len * SR), n_total - written)
        t = np.arange(n) / SR
        notes = _chord_notes(root + 12, scale, deg)
        L = np.zeros(n)
        R = np.zeros(n)
        intensity = min(1.0, 0.55 + 0.45 * (written / n_total) * 1.3)  # slow build over the video
        if "pad" in layers:
            pad_l = sum(_saw(_hz(m) * 1.003, t, rng) + _saw(_hz(m) * 0.997, t, rng) for m in notes)
            pad_r = sum(_saw(_hz(m) * 1.002, t, rng) + _saw(_hz(m) * 0.998, t, rng) for m in notes)
            env = np.minimum(1, t / 0.8) * np.minimum(1, (t[-1] - t + 1e-3) / 0.6)
            L += _lp(pad_l, bright) * env * 0.09
            R += _lp(pad_r, bright) * env * 0.09
        if "sub" in layers:
            s = np.sin(2 * np.pi * _hz(notes[0] - 24) * t) * 0.22 * np.minimum(1, t / 0.2)
            L += s
            R += s
        if "drone" in layers:
            d = _lp(nrng.standard_normal(n), 300) * 0.25 + np.sin(2 * np.pi * _hz(root - 12) * t) * 0.12
            L += d
            R += d * 0.9
        if "pulse" in layers:
            step = beat / 2
            k = np.floor(t / step)
            local = t - k * step
            f = _hz(notes[0])
            pl = _lp(_saw(f, t, rng), bright * 1.4) * np.exp(-local * 9) * 0.10 * intensity
            L += pl
            R += pl * 0.8
        if "tick" in layers:
            k = np.floor(t / beat)
            local = t - k * beat
            tick = _lp(nrng.standard_normal(n), 6000) * np.exp(-local * 60) * 0.05
            L += tick * 0.7
            R += tick
        if "drum" in layers:
            k = np.floor(t / (beat * 2))
            local = t - k * beat * 2
            kick = np.sin(2 * np.pi * (45 + 80 * np.exp(-local * 25)) * local) * np.exp(-local * 6) * 0.35 * intensity
            L += kick
            R += kick
        if "bell" in layers:
            for _ in range(rng.randint(2, 5)):
                st = rng.uniform(0, max(0.01, t[-1] - 1.0))
                m = rng.choice(notes) + 24
                lt = np.clip(t - st, 0, None)
                b = np.sin(2 * np.pi * _hz(m) * lt) * np.exp(-lt * 2.5) * (t >= st) * 0.06
                pan = rng.uniform(0.3, 1.0)
                L += b * pan
                R += b * (1.3 - pan)
        # fade in/out of whole track
        g0 = written / SR
        gt = g0 + t
        fade = np.minimum(1, gt / 2.0) * np.minimum(1, (seconds - gt) / 2.5)
        st = np.stack([L * fade, R * fade], axis=1)
        st = np.tanh(st * 1.2) * 0.8
        out.writeframes((st * 32767).astype("<i2").tobytes())
        written += n
        ci += 1
    out.close()
    log(f"Music generated: mood={mood}, tempo={tempo:.0f}")
    return path


def freesound_music(path, seconds, mood):
    """Optional: CC0 (no-attribution, monetization-safe) music loop from Freesound."""
    key = secret("FREESOUND_API_KEY")
    if not key:
        return None
    q = {"suspense": "suspense music", "mysterious": "mysterious ambient music", "dark": "dark ambient music",
         "epic": "cinematic epic music", "uplifting": "uplifting background music", "calm": "calm ambient music",
         "horror": "horror ambient drone"}.get(mood, "ambient music")
    params = {"query": q, "page_size": 40, "sort": "rating_desc",
              "filter": f'license:"Creative Commons 0" duration:[{int(max(20, min(seconds, 90)))} TO 900]',
              "fields": "id,name,previews,duration,license,tags"}
    try:
        res = []
        for ep in ("https://freesound.org/apiv2/search/", "https://freesound.org/apiv2/search/text/"):
            r = requests.get(ep, timeout=30, params=params, headers={"Authorization": f"Token {key}"})
            if r.status_code == 200:
                musical = ("music", "soundtrack", "ambient", "background", "score", "cinematic", "loop", "atmosphere")
                res = [x for x in r.json().get("results", []) if ("Creative Commons 0" in x.get("license", "")
                       or x.get("license", "").endswith("/zero/1.0/"))
                       and any(m in (x.get("name", "") + " " + " ".join(x.get("tags") or [])).lower() for m in musical)
                       and not any(b in (x.get("name", "") + " " + " ".join(x.get("tags") or [])).lower()
                                  for b in ("chord", " to ", "note", "sample", "stinger", "game", "8bit", "chiptune", "arcade"))]
                break
            log(f"Freesound {ep.split('/')[-2]}: HTTP {r.status_code}")
        if not res:
            return None
        pick = random.choice(res[:12])
        url = pick["previews"]["preview-hq-mp3"]
        with open(path, "wb") as f:
            f.write(requests.get(url, timeout=60).content)
        log(f"Freesound CC0 music: {pick['name']} (id {pick['id']})")
        return path
    except Exception as e:  # noqa: BLE001
        log("Freesound failed:", str(e)[:120])
        return None


def freesound_sfx(path, query, max_dur=8, min_dur=0.3):
    """CC0 sound effect / ambience from Freesound. Returns a WAV path or None."""
    key = secret("FREESOUND_API_KEY")
    if not key or not query:
        return None
    params = {"query": query, "page_size": 20, "sort": "rating_desc",
              "filter": f'license:"Creative Commons 0" duration:[{min_dur} TO {max_dur}]',
              "fields": "id,name,previews,license,tags"}
    words = [w for w in query.lower().split() if len(w) > 2]
    try:
        for ep in ("https://freesound.org/apiv2/search/", "https://freesound.org/apiv2/search/text/"):
            r = requests.get(ep, timeout=30, params=params, headers={"Authorization": f"Token {key}"})
            if r.status_code == 200:
                bad = ("robot", "game", "cartoon", "8bit", "8-bit", "retro", "funny", "comic", "toy", "arcade", "synth", "laser",
                       "chainsaw", "fart", "bottle", "kitchen")

                def ok(x):
                    text = (x.get("name", "") + " " + " ".join(x.get("tags") or [])).lower()
                    return (("Creative Commons 0" in x.get("license", "") or x.get("license", "").endswith("/zero/1.0/"))
                            and not any(b in text for b in bad) and all(w in text for w in words))
                res = [x for x in r.json().get("results", []) if ok(x)]
                if not res:
                    return None
                pick = random.choice(res[:6])
                mp3 = str(path) + ".mp3"
                with open(mp3, "wb") as f:
                    f.write(requests.get(pick["previews"]["preview-hq-mp3"], timeout=60).content)
                import subprocess
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-ac", "1", "-ar", str(SR),
                                "-af", "loudnorm=I=-20:TP=-2", str(path)], check=True)
                log(f"Freesound CC0 sound '{query}': {pick['name']} (id {pick['id']})")
                return path
    except Exception as e:  # noqa: BLE001
        log(f"Freesound sound '{query}' failed:", str(e)[:100])
    return None


def _load_wav_mono(path):
    with wave.open(str(path), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
        if w.getnchannels() == 2:
            data = data.reshape(-1, 2).mean(axis=1)
    return data


# ------------------------------------------------------------------ sound effects
def _bandsweep(n, f0, f1, nrng):
    noise = nrng.standard_normal(n)
    out = np.zeros(n)
    chunks = 12
    edges = np.linspace(0, n, chunks + 1).astype(int)
    for i in range(chunks):
        fc = f0 * (f1 / f0) ** (i / (chunks - 1))
        lo, hi = max(40, fc * 0.6), min(SR / 2 - 200, fc * 1.6)
        b, a = butter(2, [lo / (SR / 2), hi / (SR / 2)], "band")
        seg = lfilter(b, a, noise)[edges[i]:edges[i + 1]]
        out[edges[i]:edges[i + 1]] = seg
    return out


def sfx(kind, nrng):
    if kind == "whoosh":
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        x = _bandsweep(n, 400, 4000, nrng) * np.sin(np.pi * t / t[-1]) ** 2
        return x / (np.abs(x).max() + 1e-9) * 0.35
    if kind == "riser":
        n = int(1.6 * SR)
        t = np.arange(n) / SR
        x = _bandsweep(n, 300, 6000, nrng) * (t / t[-1]) ** 2
        x += np.sin(2 * np.pi * (200 * t + 300 * t ** 2)) * (t / t[-1]) ** 2 * 0.3
        return x / (np.abs(x).max() + 1e-9) * 0.30
    if kind == "boom":
        n = int(1.4 * SR)
        t = np.arange(n) / SR
        f = 40 + 60 * np.exp(-t * 8)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
        x += _lp(nrng.standard_normal(n), 500) * np.exp(-t * 10) * 0.6
        return x / (np.abs(x).max() + 1e-9) * 0.55
    if kind == "thud":       # low, dull hit for scene changes in horror
        n = int(0.9 * SR)
        t = np.arange(n) / SR
        f = 32 + 40 * np.exp(-t * 14)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5)
        x += _lp(nrng.standard_normal(n), 220) * np.exp(-t * 18) * 0.5
        return x / (np.abs(x).max() + 1e-9) * 0.45
    if kind == "heartbeat":  # lub-dub, speeding up over ~3 s
        n = int(3.2 * SR)
        x = np.zeros(n)
        beat_t, gap = 0.0, 0.85
        while beat_t < 3.0:
            for off, amp in ((0.0, 1.0), (0.18, 0.7)):
                st = int((beat_t + off) * SR)
                m = min(int(0.25 * SR), n - st)
                if m <= 0:
                    continue
                tt = np.arange(m) / SR
                x[st:st + m] += amp * np.sin(2 * np.pi * (48 + 30 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 22)
            beat_t += gap
            gap = max(0.45, gap * 0.86)
        x *= np.linspace(0.5, 1.0, n)
        return x / (np.abs(x).max() + 1e-9) * 0.55
    if kind == "sting":      # dissonant stab for the scare / twist
        n = int(1.8 * SR)
        t = np.arange(n) / SR
        env = np.minimum(1, t / 0.01) * np.exp(-t * 2.2)
        x = sum(np.sin(2 * np.pi * f0 * t + nrng.random() * 6) for f0 in (622, 659, 698, 932, 988))
        x += _bandsweep(n, 2500, 900, nrng) * 0.8
        x += np.sin(2 * np.pi * (60 + 50 * np.exp(-t * 10)) * t) * 1.5 * np.exp(-t * 4)
        x *= env
        return x / (np.abs(x).max() + 1e-9) * 0.5
    raise ValueError(kind)


def make_sfx_track(path, seconds, events, seed=None):
    """events: list of (time_seconds, kind). Writes stereo WAV."""
    nrng = np.random.default_rng(seed)
    n = int((seconds + 2) * SR)
    track = np.zeros(n, dtype=np.float32)
    cache = {}
    for ev in events:
        t0, kind = ev[0], ev[1]
        if kind == "file":            # real recorded sound effect
            s = _load_wav_mono(ev[2]) * float(ev[3] if len(ev) > 3 else 0.5)
        elif kind == "ambience":      # loop under the whole video
            a = _load_wav_mono(ev[2]) * float(ev[3] if len(ev) > 3 else 0.2)
            if len(a) > SR:
                reps = int(np.ceil(n / len(a)))
                loop = np.tile(a, reps)[:n]
                fade = np.minimum(1, np.arange(n) / (2 * SR)) * np.minimum(1, (n - np.arange(n)) / (2 * SR))
                track += (loop * fade).astype(np.float32)
            continue
        else:
            if kind not in cache:
                cache[kind] = sfx(kind, nrng).astype(np.float32)
            s = cache[kind]
        start = int(max(0, t0) * SR)
        end = min(n, start + len(s))
        if end > start:
            track[start:end] += s[:end - start]
    track = np.tanh(track)
    st = np.stack([track, track], axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((st * 32767).astype("<i2").tobytes())
    return path
