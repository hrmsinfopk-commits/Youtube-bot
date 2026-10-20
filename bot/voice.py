"""Text-to-speech per scene: Microsoft Edge neural voices (free), gTTS fallback."""
import asyncio
import random

from .common import duration, log, run

GTTS_LANG = {"urdu": "ur", "hindi": "hi", "english": "en"}


async def _edge(text, voice, rate, pitch, path):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(path))


def pick_voice(cfg):
    """Random voice + slight random speed/pitch so every video sounds a bit different."""
    lang = cfg["channel"]["language"]
    return {
        "voice": random.choice(cfg["voices"][lang]),
        "rate": f"+{random.randint(4, 12)}%",
        "pitch": f"{random.choice(['-', '+'])}{random.randint(0, 4)}Hz",
    }


def synth_scenes(cfg, scenes, workdir, vsettings):
    """Create one normalised WAV per scene; returns list of (path, seconds)."""
    lang = cfg["channel"]["language"]
    out = []
    for i, s in enumerate(scenes):
        mp3 = workdir / f"voice_{i:03d}.mp3"
        wav = workdir / f"voice_{i:03d}.wav"
        ok = False
        base = int(vsettings["rate"].strip("%+"))
        rate = base + {"fast": 8, "normal": 0, "slow": -10}.get(s.get("pace", "normal"), 0)
        rate_s = f"{rate:+d}%"
        for attempt in range(3):
            try:
                asyncio.run(_edge(s["text"], vsettings["voice"], rate_s,
                                  vsettings["pitch"], mp3))
                ok = mp3.exists() and mp3.stat().st_size > 1000
                if ok:
                    break
            except Exception as e:  # noqa: BLE001
                log(f"edge-tts error scene {i}: {str(e)[:120]}")
        if not ok:
            from gtts import gTTS
            log(f"Scene {i}: using gTTS fallback")
            gTTS(s["text"], lang=GTTS_LANG[lang]).save(str(mp3))
        # trim leading/trailing silence, normalise, 44.1k stereo
        run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-af",
             "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
             "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
             "loudnorm=I=-16:TP=-1.5:LRA=11",
             "-ar", "44100", "-ac", "2", str(wav)])
        out.append((wav, duration(wav)))
    return out
