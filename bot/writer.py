"""Topic selection and script writing (Gemini)."""
import random
import re

from .common import log, topics_file
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
    qfile = topics_file()
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
    if ch.get("mode") == "stories":
        return _pick_story_premise(cfg, past, kind)
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


def _pick_story_premise(cfg, past, kind):
    ch = cfg["channel"]
    prompt = f"""You create ORIGINAL story premises for a faceless Urdu story channel.
Genres: {ch['niche']}
Audience: {ch['audience']}
Format: {"45-55 second YouTube Short with a twist ending" if kind == "short" else "8-10 minute story with several twists"}

Write 12 fresh, completely ORIGINAL premises (your own invention - never retell existing books, films, TV shows,
famous creepypastas, urban legends attributed to real people, or real crimes). Settings should feel local to
Pakistan/India (gaon, haveli, hostel, hospital night shift, highway dhaba, purana mohalla, train) but use fictional names/places.
Each premise: one line, English, with the hook and the twist hinted, e.g. "Night-shift nurse hears a patient call from an empty ward - the call comes from her own phone".

Do NOT repeat or resemble these already-made stories:
{chr(10).join('- ' + p for p in past) or '- (none yet)'}

Return ONLY the 12 premises, one per line, no numbering."""
    text = ask(cfg, prompt, temperature=1.15)
    ideas = [re.sub(r"^\s*(?:[-•*]+|\d{1,2}[.)])\s*", "", l).strip(" *\"") for l in text.splitlines()]
    ideas = [i for i in ideas if 15 < len(i) < 220]
    topic = random.choice(ideas[:8])
    log("Story premise:", topic)
    return topic


def _wps(cfg):
    """Spoken words per second for this channel's voice settings (stories are told slower)."""
    return float(cfg.get("words_per_second", 3.2))


def _story_prompt(cfg, premise, kind, style):
    ch = cfg["channel"]
    lang = ch["language"]
    if kind == "short":
        secs = cfg["shorts"]["target_seconds"]
        length = f"about {int(secs * _wps(cfg))} spoken words ({secs} seconds), 5-8 scenes of 2-3 flowing sentences each"
        shape = ("- ONE narrator ('main'), ONE place, ONE night, ONE strange thing that gets worse in 3 steps. No sub-plots, no backstory dumps.\n"
                 "- Line 1: drop the listener into a specific, quiet, ordinary moment that feels slightly wrong (time + place + one detail),\n"
                 "  e.g. 'Raat ke teen baj rahe the... aur hostel ki teesri manzil par koi seedhiyan chadh raha tha.'\n"
                 "- Escalate with concrete SENSORY details the listener can picture/hear (khat-khat, geeli mitti ki boo, achanak thand, dheemi sargoshi).\n"
                 "- Include ONE short line of dialogue or a whisper in quotes - it is the scariest part.\n"
                 "- Tell it the way people really tell a scary incident to friends: flowing and natural, one sentence leading into the next,\n"
                 "  with everyday Urdu, not poetic or bookish. Use '...' only 2-3 times where a real pause adds tension.\n"
                 "- Keep the momentum: every line must add something new (a sound, a detail, a realisation). No filler, no repeating.\n"
                 "- The final line is the TWIST: short, quiet, and it changes the meaning of everything before it. No moral, no explanation after it.\n"
                 "- The story must make complete sense on its own and be satisfying, not confusing.")
    else:
        mins = cfg["long"]["target_minutes"]
        length = f"about {int(mins * 60 * _wps(cfg))} spoken words ({mins} minutes), 40-70 scenes, one or two sentences per scene"
        shape = ("- Cold open: start at the scariest moment, then 'lekin yeh sab shuru kaise hua...' and go back.\n"
                 "- 4-6 parts, each ending on a cliffhanger. Put a 2-4 word part name in 'chapter' on the first scene of each part.\n"
                 "- Plant small clues early that pay off in the final twist. Final twist must be surprising but fair.\n"
                 "- Mark the 3-6 biggest scare/twist moments reveal: true.")
    return f"""You are a master storyteller writing an ORIGINAL story for the YouTube channel "{ch['name']}".
Genres: {ch['niche']}
Premise: {premise}
Storytelling style for THIS video: {style}
Format: {"YouTube Short (vertical)" if kind == "short" else "Long YouTube video (horizontal)"}
Length: {length}
Narration language: {LANG_RULES[lang]}
{ch.get('extra_instructions') or ''}

Rules:
- 100% original fiction. Never retell or borrow plots, characters or lines from existing books, films, shows or famous stories.
- Fictional names and places only; never name real people, real crimes or real victims.
- Advertiser-friendly: build fear with atmosphere, sound and suspense, NOT gore. No graphic violence, no self-harm, no harm to children, no sexual content.
- Sound like a real person telling a story late at night: short sentences, pauses, everyday words, present-tense moments for tension.
- Never use AI-sounding phrases ("is video mein", "aaiye jaante hain", "dilchasp baat yeh hai").
{shape}

For every scene pick 3 stock-footage keywords ONLY from this list (they return proper dark, atmospheric footage):
{", ".join(cfg.get("footage", {}).get("vocabulary", [])) or "dark corridor, abandoned house, foggy forest, flickering light, rain window, old door, night road, candle, shadow"}
Pick what best matches what the listener is imagining in that line. Scene 1 = the most chilling one.
For every scene also set "pace" (fast/normal/slow) and "reveal" (true only for the 1-2 biggest scare/twist moments).

Return ONLY JSON:
{{
 "title": "Curiosity title, max 70 chars, Roman Urdu/Hindi + a few English words, no lies{' (do NOT add #shorts)' if kind == 'short' else ''}",
 "thumbnail_text": "2-4 creepy words, Roman Urdu or English",
 "hook_text": "2-4 word ALL-CAPS on-screen hook for the first 2 seconds, e.g. DARWAZA MAT KHOLNA",
 "mood": "one of: horror, dark, suspense, mysterious",
 "narrator_gender": "male or female - must match the narrator's Urdu verb forms (raha/rahi) used in the story",
 "description": "2 short Roman Urdu paragraphs teasing the story without spoilers, then a 1-line comment question",
 "tags": ["15 search tags mixing English and Roman Urdu/Hindi, e.g. horror story urdu, bhoot ki kahani"],
 "hashtags": ["#3to5", "#hashtags"],
 "global_keywords": ["4-6 atmospheric English stock keywords for the whole story"],
 "scenes": [
   {{"text": "narration in the narration language/script", "caption": "same in Roman {'Urdu' if lang != 'hindi' else 'Hindi'} (Latin letters)", "keywords": ["specific", "medium", "general"], "pace": "normal", "reveal": false, "chapter": ""}}
 ]
}}"""


