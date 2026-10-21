"""Topic selection and script writing (Gemini)."""
import random
import re

from .common import ROOT, log, topics_file
from .llm import ask

LANG_RULES = {
    "urdu": ("Urdu script (اردو) mein, aam bol-chaal wali Urdu jo Hindi bolne wale bhi samajh saken. "
             "Mushkil Farsi/Arabi alfaaz se bacho. Tech words English mein hi likho magar Urdu script mein (jaise روبوٹ، اے آئی)."),
    "hindi": ("Hindi Devanagari script mein, aam bol-chaal wali Hindustani. "
              "Tech words English hi rakho magar Devanagari mein."),
    "english": ("natural spoken American-style English for a global audience: simple words, contractions, "
                "energetic but not hype; avoid British spellings and slang that non-native speakers won't get."),
}


def queued_topic(kind="short", consume=True):
    """Next line from topics.txt (your own topics go first). Lines starting with 'long:' are for long videos."""
    qfile = topics_file()
    if not qfile.exists():
        return None
    lines = qfile.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        t = line.strip()
        is_long = t.lower().startswith("long:")
        if t and not t.startswith("#") and is_long == (kind == "long"):
            t = t[5:].strip() if is_long else t
            if not consume:   # test runs (no upload) leave your list untouched
                log("Topic from topics file (test, kept in list):", t)
                return t
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


def writer_brief():
    """The owner's standing brief for the script writer (writer_brief.md, editable on GitHub)."""
    p = ROOT / "writer_brief.md"
    try:
        txt = p.read_text(encoding="utf-8")
        return "\n".join(l for l in txt.splitlines() if not l.startswith(">"))
    except Exception:  # noqa: BLE001
        return ""


SIGNATURES = ["THE CATCH", "WE DID THE MATH", "HYPE METER", "TOMORROW TEST"]


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


