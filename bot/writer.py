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
    "english": ("natural spoken American-style English for a global audience: simple words, contractions, "
                "energetic but not hype; avoid British spellings and slang that non-native speakers won't get."),
}


def queued_topic():
    """Next line from topics.txt (your own topics always go first)."""
    qfile = topics_file()
    if not qfile.exists():
        return None
    lines = qfile.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        t = line.strip()
        if t and not t.startswith("#"):
            del lines[i]
            qfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
            log("Topic from topics file:", t)
            return t
    return None


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
For every scene also write "image": one English sentence describing exactly what the viewer should SEE in that moment
(setting, light, objects, the character from behind/in shadow, camera angle) for an AI illustration. Rules for "image": always an ORIGINAL scene,
no real or famous people, no known film/game/cartoon characters, no brands or logos, no written text, no gore. Keep the same main character
description (clothes, age) in every image so the story looks consistent.
For every scene also set "sound": a 1-2 word English sound effect that happens in that line if any (e.g. "door knock", "footsteps", "radio static",
"whisper", "glass break", "thunder"), else "".
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
 "ambience": "1-3 word English background ambience for the whole story, e.g. rain night, wind howling, basement hum, crickets night",
 "scenes": [
   {{"text": "narration in the narration language/script", "caption": "same in Roman {'Urdu' if lang != 'hindi' else 'Hindi'} (Latin letters)", "keywords": ["specific", "medium", "general"], "image": "what we see", "sound": "", "pace": "normal", "reveal": false, "chapter": ""}}
 ]
}}"""


def write_script(cfg, topic, kind, style, brief=None):
    """brief: optional dict from trends.find_topic() with real news facts + search keywords."""
    ch = cfg["channel"]
    lang = ch["language"]
    if ch.get("mode") == "stories":
        draft = _ask_script(cfg, _story_prompt(cfg, topic, kind, style), kind, 1.1)
        return _finish(_edit_story(cfg, draft, kind), topic, style)
    en = lang == "english"
    if kind == "short":
        secs = cfg["shorts"]["target_seconds"]
        length = f"about {int(secs * _wps(cfg))} spoken words total ({secs} seconds), 6-9 scenes"
        extra = ("- STRUCTURE: (1) bold statement or vivid 'you' scenario as the hook (not a question), "
                 "(2) an open loop in the first 5 seconds that promises a payoff at the end, (3) fast build-up of 2-3 lines, "
                 "(4) a twist ('but here's the thing...'), (5) the REVEAL near the end, (6) final line.\n"
                 "- One natural SHARE trigger near the end aimed at a specific friend type (e.g. 'send this to the friend who...').\n"
                 "- Final line: either flows seamlessly back into the first line (loop) OR is a short opinion question people want to answer.\n"
                 "- One idea only. Every line must add something new. No intro, no 'subscribe' at the start.")
    else:
        mins = cfg["long"]["target_minutes"]
        length = f"about {int(mins * 60 * _wps(cfg))} spoken words total ({mins} minutes), 35-60 scenes"
        fmt = (brief or {}).get("long_format", "deep dive")
        if fmt == "weekly roundup":
            shape = ("- FORMAT: weekly roundup of the 5 biggest stories in the fact sheet, counting down from #5 to #1 (the biggest).\n"
                     "- Cold open teasing #1 in the first 15 seconds, then go through each story: what happened, why it matters, what's next.")
        else:
            shape = ("- FORMAT: deep dive on ONE story: cold open with the most surprising fact, then context/background, "
                     "how it works, who is behind it, problems and doubts, what happens next, and what it means for ordinary people.")
        extra = (shape + "\n"
                 "- 4-7 sections, each ending with a mini cliffhanger. Put a 2-5 word chapter name on the first scene of each section in 'chapter'; other scenes \"\".\n"
                 "- At ~40% and ~70% add a pattern interrupt (surprising question or fact) to keep retention high.\n"
                 "- Open a big question in the first 20 seconds and only fully answer it in the last section (open loop).\n"
                 "- Mark the 3-6 biggest twist/answer moments as reveal: true.\n"
                 "- End with a short outro inviting people to comment and to watch the next video; no begging.")

    facts = ""
    if brief and brief.get("facts"):
        facts = ("\nFACT SHEET (from real news published in the last days; these are the ONLY facts you may state as true):\n"
                 + "\n".join(f"- {f}" for f in brief["facts"][:40]) +
                 "\nRules for using it: explain in your OWN words - never copy sentences from it; if something is only announced,"
                 " planned or claimed, say so clearly; don't add numbers or claims that are not in the fact sheet or well-established science.\n")
    seo = ""
    if brief and brief.get("keywords"):
        seo = ("\nSEO: people are actively searching/watching these phrases right now - use the best ones naturally in the title,"
               " the first two lines of the description and the tags: " + ", ".join(brief["keywords"][:15]) + "\n")

    title_lang = "English" if en else "Roman Urdu/Hindi + strong English keywords"
    prompt = f"""You write viral YouTube scripts for the channel "{ch['name']}".
Niche: {ch['niche']}
Audience: {ch['audience']}
Topic: {topic}
Format: {"YouTube Short (vertical)" if kind == "short" else "Long YouTube video (horizontal)"}
Style for THIS video: {style}
Length: {length}
Narration language: {LANG_RULES[lang]}
{ch.get('extra_instructions') or ''}{facts}{seo}
Write it like a real, passionate human creator talking to a friend, NOT like an AI:
- First sentence = a scroll-stopping hook. No greetings, no "today we're going to talk about".
- Short punchy sentences, varied rhythm, everyday words, occasional casual reactions.
- Never use AI-sounding phrases: "in this video", "let's dive in", "delve", "buckle up", "in conclusion", "fascinating world of",
  "did you know" as an opener{', "is video mein", "aaiye jaante hain", "dilchasp baat yeh hai"' if not en else ''}.
