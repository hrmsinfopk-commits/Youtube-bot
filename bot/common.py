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
CHANNEL = {"id": "future"}   # set by main.py (--channel)


def history_file():
    ch = CHANNEL["id"]
    return DATA / ("history.json" if ch == "future" else f"history_{ch}.json")


def topics_file():
    ch = CHANNEL["id"]
    return ROOT / ("topics.txt" if ch == "future" else f"topics_{ch}.txt")


def yt_secret_suffix():
    ch = CHANNEL["id"]
    return "" if ch == "future" else f"_{ch.upper()}"


def log(*args):
    print(time.strftime("[%H:%M:%S]"), *args, flush=True)


def _merge(base, over):
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(channel="future"):
    """config.yaml = base (Future channel). channels/<name>.yaml overrides it for other channels."""
    CHANNEL["id"] = channel
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    extra = ROOT / "channels" / f"{channel}.yaml"
    if channel != "future":
        if not extra.exists():
            raise SystemExit(f"channels/{channel}.yaml nahi mili")
        with open(extra, encoding="utf-8") as f:
            _merge(cfg, yaml.safe_load(f))
    cfg.setdefault("channel", {}).setdefault("mode", "facts")
    cfg.setdefault("visual", {})
    return cfg


def load_history():
    if history_file().exists():
        with open(history_file(), encoding="utf-8") as f:
            h = json.load(f)
    else:
        h = {}
    h.setdefault("videos", [])
    h.setdefault("used_media", [])
    return h


def save_history(h):
    DATA.mkdir(exist_ok=True)
    h["used_media"] = h["used_media"][-5000:]
    with open(history_file(), "w", encoding="utf-8") as f:
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