def write_script(cfg, topic, kind, style, brief=None, memory=None):
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
        length = f"about {int(mins * 60 * _wps(cfg))} spoken words total ({mins} minutes), 18-30 scenes"
        extra = (
            "- ONE story, ONE central question, told from start to end. Every scene must move the viewer closer to the answer;\n"
            "  if a line does not connect to the central question, cut it. No lists of unrelated facts.\n"
            "- STORY SPINE (with approximate share of the video):\n"
            "  1. HOOK (first 10-15 s): the most surprising concrete fact + the central question + why the viewer should care.\n"
            "  2. CONTEXT (~15%): the problem or situation before this news, in simple everyday terms.\n"
            "  3. HOW IT WORKS (~25%): explain the key idea with one clear everyday analogy; show, don't lecture.\n"
            "  4. THE PEOPLE/STAKES (~15%): who is doing it, what they risk, a concrete number or moment.\n"
            "  5. THE TWIST (~15%): 'but here's the catch...' - the real limitation, doubt, cost or open problem (be honest).\n"
            "  6. PAYOFF (~20%): answer the central question clearly, then what it means for ordinary people in the next years.\n"
            "  7. END (last 10 s): one short sentence that calls back to the hook, then ONE opinion question for the comments. No outro, no begging.\n"
            "- Each part ends with a one-line bridge that makes the viewer want the next part (a small open question).\n"
            "- Escalate: the most impressive fact goes late, not at the start (except the hook).\n"
            "- Change rhythm every 30-40 s: a question to the viewer, a big on_screen number, a quick comparison, or a reveal.\n"
            "- Put a 2-4 word chapter name on the first scene of each of the 7 parts in 'chapter'; other scenes \"\".\n"
            "- Mark the 2-4 biggest reveal moments as reveal: true.")

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
    memory = memory or {}
    brief_txt = writer_brief()
    if kind == "short":
        recent = memory.get("recent_signatures", [])
        options = [x for x in SIGNATURES if x not in recent[-2:]] or SIGNATURES
        signature = __import__("random").choice(options)
        sig_rule = (f"- SIGNATURE for this Short: use exactly one - {signature} - placed where it hits hardest "
                    f"(HYPE METER / TOMORROW TEST work best as the last line).")
    else:
        signature = "ALL"
        sig_rule = ("- SIGNATURES for this long video: THE CATCH (in the twist part) and WE DID THE MATH (one calculation, "
                    "with a 'bars' or 'counter' graphic), then end with HYPE METER and TOMORROW TEST (each with its graphic).")
    avoid = memory.get("openings", [])[-25:] + memory.get("endings", [])[-15:]
    avoid_txt = ("\nNEVER reuse or closely imitate these openings/endings from our previous videos:\n"
                 + "\n".join(f"- {x}" for x in avoid) + "\n") if avoid else ""
    owner = (brief or {}).get("owner_take")
    owner_txt = f"\nCHANNEL OWNER'S OWN TAKE - weave this opinion in naturally, in your words: {owner}\n" if owner else ""
    graphics_rule = (
        "\nOWN GRAPHICS (made by our code - they make the channel unique). Add a \"graphic\" to "
        + ("at most 1-2 scenes" if kind == "short" else "4-7 scenes") + ", only where it truly helps; else null:\n"
        '- {"type": "counter", "value": 250000, "prefix": "$", "suffix": "", "label": "starting price"}  (one big number counting up)\n'
        '- {"type": "bars", "title": "Top speed", "labels": ["Car", "Jet"], "values": [300, 900], "unit": "km/h"}  (2-4 bars, real numbers only)\n'
        '- {"type": "timeline", "items": [{"year": "2024", "text": "First test"}, {"year": "2027", "text": "Planned launch"}]}  (2-4 items)\n'
        '- {"type": "hype_meter", "value": 6}  (1-10; the HYPE METER scene)\n'
        '- {"type": "tomorrow_test", "answer": "Maybe"}  (Yes / Maybe / Not yet; the TOMORROW TEST scene)\n'
        "Every number in a graphic must come from the fact sheet, well-established facts, or your clearly rough WE DID THE MATH.\n")
    prompt = f"""You write viral YouTube scripts for the channel "{ch['name']}".
Niche: {ch['niche']}
Audience: {ch['audience']}
Topic: {topic}
Format: {"YouTube Short (vertical)" if kind == "short" else "Long YouTube video (horizontal)"}
Style for THIS video: {style}
Length: {length}
Narration language: {LANG_RULES[lang]}
{ch.get('extra_instructions') or ''}{facts}{seo}{owner_txt}
=== CHANNEL WRITER BRIEF (your standing instructions - follow it) ===
{brief_txt}
=== END OF BRIEF ===
{sig_rule}
{avoid_txt}
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
"sound": only if the line clearly has one, pick EXACTLY one of: "rocket launch", "jet flyby", "whoosh", "computer beep",
"notification", "crowd cheer", "camera shutter", "thunder", "explosion distant", "electric motor", "alarm", "heartbeat"; else "".
Use sounds rarely (at most 3 per Short).
Scene 1 keywords must be the single most visually stunning shot for this topic (the first second decides if people stay).{graphics_rule}
"pace": "fast" for build-up/lists, "normal", or "slow" for reveals. "reveal": true only for the biggest twist/answer moments.
"subject": if the line is about a specific REAL named thing people would want to see (e.g. "Tesla Roadster", "Starship",
"James Webb Space Telescope", "Boston Dynamics Atlas"), its exact name - used to find real licensed photos; else "".
"on_screen": for the 20-30% of scenes with a striking number or 2-4 word fact, the text to flash big on screen
(e.g. "$250,000", "10 THRUSTERS", "0-60 IN 1.9s", "BY 2027?"); else "". Never more than 5 words.

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
   {{"text": "narration for this scene", "caption": "{'same as text' if en else 'same narration in Roman Urdu (Latin letters)'}", "keywords": ["specific", "medium", "general"], "image": "what we see", "sound": "", "subject": "", "on_screen": "", "graphic": null, "pace": "normal", "reveal": false, "chapter": ""}}
 ],
 "hype_score": "1-10 (your HYPE METER verdict)",
 "tomorrow_test": "Yes / Maybe / Not yet"
}}"""
    draft = _ask_script(cfg, prompt, kind, 1.0)
    draft = _uniqueness_check(cfg, draft, prompt, kind, memory)
    draft["signature"] = signature
    if kind == "long":
        draft = _edit_long(cfg, draft, topic)
    return _finish(draft, topic, style)


