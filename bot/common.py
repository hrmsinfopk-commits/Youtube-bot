"""Shared helpers: config, paths, history, logging, ffmpeg wrappers."""
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "output"
WORK = ROOT / "work"
FONTS = ROOT / "fonts"
MUSIC = ROOT / "music"
HISTORY_FILE = DATA / "history.json"


def log(*args):
    print(time.strftime("[%H:%M:%S]"), *args, flush=True)


def load_config():
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            h = json.load(f)
    else:
        h = {}
    h.setdefault("videos", [])
    h.setdefault("used_media", [])
    return h


def save_history(h):
    DATA.mkdir(exist_ok=True)
    h["used_media"] = h["used_media"][-5000:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=1)


def run(cmd, quiet=True):
    """Run a command list; raise with stderr on failure."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-3000:])
        raise RuntimeError(f"Command failed: {' '.join(map(str, cmd[:6]))} ...")
    if not quiet:
        print(r.stdout)
    return r.stdout


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


def secret(name):
    return os.environ.get(name, "").strip()


def rnd(seed_text=None):
    return random.Random(seed_text) if seed_text else random.Random()
