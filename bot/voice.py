"""Text-to-speech per scene: Microsoft Edge neural voices (free), gTTS fallback.
Also returns word timings so captions stay exactly in sync with the voice."""
import asyncio
import random

from .common import duration, log, run

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


def pick_voice(cfg, gender=None):
    """Voice matching the narrator's gender + slight random speed/pitch so every video sounds different."""
    lo, hi = cfg.get("voice_pitch", [-4, 4])
    return {
        "voice": random.choice(_voices(cfg, gender)),
        "rate": f"{random.randint(*cfg.get('voice_rate', [4, 12])):+d}%",
        "pitch": f"{random.randint(lo, hi):+d}Hz",
    }


def synth_scenes(cfg, scenes, workdir, vsettings):
    """One normalised WAV per scene. Returns list of (path, seconds, word_times)."""
    lang = cfg["channel"]["language"]
    fx = VOICE_FX.get(cfg.get("voice_fx"), "")
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
