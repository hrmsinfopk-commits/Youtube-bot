"""AI-singer cover that keeps the original singer's melody, timing and words exactly (side tool, runs in cover.yml).

usage: python scripts/make_cover.py <work dir with song.wav> <out dir> <seed-vc dir> <audio-separator binary>
1) split the song into vocals + music, 2) make short reference clips of synthetic (TTS) voices for the new timbre,
3) Seed-VC singing voice conversion (f0-conditioned: the melody is copied, not re-composed), 4) mix back with the music.
"""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

WORK, OUT, SEEDVC, SEP = (Path(a) for a in sys.argv[1:5])
OUT.mkdir(parents=True, exist_ok=True)
VOICES = {   # synthetic voices only (no real singer is imitated)
    "A_urdu_male": ("ur-PK-AsadNeural",
                    "Dil ki baat kehna asaan nahin hota. Kabhi kabhi yaadein itni gehri hoti hain ke raat bhar neend nahin aati. "
                    "Phir bhi hum muskurate hain, aur zindagi ke raaste par aage barhte rehte hain, ek nayi umeed ke saath."),
    "B_hindi_male": ("hi-IN-MadhurNeural",
                     "दिल की बात कहना आसान नहीं होता। कभी कभी यादें इतनी गहरी होती हैं कि रात भर नींद नहीं आती। "
                     "फिर भी हम मुस्कुराते हैं, और ज़िंदगी के रास्ते पर आगे बढ़ते रहते हैं, एक नई उम्मीद के साथ।"),
}


def run(cmd, **kw):
    print("$", " ".join(map(str, cmd))[:300], flush=True)
    subprocess.run(list(map(str, cmd)), check=True, **kw)


def rms(x):
    return float(np.sqrt(np.mean(np.square(x)) + 1e-12))


def main():
    t0 = time.time()
    src = WORK / "song.wav"
    full = WORK / "full44.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", src, "-ar", "44100", "-ac", "2", full])
    sep = WORK / "sep"
    sep.mkdir(exist_ok=True)
    run([SEP, full, "--model_filename", "Kim_Vocal_2.onnx", "--output_dir", sep, "--output_format", "WAV"])
    vocals = next(p for p in sep.iterdir() if "vocals" in p.name.lower())
    inst = next(p for p in sep.iterdir() if "instrumental" in p.name.lower())
    print(f"separated in {time.time() - t0:.0f}s: {vocals.name} / {inst.name}", flush=True)
    voc_mono = WORK / "vocals_mono.wav"
    run(["ffmpeg", "-v", "error", "-y", "-i", vocals, "-ac", "1", "-ar", "44100", voc_mono])

    import edge_tts
    for name, (voice, text) in VOICES.items():
        try:
            mp3 = WORK / f"ref_{name}.mp3"
            asyncio.run(edge_tts.Communicate(text, voice, rate="-8%").save(str(mp3)))
            ref = WORK / f"ref_{name}.wav"
            run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-t", "20", "-ac", "1", "-ar", "22050", ref])
            vc_dir = WORK / f"vc_{name}"
            t = time.time()
            run([sys.executable, "inference.py", "--source", voc_mono, "--target", ref, "--output", vc_dir,
                 "--diffusion-steps", "25", "--inference-cfg-rate", "0.7", "--f0-condition", "True",
                 "--auto-f0-adjust", "False", "--semi-tone-shift", "0", "--fp16", "False"], cwd=SEEDVC)
            vc = next(vc_dir.glob("*.wav"))
            print(f"{name}: converted in {time.time() - t:.0f}s", flush=True)
            # same loudness as the original vocal, then a touch of room + compression, then mix with the music
            orig, _ = sf.read(voc_mono)
            new, sr = sf.read(vc)
            new = new * (rms(orig) / rms(new))
            fixed = WORK / f"vc_{name}_lvl.wav"
            sf.write(fixed, np.clip(new, -1, 1), sr)
            out = OUT / f"cover_{name}.mp3"
            run(["ffmpeg", "-v", "error", "-y", "-i", fixed, "-i", inst, "-filter_complex",
                 "[0:a]aresample=44100,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=150,"
                 "aecho=0.8:0.6:45|90:0.18|0.10,pan=stereo|c0=c0|c1=c0[v];"
                 "[1:a]aresample=44100[m];[v][m]amix=inputs=2:normalize=0:duration=longest,"
                 "alimiter=limit=0.95,loudnorm=I=-14:TP=-1:LRA=11[a]",
                 "-map", "[a]", "-c:a", "libmp3lame", "-b:a", "320k", out])
            run(["ffmpeg", "-v", "error", "-y", "-i", fixed, "-c:a", "libmp3lame", "-b:a", "256k",
                 OUT / f"vocals_only_{name}.mp3"])
        except Exception as e:  # noqa: BLE001
            print(f"{name} failed: {e}", flush=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", inst, "-c:a", "libmp3lame", "-b:a", "320k", OUT / "music_only.mp3"])
    print(f"done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
