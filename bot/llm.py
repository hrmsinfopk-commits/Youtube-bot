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


def ask(cfg, prompt, json_mode=False, search=False, temperature=1.0):
    if not secret("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY secret missing")
    last = None
    for attempt in range(3):
        for model in cfg["gemini"]["models"]:
            try:
                text = _call(model, prompt, json_mode, search, temperature)
                if json_mode:
                    return parse_json(text)
                return text
            except Exception as e:  # noqa: BLE001
                last = e
                log(f"Gemini error ({model}): {str(e)[:200]}")
        time.sleep(20 * (attempt + 1))
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
