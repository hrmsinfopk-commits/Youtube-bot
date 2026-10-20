"""Gemini API (free tier) wrapper with retries and model fallback."""
import json
import re
import time

import requests

from .common import log, secret

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _call(model, prompt, json_mode, search, temperature):
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    if search:
        body["tools"] = [{"google_search": {}}]
    r = requests.post(API.format(model=model), headers={"x-goog-api-key": secret("GEMINI_API_KEY")},
                      json=body, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"{model}: HTTP {r.status_code} {r.text[:300]}")
    data = r.json()
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


DEAD = set()  # models that returned 404 (retired) - skipped for the rest of the run


def ask(cfg, prompt, json_mode=False, search=False, temperature=1.0, attempts=4):
    if not secret("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY secret missing")
    last = None
    for attempt in range(attempts):
        for model in cfg["gemini"]["models"]:
            if model in DEAD:
                continue
            try:
                text = _call(model, prompt, json_mode, search, temperature)
                result = parse_json(text) if json_mode else text
                log(f"Gemini OK ({model})")
                return result
            except Exception as e:  # noqa: BLE001
                last = e
                msg = str(e)
                if "HTTP 404" in msg:
                    DEAD.add(model)
                log(f"Gemini error ({model}): {msg[:160].replace(chr(10), ' ')}")
        if attempt < attempts - 1:
            time.sleep(35)  # free-tier per-minute limit resets after ~1 minute
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