def _shingles(text, n=5):
    w = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def script_text(data):
    return " ".join(str(sc.get("text", "")) for sc in data.get("scenes", []))


def _uniqueness_check(cfg, draft, prompt, kind, memory):
    """Compare with our previous scripts; if too similar (repeated phrasing/structure), ask for a fresh rewrite once."""
    past = memory.get("scripts", [])
    if not past:
        return draft
    me = _shingles(script_text(draft))
    worst = 0.0
    for old in past[-60:]:
        o = _shingles(old)
        if me and o:
            worst = max(worst, len(me & o) / min(len(me), len(o)))
    first = (draft.get("scenes") or [{}])[0].get("text", "").lower()
    same_open = any(len(set(first.split()) & set(x.lower().split())) >= 0.6 * max(1, len(first.split()))
                    for x in memory.get("openings", [])[-25:])
    log(f"Uniqueness: {100 * (1 - worst):.0f}% unique vs previous scripts" + (" (opening too similar)" if same_open else ""))
    if worst < 0.12 and not same_open:
        return draft
    try:
        again = ask(cfg, prompt + "\n\nIMPORTANT: your draft repeated phrasing/openings from our earlier videos. Write a FRESH script with a "
                    "different opening type, different sentence patterns and a different structure, same facts and rules.",
                    json_mode=True, temperature=1.1)
        if len(again.get("scenes", [])) >= 3:
            log("Rewritten for uniqueness")
            return again
    except Exception as e:  # noqa: BLE001
        log("Uniqueness rewrite failed:", str(e)[:100])
    return draft


def _edit_long(cfg, draft, topic):
    """Second pass by a strict editor: one clear thread from hook to payoff, no random lines, no boring stretches."""
    import json as _json
    prompt = f"""You are the head editor of a top science & tech YouTube channel. Improve this {cfg['long']['target_minutes']}-minute script about
"{topic}" so a curious viewer watches until the end. Draft JSON:
{_json.dumps(draft, ensure_ascii=False)}

Check and fix:
- Is there ONE central question stated in the first 15 seconds and clearly answered at the end? If not, add/fix it.
- Does every scene connect to that question and follow logically from the previous one? Rewrite or cut lines that feel random.
- Are there boring stretches (more than ~35 s without a question, surprise, number or reveal)? Fix them.
- Is the most impressive fact saved for late in the video? Is there an honest "catch"? Is the ending short and does it call back to the hook?
- Keep facts exactly as true as in the draft (do not invent numbers). Keep spoken words within +-10% of the draft length.
- Keep the same JSON structure and all fields (text, caption = same as text, keywords, image, sound, subject, on_screen, graphic, pace, reveal, chapter) and hype_score, tomorrow_test.
Return ONLY the improved JSON."""
    try:
        better = ask(cfg, prompt, json_mode=True, temperature=0.7)
        if len([sc for sc in better.get("scenes", []) if sc.get("text")]) >= 8 and _words(better) >= 0.75 * _words(draft):
            log(f"Long script edited for flow ({_words(draft)} -> {_words(better)} words)")
            return better
    except Exception as e:  # noqa: BLE001
        log("Long-script editor failed, using draft:", str(e)[:120])
    return draft


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
        s["subject"] = str(s.get("subject") or "").strip()
        s["on_screen"] = " ".join(str(s.get("on_screen") or "").split()[:5])
        g = s.get("graphic")
        s["graphic"] = g if isinstance(g, dict) and g.get("type") in (
            "counter", "bars", "timeline", "hype_meter", "tomorrow_test") else None
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