def write_script(cfg, topic, kind, style, latest_long_url=None):
    ch = cfg["channel"]
    lang = ch["language"]
    if ch.get("mode") == "stories":
        return _finish(_ask_script(cfg, _story_prompt(cfg, topic, kind, style), kind, 1.1), topic, style)
    if kind == "short":
        secs = cfg["shorts"]["target_seconds"]
        length = f"about {int(secs * _wps(cfg))} spoken words total ({secs} seconds), 6-9 scenes"
        extra = ("- SUSPENSE STRUCTURE: (1) hook line, (2) an open loop in the first 5 seconds that promises a payoff at the end "
                 "(e.g. 'aur aakhri wali baat sab se khatarnak hai'), (3) fast build-up of 2-3 lines, (4) a twist starting with "
                 "'lekin'/'magar' style turn, (5) the REVEAL near the end, delivered slowly, (6) final line.\n"
                 "- One natural SHARE trigger near the end, aimed at a specific friend type (e.g. 'yeh us dost ko bhejo jo kehta hai...').\n"
                 "- Final line: either flows seamlessly back into the first line (loop) OR is a short opinion question people want to answer in comments.\n"
                 "- No 'subscribe' begging at the start.")
    else:
        mins = cfg["long"]["target_minutes"]
        length = f"about {int(mins * 60 * _wps(cfg))} spoken words total ({mins} minutes), 28-45 scenes"
        extra = ("- Structure: hook (0-20s) -> promise of what they'll learn -> 4-7 sections each ending with a mini cliffhanger -> satisfying conclusion -> short outro.\n"
                 "- Put a short chapter name (2-5 words, Roman Urdu/English) on the first scene of each section in 'chapter'; other scenes chapter = \"\".\n"
                 "- At ~40% and ~70% add a pattern interrupt (surprising question or fact) to keep retention high.\n"
                 "- Open a big question in the first 20 seconds and only fully answer it in the last section (open loop).\n"
                 "- Mark the 3-6 biggest twist/answer moments as reveal: true.")

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
- No fear-mongering: never claim or hint at wars, attacks, cover-ups or conspiracies that are not established fact. Excitement must come from real facts, not invented danger.
- Never say "is video mein" / "yeh video" - talk about the topic itself.
- Give specific details (names, years, numbers) instead of vague claims.
{extra}

