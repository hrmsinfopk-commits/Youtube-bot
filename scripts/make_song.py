"""Make a song with Google Lyria (Gemini API). Side tool, not part of the channel bot.

usage: python scripts/make_song.py song/request.json song/out
request.json: {"versions": [{"name": "A", "prompt": "..."}], "model": "lyria-3.5"}
Outputs are encrypted with song/pubkey.pem (the repo is public; only the owner can open them).
"""
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

API = "https://generativelanguage.googleapis.com/v1beta"
KEY = os.environ.get("LYRIA_API_KEY") or os.environ["GEMINI_API_KEY"]   # separate paid key keeps the bot's free key free
H = {"x-goog-api-key": KEY, "Content-Type": "application/json"}


def log(*a):
    print(*a, flush=True)
    with open(OUT / "log.txt", "a") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def find_audio(obj, found):
    if isinstance(obj, dict):
        d = obj.get("data")
        kind = str(obj.get("type", "")) + str(obj.get("mime_type", obj.get("mimeType", "")))
        if isinstance(d, str) and len(d) > 1000 and ("audio" in kind or "mp3" in kind or "wav" in kind or not kind):
            found.append((obj.get("mime_type") or obj.get("mimeType") or "audio/mpeg", d))
        for v in obj.values():
            find_audio(v, found)
    elif isinstance(obj, list):
        for v in obj:
            find_audio(v, found)


def find_text(obj, out):
    if isinstance(obj, dict):
        if obj.get("type") == "text" and isinstance(obj.get("text"), str):
            out.append(obj["text"])
        for v in obj.values():
            find_text(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_text(v, out)


def generate(model, prompt):
    r = requests.post(f"{API}/interactions", headers=H, timeout=900,
                      json={"model": model, "input": prompt, "response_format": {"type": "audio"}})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:800]}")
    j = r.json()
    # long jobs may come back as "in progress": poll until done
    for _ in range(60):
        st = str(j.get("status", "")).lower()
        if not j.get("id") or st in ("", "completed", "succeeded", "done") or "progress" not in st and "running" not in st:
            break
        time.sleep(15)
        j = requests.get(f"{API}/interactions/{j['id']}", headers=H, timeout=120).json()
    return j


def encrypt(src):
    k = OUT / "tmp.key"
    k.write_text(os.urandom(32).hex())
    subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-in", str(src), "-out", str(src) + ".enc",
                    "-pass", f"file:{k}"], check=True)
    subprocess.run(["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", "song/pubkey.pem", "-in", str(k),
                    "-out", str(src) + ".key.enc"], check=True)
    k.unlink()
    src.unlink()


def main():
    req = json.loads(Path(sys.argv[1]).read_text())
    for v in req["versions"]:
        for model in [req.get("model", "lyria-3.5")] + req.get("fallback_models", []):
            try:
                log(f"[{v['name']}] generating with {model} ...")
                t = time.time()
                j = generate(model, v["prompt"])
                found, texts = [], []
                find_audio(j, found)
                find_text(j, texts)
                if not found:
                    log(f"[{v['name']}] no audio in reply: {json.dumps(j)[:600]}")
                    continue
                mime, data = found[0]
                ext = ".wav" if "wav" in mime else ".mp3"
                p = OUT / f"song_{v['name']}_{model}{ext}"
                p.write_bytes(base64.b64decode(data))
                (OUT / f"song_{v['name']}_{model}_lyrics.txt").write_text("\n\n".join(texts))
                log(f"[{v['name']}] OK {model}: {p.stat().st_size // 1024} KB in {time.time() - t:.0f}s")
                encrypt(p)
                encrypt(OUT / f"song_{v['name']}_{model}_lyrics.txt")
                break
            except Exception as e:  # noqa: BLE001
                log(f"[{v['name']}] {model} failed: {str(e)[:900]}")


if __name__ == "__main__":
    OUT = Path(sys.argv[2])
    OUT.mkdir(parents=True, exist_ok=True)
    main()
