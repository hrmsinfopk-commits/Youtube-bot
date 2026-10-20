"""Text-to-speech per scene: Microsoft Edge neural voices (free), gTTS fallback.
Also returns word timings so captions stay exactly in sync with the voice."""
import asyncio
import base64
import random
import re
import subprocess
import time

import requests

from .common import duration, log, run, secret

GTTS_LANG = {"urdu": "ur", "hindi": "hi", "english": "en"}
FEMALE = {"ur-PK-UzmaNeural", "ur-IN-GulNeural", "hi-IN-SwaraNeural", "en-US-AvaNeural",
          "en-US-AriaNeural", "en-US-JennyNeural", "en-GB-SoniaNeural"}

# extra audio processing per channel style
VOICE_FX = {
    None: "",
    "horror": ",lowpass=f=7500,aecho=0.8:0.6:70|140:0.18|0.10",
}


async def _edge(text, voice, rate, pitch, path):
    """Save MP3 and collect word boundaries [(start_sec, end_sec)]."""
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    except TypeError:  # older edge-tts
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    words = []
    with open(path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                st = chunk["offset"] / 1e7
                words.append((st, st + chunk["duration"] / 1e7))
    return words


def _voices(cfg, gender=None):
    lang = cfg["channel"]["language"]
    v = cfg["voices"][lang]
    if isinstance(v, dict):
        pool = v.get(gender) or (v.get("male", []) + v.get("female", []))
    else:
        pool = [x for x in v if (x in FEMALE) == (gender == "female")] if gender in ("male", "female") else v
    return pool or (list(v) if not isinstance(v, dict) else v.get("male", []) + v.get("female", []))


def edge_fallback(cfg, vsettings):
    lo, hi = cfg.get("voice_pitch", [-4, 4])
    return {"engine": "edge", "voice": random.choice(_voices(cfg, vsettings.get("gender"))),
            "rate": f"{random.randint(*cfg.get('voice_rate', [4, 12])):+d}%",
            "pitch": f"{random.randint(lo, hi):+d}Hz"}


def pick_voice(cfg, gender=None):
    """Voice matching the narrator's gender + slight random speed/pitch so every video sounds different."""
    tts = cfg.get("tts", {})
    if tts.get("engine") == "gemini" and secret("GEMINI_API_KEY"):
        pool = tts.get("voices", {})
        names = pool.get(gender) if gender in ("male", "female") else (pool.get("male", []) + pool.get("female", []))
        if names:
            g = gender or ("female" if names[0] in pool.get("female", []) else "male")
            return {"engine": "gemini", "voice": random.choice(names), "gender": g, "style": tts["style"]}
    lo, hi = cfg.get("voice_pitch", [-4, 4])
    return {"engine": "edge", "gender": gender,
        "voice": random.choice(_voices(cfg, gender)),
        "rate": f"{random.randint(*cfg.get('voice_rate', [4, 12])):+d}%",
        "pitch": f"{random.randint(lo, hi):+d}Hz",
    }


# ------------------------------------------------------------------ Gemini TTS (natural, directable voice)
GEMINI_TTS_API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _gemini_tts_call(cfg, text, voice_name, style, vsettings=None):
    tts = cfg["tts"]
    last = None
    models = list(tts.get("models", ["gemini-3.1-flash-tts-preview"]))
    locked = (vsettings or {}).get("tts_model")
    for attempt in range(5):
        # once a model has spoken part of this video, keep using it so the voice sounds the same throughout;
        # only switch if it keeps failing (attempt >= 3)
        order = [locked] if locked and attempt < 3 else models
        for model in order:
            body = {"contents": [{"parts": [{"text": f"{style}:\n\n{text}"}]}],
                    "generationConfig": {"responseModalities": ["AUDIO"],
                                         "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}}}}
            try:
                r = requests.post(GEMINI_TTS_API.format(model=model), json=body, timeout=300,
                                  headers={"x-goog-api-key": secret("GEMINI_API_KEY")})
                if r.status_code != 200:
                    raise RuntimeError(f"{model}: HTTP {r.status_code} {r.text[:150]}")
                cand = (r.json().get("candidates") or [{}])[0]
                if "content" not in cand:
                    raise RuntimeError(f"{model}: no audio (finishReason={cand.get('finishReason')})")
                part = cand["content"]["parts"][0]
                pcm = base64.b64decode(part["inlineData"]["data"])
                if len(pcm) < 24000:
                    raise RuntimeError(f"{model}: empty audio")
                log(f"Gemini TTS OK ({model}, {voice_name})")
                if vsettings is not None:
                    vsettings["tts_model"] = model
                return pcm
            except Exception as e:  # noqa: BLE001
                last = e
                log("Gemini TTS error:", str(e)[:160].replace("\n", " "))
        time.sleep(35)
    raise RuntimeError(f"Gemini TTS failed: {last}")


def _silences(wav):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af", "silencedetect=n=-38dB:d=0.16",
                        "-f", "null", "-"], capture_output=True, text=True)
    st = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", r.stderr)]
    en = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", r.stderr)]
    return [((a + b) / 2) for a, b in zip(st, en)]


def _split_points(total, weights, sil):
    """Estimated scene boundaries (by text length) snapped to the nearest real pause in the audio."""
    cum, acc = [], 0
    for w in weights[:-1]:
        acc += w
        cum.append(total * acc / sum(weights))
    pts, prev = [], 0.0
    for est in cum:
        near = [x for x in sil if abs(x - est) <= 1.6 and x > prev + 0.4]
        p = min(near, key=lambda x: abs(x - est)) if near else max(est, prev + 0.4)
        pts.append(p)
        prev = p
    return pts


def _gemini_scenes(cfg, scenes, workdir, vsettings):
    """Narrate scenes in a few large chunks (fewer API calls, more natural flow), then cut per scene."""
    max_words = cfg["tts"].get("chunk_words", 140)
    chunks, cur, n = [], [], 0
    for i, s in enumerate(scenes):
        w = len(s["text"].split())
        if cur and n + w > max_words:
            chunks.append(cur)
            cur, n = [], 0
        cur.append(i)
        n += w
    if cur:
        chunks.append(cur)
    pieces = {}
    for ci, idxs in enumerate(chunks):
        pcm = _gemini_tts_call(cfg, "\n\n".join(scenes[i]["text"] for i in idxs),
                               vsettings["voice"], vsettings["style"], vsettings)
        raw = workdir / f"gtts_{ci:02d}.pcm"
        raw.write_bytes(pcm)
        wav = workdir / f"gtts_{ci:02d}.wav"
        run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw), str(wav)])
        total = duration(wav)
        pts = _split_points(total, [max(1, len(scenes[i]["text"])) for i in idxs], _silences(wav))
        bounds = [0.0] + pts + [total]
        for k, i in enumerate(idxs):
            pieces[i] = (wav, bounds[k], bounds[k + 1])
    return pieces