- Only true, verifiable facts. If unsure, frame as possibility. No fake statistics.
- No fear-mongering: never claim or hint at wars, attacks, cover-ups or conspiracies that are not established fact.
- Weapons/military tech: explain the technology and why it matters, neutral tone, no glorifying violence, no how-to.
- Give specific details (names, dates, numbers) instead of vague claims.
{extra}

For every scene give 3 stock-footage search keywords in ENGLISH, ordered from most specific to more general,
each 1-2 words, showing what the viewer should SEE while hearing that line (e.g. for a rocket-landing line: "rocket launch", "rocket", "space").
Keywords must be literal visual subjects that stock sites have (rocket, robot, astronaut, circuit board, city skyline, laboratory),
NOT abstract words. Every keyword must clearly relate to the topic. No brand names or real people in keywords.
For real events prefer REAL footage words (launch, satellite, earth from space, control room) over sci-fi words (alien, spaceship).
For every scene also write "image": one English sentence describing what the viewer should SEE (realistic, accurate to the facts) for an AI
illustration - always an ORIGINAL scene: no real or famous people, no known characters, no brands or logos, no text, no gore.
"sound": a 1-2 word English sound effect in that line if any (e.g. "rocket launch", "beep", "crowd cheer", "engine"), else "".
Scene 1 keywords must be the single most visually stunning shot for this topic (the first second decides if people stay).
"pace": "fast" for build-up/lists, "normal", or "slow" for reveals. "reveal": true only for the biggest twist/answer moments.

Return ONLY JSON:
{{
 "title": "SEO title in {title_lang}, max 70 chars, curiosity driven, no clickbait lies{' (do NOT add #shorts)' if kind == 'short' else ''}",
 "thumbnail_text": "2-4 punchy words for the thumbnail",
 "hook_text": "2-4 word ALL-CAPS on-screen hook for the first 2 seconds, e.g. IT CAN FLY?",
 "narrator_gender": "male or female",
 "mood": "one of: suspense, mysterious, dark, epic, uplifting, calm (background music)",
 "description": "{'3 short English paragraphs' if en else '3 short Roman Urdu paragraphs'} with the main search keywords in the first 2 lines, then a 1-line question to drive comments",
 "tags": ["15 search tags people really type"],
 "hashtags": ["#3to5", "#hashtags"],
 "global_keywords": ["4-6 general English stock keywords that fit the WHOLE topic visually"],
 "scenes": [
   {{"text": "narration for this scene", "caption": "{'same as text' if en else 'same narration in Roman Urdu (Latin letters)'}", "keywords": ["specific", "medium", "general"], "image": "what we see", "sound": "", "pace": "normal", "reveal": false, "chapter": ""}}
 ]
}}"""
    return _finish(_ask_script(cfg, prompt, kind, 1.0), topic, style)


def _edit_story(cfg, draft, kind):
    """Second pass: a harsh editor rewrites the draft to be scarier, more adult and more specific."""
    import json as _json
    prompt = f"""You are a harsh, experienced editor of a hit Urdu horror YouTube channel for ADULT listeners.
Here is a draft script as JSON:
{_json.dumps(draft, ensure_ascii=False)}

Rewrite it to be genuinely creepy and gripping:
- Cut anything childish, generic or cliche (no 'bhoot ne kaha bhaago', no cartoonish villains, no explaining the twist).
- Make the fear personal and specific: real places in an ordinary life, small wrong details, believable reactions.
- Sharpen the final line so the twist lands like a cold shock in one short sentence.
- Keep the same premise, roughly the same length ({_target_words(cfg, kind)} words), the same JSON structure and fields,
  keep "caption" as the Roman Urdu version of "text", keep all rules for keywords, "image" and "sound".
- 100% original, fictional names and places, no real people, no gore.
Return ONLY the improved JSON."""
    try:
        better = ask(cfg, prompt, json_mode=True, temperature=0.9)
        if len([sc for sc in better.get("scenes", []) if sc.get("text")]) >= 3 and _words(better) >= 0.7 * _words(draft):
            log(f"Story edited ({_words(draft)} -> {_words(better)} words)")
            return better
    except Exception as e:  # noqa: BLE001
        log("Editor pass failed, using draft:", str(e)[:120])
    return draft


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
        s["image"] = str(s.get("image") or "").strip()
        s["sound"] = str(s.get("sound") or "").strip()
        s["reveal"] = bool(s.get("reveal")) and s is not scenes[0]
    g = [k for k in (data.get("global_keywords") or []) if isinstance(k, str) and k.strip()]
    data["global_keywords"] = g or [topic]
    data["scenes"] = scenes
    data["mood"] = str(data.get("mood", "suspense")).strip().lower()
    data["ambience"] = str(data.get("ambience") or "").strip()
    data["hook_text"] = " ".join(str(data.get("hook_text") or data.get("thumbnail_text") or "").split()[:4])
    g = str(data.get("narrator_gender", "")).lower()
    data["narrator_gender"] = g if g in ("male", "female") else None
    data["topic"] = topic
    data["style"] = style
    log(f"Script ready: {data['title']} ({len(scenes)} scenes)")
    return data