For every scene give 3 stock-footage search keywords in ENGLISH, ordered from most specific to more general,
each 1-2 words, showing what the viewer should SEE while hearing that line (e.g. for a rocket-landing line: "rocket launch", "rocket", "space").
Keywords must be literal visual subjects that stock sites have (rocket, robot, astronaut, circuit board, city skyline, hospital, laboratory),
NOT abstract words from the sentence (avoid: heavy, success, cheap, time, money, tower, second). Every keyword must clearly relate to the video topic.
Avoid brand names and real people in keywords. For real events prefer REAL footage words (launch, satellite, earth from space, control room)
over sci-fi words (alien, spaceship, futuristic city) so viewers are not misled.
Scene 1 keywords must be the single most visually stunning, dramatic shot for this topic (the first second decides if people stay).

For every scene also set:
- "pace": "fast" for build-up/lists, "normal", or "slow" for the reveal/emotional lines
- "reveal": true only for the 1-2 biggest twist/answer scenes (a short pause + boom sound + zoom will be added before them), else false

Return ONLY JSON:
{{
 "title": "SEO title, max 70 chars, Roman Urdu/Hindi + strong English keywords, curiosity driven, no clickbait lies{' (do NOT add #shorts, it is added later)' if kind == 'short' else ''}",
 "thumbnail_text": "2-4 punchy words in Roman Urdu or English for the thumbnail",
 "hook_text": "2-4 word ALL-CAPS on-screen hook shown in the first 2 seconds (Roman Urdu/English), e.g. PHYSICS FAIL?",
 "narrator_gender": "male or female (keep Urdu verb forms consistent with it)",
 "mood": "one of: suspense, mysterious, dark, epic, uplifting, calm (for background music)",
 "description": "3 short paragraphs in Roman Urdu with main keywords naturally used in first 2 lines, then a 1-line question to drive comments",
 "tags": ["15 search tags mixing English and Roman Urdu/Hindi"],
 "hashtags": ["#3to5", "#hashtags"],
 "global_keywords": ["4-6 general English stock keywords that fit the WHOLE topic visually, e.g. rocket, space, astronaut, earth from space"],
 "scenes": [
   {{"text": "narration for this scene in the narration language/script", "caption": "same narration in Roman {'Urdu' if lang != 'hindi' else 'Hindi'} (Latin letters)", "keywords": ["specific", "medium", "general"], "pace": "normal", "reveal": false, "chapter": ""}}
 ]
}}"""
    return _finish(_ask_script(cfg, prompt, kind, 1.05), topic, style)


def _target_words(cfg, kind):
    w = _wps(cfg)
    return int(cfg["shorts"]["target_seconds"] * w) if kind == "short" else int(cfg["long"]["target_minutes"] * 60 * w)


def _words(data):
    return sum(len(str(sc.get("caption") or sc.get("text", "")).split()) for sc in data.get("scenes", []))


def _ask_script(cfg, prompt, kind, temperature):
    """Ask for a script; if it comes back much shorter than the target, ask once more for a full-length one."""
    target = _target_words(cfg, kind)
    best = ask(cfg, prompt, json_mode=True, temperature=temperature)
    n = _words(best)
    if n < 0.75 * target:
        log(f"Script too short ({n} words, target ~{target}) - rewriting longer")
        try:
            again = ask(cfg, prompt + f"\n\nIMPORTANT: your last draft had only {n} words. This script MUST have "
                                      f"at least {target} spoken words in total across the scenes. Keep every rule above.",
                        json_mode=True, temperature=temperature)
            if _words(again) > n:
                best = again
        except Exception as e:  # noqa: BLE001
            log("Rewrite failed, keeping first draft:", str(e)[:120])
    log(f"Script length: {_words(best)} words")
    return best


def _finish(data, topic, style):
    scenes = [s for s in data.get("scenes", []) if s.get("text", "").strip()]
    if len(scenes) < 3:
        raise RuntimeError("Script too short / malformed")
    for s in scenes:
        s.setdefault("caption", s["text"])
        s.setdefault("chapter", "")
        kws = s.get("keywords") or []
        s["keywords"] = [k for k in kws if isinstance(k, str) and k.strip()] or [topic]
        s["pace"] = s.get("pace") if s.get("pace") in ("fast", "normal", "slow") else "normal"
        s["reveal"] = bool(s.get("reveal")) and s is not scenes[0]
    g = [k for k in (data.get("global_keywords") or []) if isinstance(k, str) and k.strip()]
    data["global_keywords"] = g or [topic]
    data["scenes"] = scenes
    data["mood"] = str(data.get("mood", "suspense")).strip().lower()
    data["hook_text"] = " ".join(str(data.get("hook_text") or data.get("thumbnail_text") or "").split()[:4])
    g = str(data.get("narrator_gender", "")).lower()
    data["narrator_gender"] = g if g in ("male", "female") else None
    data["topic"] = topic
    data["style"] = style
    log(f"Script ready: {data['title']} ({len(scenes)} scenes)")
    return data