_WHISPER = {}


def align_words(cfg, wavs):
    """Real word timings for each scene WAV using faster-whisper (free, runs on the GitHub machine).
    Gemini voices don't report word timings; without this, captions drift a little inside each scene."""
    if not cfg.get("caption_align", True):
        return None
    try:
        from faster_whisper import WhisperModel
        lang = {"english": "en", "urdu": "ur", "hindi": "hi"}[cfg["channel"]["language"]]
        name = "base.en" if lang == "en" else "small"
        if name not in _WHISPER:
            _WHISPER[name] = WhisperModel(name, device="cpu", compute_type="int8")
        model = _WHISPER[name]
        out = []
        for w in wavs:
            segs, _ = model.transcribe(str(w), language=lang, word_timestamps=True, beam_size=1,
                                       condition_on_previous_text=False)
            out.append([(float(x.start), float(x.end)) for sg in segs for x in (sg.words or [])])
        log(f"Captions aligned to the voice ({sum(len(x) for x in out)} words)")
        return out
    except Exception as e:  # noqa: BLE001
        log("Caption alignment unavailable, using estimated timing:", str(e)[:120])
        return None


def synth_scenes(cfg, scenes, workdir, vsettings):
    """One normalised WAV per scene. Returns list of (path, seconds, word_times)."""
    lang = cfg["channel"]["language"]
    fx = VOICE_FX.get(cfg.get("voice_fx"), "")
    out = []
    if vsettings.get("engine") == "gemini":
        try:
            pieces = _gemini_scenes(cfg, scenes, workdir, vsettings)
            for i in range(len(scenes)):
                src, a, b = pieces[i]
                wav = workdir / f"voice_{i:03d}.wav"
                run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af",
                     f"atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,"
                     "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                     "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                     f"loudnorm=I=-16:TP=-1.5:LRA=11{fx}", "-ar", "44100", "-ac", "2", str(wav)])
                out.append((wav, duration(wav), []))
            aligned = align_words(cfg, [o[0] for o in out])
            if aligned and len(aligned) == len(out):
                out = [(w, d, wt) for (w, d, _), wt in zip(out, aligned)]
            return out
        except Exception as e:  # noqa: BLE001
            log("Gemini voice failed, switching whole video to Microsoft voice:", str(e)[:150])
            vsettings.update(edge_fallback(cfg, vsettings))
            out = []
    for i, s in enumerate(scenes):
        mp3 = workdir / f"voice_{i:03d}.mp3"
        wav = workdir / f"voice_{i:03d}.wav"
        ok, words = False, []
        base = int(vsettings["rate"].strip("%+").replace("-", "")) * (-1 if vsettings["rate"].startswith("-") else 1)
        rate = base + {"fast": 8, "normal": 0, "slow": -10}.get(s.get("pace", "normal"), 0)
        for attempt in range(3):
            try:
                words = asyncio.run(_edge(s["text"], vsettings["voice"], f"{rate:+d}%", vsettings["pitch"], mp3))
                ok = mp3.exists() and mp3.stat().st_size > 1000
                if ok:
                    break
            except Exception as e:  # noqa: BLE001
                log(f"edge-tts error scene {i}: {str(e)[:120]}")
        if not ok:
            from gtts import gTTS
            log(f"Scene {i}: using gTTS fallback")
            gTTS(s["text"], lang=GTTS_LANG[lang]).save(str(mp3))
            words = []
        # trim leading/trailing silence, normalise, optional style fx, 44.1k stereo
        run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-af",
             "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
             "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
             f"loudnorm=I=-16:TP=-1.5:LRA=11{fx}",
             "-ar", "44100", "-ac", "2", str(wav)])
        d = duration(wav)
        if words:  # leading silence was trimmed -> shift so first word starts at ~0
            shift = max(0.0, words[0][0] - 0.03)
            words = [(max(0.0, a - shift), min(d, b - shift)) for a, b in words]
        out.append((wav, d, words))
    return out
