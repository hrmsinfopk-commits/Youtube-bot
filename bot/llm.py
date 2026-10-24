"""Gemini API (free tier) wrapper with retries and model fallback."""
import json
import re
import time

import requests

from .common import log, secret

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _call(model, prompt, json_mode, search, temperature, video_url=None, extra_parts=None):
    parts = [{"text": prompt}] + list(extra_parts or [])
    if video_url:   # Gemini watches a public YouTube video itself (nothing is downloaded)
        parts = [{"file_data": {"file_uri": video_url}}] + parts
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    if search:
        body["tools"] = [{"google_search": {}}]
    r = requests.post(API.format(model=model), headers={"x-goog-api-key": secret("GEMINI_API_KEY")},
                      json=body, timeout=300 if video_url else 180)
    if r.status_code != 200:
        raise RuntimeError(f"{model}: HTTP {r.status_code} {r.text[:300]}")
    data = r.json()
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


DEAD = set()  # models that are retired or out of daily quota - skipped for the rest of the run
HITS = {}     # how often a model said "quota exceeded" (per-minute limits clear after ~1 minute)


def ask(cfg, prompt, json_mode=False, search=False, temperature=1.0, attempts=4, video_url=None, extra_parts=None):
    if not secret("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY secret missing")
    last = None
    for attempt in range(attempts):
        # first tries: only the stronger models (better, longer scripts); "lite" only as a last resort
        strong_left = [m for m in cfg["gemini"]["models"] if "lite" not in m and m not in DEAD]
        use_lite = attempt >= min(2, attempts - 1) or not strong_left
        for model in cfg["gemini"]["models"]:
            if model in DEAD or ("lite" in model and not use_lite):
                continue
            try:
                text = _call(model, prompt, json_mode, search, temperature, video_url, extra_parts)
                result = parse_json(text) if json_mode else text
                log(f"Gemini OK ({model})")
                return result
            except Exception as e:  # noqa: BLE001
                last = e
                msg = str(e)
                if "HTTP 404" in msg:
                    DEAD.add(model)   # retired model
                elif "HTTP 429" in msg and "quota" in msg.lower():
                    HITS[model] = HITS.get(model, 0) + 1
                    if HITS[model] >= 3:   # still over quota after waiting ~1 min twice -> daily limit, skip it
                        DEAD.add(model)
                log(f"Gemini error ({model}): {msg[:160].replace(chr(10), ' ')}")
        if attempt < attempts - 1:
            time.sleep(25)  # busy (503) / per-minute limit (429) usually clears quickly
    raise RuntimeError(f"Gemini failed: {last}")


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))
