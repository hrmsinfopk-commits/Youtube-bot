"""Topic selection and script writing (Gemini)."""
import random
import re

from .common import ROOT, log
from .llm import ask

LANG_RULES = {
    "urdu": ("Urdu script (اردو) mein, aam bol-chaal wali Urdu jo Hindi bolne wale bhi samajh saken. "
             "Mushkil Farsi/Arabi alfaaz se bacho. Tech words English mein hi likho magar Urdu script mein (jaise روبوٹ، اے آئی)."),
    "hindi": ("Hindi Devanagari script mein, aam bol-chaal wali Hindustani. "
              "Tech words English hi rakho magar Devanagari mein."),
    "english": "simple, conversational English.",
}


def pick_topic(cfg, history, kind):
    """1) topics.txt queue, 2) Gemini trending ideas avoiding repeats."""
    qfile = ROOT / "topics.txt"
    if qfile.exists():
        lines = qfile.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            t = line.strip()
            if t and not t.startswith("#"):
                del lines[i]
                qfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
                log("Topic from topics.txt:", t)
                return t

    past = [v.get("topic", "") for v in history["videos"]][-150:]
    ch = cfg["channel"]
    prompt = f"""You are a YouTube growth strategist for a faceless channel.
Niche: {ch['niche']}
Audience: {ch['audience']}
Video type: {"YouTube Short (under 60s)" if kind == "short" else "8-10 minute long video"}

Find 12 fresh video topic ideas that are trending RIGHT NOW or have strong evergreen search demand
and high curiosity / click potential in this niche. Prefer real recent news, launches, discoveries
(look them up), plus curiosity-gap evergreen angles. Every idea must be factually grounded.

Do NOT repeat or closely resemble any of these already-made topics:
{chr(10).join('- ' + p for p in past) or '- (none yet)'}

Return ONLY the 12 topics, one per line, each a short working title in English, no numbering, no extra text."""
    text = None
    if cfg["gemini"].get("use_google_search_for_trends", True):
        try:
            text = ask(cfg, prompt, search=True, attempts=1)
        except Exception as e:  # noqa: BLE001
            log("Search-grounded ideas failed, using plain mode:", str(e)[:150])
    if not text:
        text = ask(cfg, prompt)
    ideas = [re.sub(r"^\s*(?:[-•*]+|\d{1,2}[.)])\s*", "", l).strip(" *\"") for l in text.splitlines()]
    ideas = [i for i in ideas if 8 < len(i) < 140]
    past_l = {p.lower() for p in past}
    ideas = [i for i in ideas if i.lower() not in past_l] or ideas
    topic = random.choice(ideas[:6])
    log("Topic chosen:", topic)
    return topic


def write_script(cfg, topic, kind, style, latest_long_url=None):
    ch = cfg["channel"]
    lang = ch["language"]
    if kind == "short":
        secs = cfg["shorts"]["target_seconds"]
        length = f"about {int(secs * 2.4)} spoken words total ({secs} seconds), 6-9 scenes"
        extra = ("- The LAST line must flow naturally back into the FIRST line so the Short loops seamlessly.\n"
                 "- No 'subscribe' begging at the start; one quick casual CTA allowed at the end.")
    else:
        mins = cfg["long"]["target_minutes"]
        length = f"about {int(mins * 145)} spoken words total ({mins} minutes), 28-45 scenes"
        extra = ("- Structure: hook (0-20s) -> promise of what they'll learn -> 4-7 sections each ending with a mini cliffhanger -> satisfying conclusion -> short outro.\n"
                 "- Put a short chapter name (2-5 words, Roman Urdu/English) on the first scene of each section in 'chapter'; other scenes chapter = \"\".\n"
                 "- At ~40% and ~70% add a pattern interrupt (surprising question or fact) to keep retention high.")

    prompt = f"""You write viral YouTube scripts for the channel "{ch['name']}".
Niche: {ch['niche']}
Audience: {ch['audience']}
Topic: {topic}
Format: {"YouTube Short (vertical)" if kind == "short" else "Long YouTube video (horizontal)"}
Style for THIS video: {style}
Length: {length}
Narration language: {LANG_RULES[lang]}
{ch.get('extra_instructions') or ''}

Write it like a real, passionate human creator talking to a friend, NOT like an AI:
- First sentence = a scroll-stopping hook (shock, curiosity gap, bold claim, or direct question). No greetings, no "aaj hum baat karenge".
- Short punchy sentences, varied rhythm, everyday words, occasional casual reactions ("socho zara", "yahi to twist hai").
- Never use these AI-sounding phrases: "is video mein", "aaiye jaante hain", "dilchasp baat yeh hai", "in conclusion", "delve", "kya aap jaante hain" as an opener.
- Only true, verifiable facts. If unsure, frame as possibility, not fact. No fake statistics.
- Give specific details (names, years, numbers) instead of vague claims.
{extra}

For every scene give 3 stock-footage search keywords in ENGLISH, ordered from most specific to more general,
each 1-2 words, showing what the viewer should SEE while hearing that line (e.g. for a rocket-landing line: "rocket launch", "rocket", "space").
Keywords must be literal visual subjects that stock sites have (rocket, robot, astronaut, circuit board, city skyline, hospital, laboratory),
NOT abstract words from the sentence (avoid: heavy, success, cheap, time, money, tower, second). Every keyword must clearly relate to the video topic.
Avoid brand names and real people in keywords.

Return ONLY JSON:
{{
 "title": "SEO title, max 70 chars, Roman Urdu/Hindi + strong English keywords, curiosity driven, no clickbait lies{' (do NOT add #shorts, it is added later)' if kind == 'short' else ''}",
 "thumbnail_text": "2-4 punchy words in Roman Urdu or English for the thumbnail",
 "description": "3 short paragraphs in Roman Urdu with main keywords naturally used in first 2 lines, then a 1-line question to drive comments",
 "tags": ["15 search tags mixing English and Roman Urdu/Hindi"],
 "hashtags": ["#3to5", "#hashtags"],
 "global_keywords": ["4-6 general English stock keywords that fit the WHOLE topic visually, e.g. rocket, space, astronaut, earth from space"],
 "scenes": [
   {{"text": "narration for this scene in the narration language/script", "caption": "same narration in Roman {'Urdu' if lang != 'hindi' else 'Hindi'} (Latin letters)", "keywords": ["specific", "medium", "general"], "chapter": ""}}
 ]
}}"""
    data = ask(cfg, prompt, json_mode=True, temperature=1.05)
    scenes = [s for s in data.get("scenes", []) if s.get("text", "").strip()]
    if len(scenes) < 3:
        raise RuntimeError("Script too short / malformed")
    for s in scenes:
        s.setdefault("caption", s["text"])
        s.setdefault("chapter", "")
        kws = s.get("keywords") or []
        s["keywords"] = [k for k in kws if isinstance(k, str) and k.strip()] or [topic]
    g = [k for k in (data.get("global_keywords") or []) if isinstance(k, str) and k.strip()]
    data["global_keywords"] = g or [topic]
    data["scenes"] = scenes
    data["topic"] = topic
    data["style"] = style
    log(f"Script ready: {data['title']} ({len(scenes)} scenes)")
    return data
