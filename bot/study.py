"""Weekly study of viral Shorts in our niche.

Finds the most-watched recent Shorts (YouTube Data API), lets Gemini WATCH each one (public YouTube link - nothing is
downloaded) and describe how it is built, then turns the patterns into a playbook the script writer reads
(data/playbook_<channel>.json). We learn patterns only - never anyone's wording.

python -m bot.study                 -> full study (config: study.videos, default 12)
python -m bot.study --limit 3       -> quick test
"""
import argparse
import datetime as dt
import json
import re

from .common import CHANNEL, DATA, ROOT, load_config, log
from .llm import ask

ANALYSE = """You are a YouTube Shorts analyst. Watch this Short carefully (picture AND sound) and describe HOW it is built.
Return ONLY JSON:
{
 "first_line": "what is said in the first ~3 seconds (paraphrase is fine)",
 "seconds_until_topic_is_clear": 0,
 "hook_type": "e.g. named subject + promise / contradiction / shocking number / question / visual shock",
 "beats": ["the script structure in 4-8 short steps, e.g. 'hook: name + promise', 'big number with comparison', 'explains concept', 'honest limit', 'payoff', 'channel CTA'"],
 "length_seconds": 0,
 "words_per_second": 0.0,
 "key_number_and_how_it_is_made_feelable": "",
 "what_the_viewer_learns": "",
 "language_level": "simple / medium / technical",
 "tone": "e.g. calm documentary / energetic / funny / dramatic",
 "ending": "how it ends (CTA, loop, question, summary...)",
 "visual_style": "3D animation / real footage / stock / talking head / screen recording / mixed - and how well picture matches words",
 "cuts_per_10_seconds": 0.0,
 "captions": "size, case, colours, how many words at once, highlighted words",
 "sound": "music mood and loudness vs voice, sound effects used or not",
 "why_it_works": ["3 concrete reasons"],
 "weak_points": ["1-2 things that could be better"]
}"""


def find_viral(cfg, n):
    from . import upload
    yt = upload._service()
    st = cfg.get("study", {})
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=st.get("days", 30))).strftime("%Y-%m-%dT%H:%M:%SZ")
    region = cfg["trends"].get("region", "US")
    ids = []
    for kw in st.get("keywords") or cfg["trends"]["youtube_keywords"]:
        try:
            res = yt.search().list(part="id", q=kw, type="video", videoDuration="short", order="viewCount",
                                   publishedAfter=since, maxResults=10, regionCode=region, relevanceLanguage="en").execute()
            ids += [it["id"]["videoId"] for it in res.get("items", [])]
        except Exception as e:  # noqa: BLE001
            log(f"Search failed ({kw}):", str(e)[:100])
    me = ""
    try:
        me = yt.channels().list(part="id", mine=True).execute()["items"][0]["id"]
    except Exception:  # noqa: BLE001
        pass
    out = []
    ids = list(dict.fromkeys(ids))
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50])).execute().get("items", []):
            m = re.match(r"PT(?:(\d+)M)?(?:(\d+)S)?$", v["contentDetails"].get("duration", ""))
            secs = (int(m.group(1) or 0) * 60 + int(m.group(2) or 0)) if m else 999
            views = int(v.get("statistics", {}).get("viewCount", 0))
            if (secs > 180 or views < st.get("min_views", 200000) or v["snippet"]["channelId"] == me
                    or v["snippet"].get("categoryId") not in st.get("categories", ["27", "28"])):   # Education, Science & Tech
                continue
            out.append({"id": v["id"], "title": v["snippet"]["title"], "channel": v["snippet"]["channelTitle"],
                        "channel_id": v["snippet"]["channelId"], "views": views, "seconds": secs,
                        "published": v["snippet"]["publishedAt"][:10]})
    out.sort(key=lambda x: -x["views"])
    picked, per_channel = [], {}
    for v in out:   # max 2 per channel, so we learn from different creators
        if per_channel.get(v["channel_id"], 0) >= 2:
            continue
        per_channel[v["channel_id"]] = per_channel.get(v["channel_id"], 0) + 1
        picked.append(v)
    log(f"Viral Shorts found: {len(out)}, studying {min(n, len(picked))}")
    return picked[:n]


def owner_links():
    """Links the owner put in inspiration.txt (one per line)."""
    p = ROOT / "inspiration.txt"
    if not p.exists():
        return []
    ids = re.findall(r"(?:v=|shorts/|youtu\.be/)([A-Za-z0-9_-]{11})", p.read_text(encoding="utf-8"))
    return [{"id": i, "title": "(owner pick)", "channel": "", "views": 0, "seconds": 0, "owner_pick": True}
            for i in dict.fromkeys(ids)]


def run(cfg, limit=None):
    n = limit or cfg.get("study", {}).get("videos", 12)
    vids = owner_links()[:4] + find_viral(cfg, n)
    vids = vids[:n + 4]
    done = []
    for v in vids:
        url = f"https://www.youtube.com/watch?v={v['id']}"
        try:
            a = ask(cfg, ANALYSE, json_mode=True, temperature=0.2, video_url=url, attempts=2)
            done.append({**v, "analysis": a})
            log(f"Studied: {v['title'][:60]} ({v['views']:,} views) - hook: {str(a.get('hook_type', ''))[:60]}")
        except Exception as e:  # noqa: BLE001
            log(f"Could not study {url}:", str(e)[:150])
    if not done:
        log("No video could be studied - playbook unchanged")
        return
    ours = ""
    try:
        learn = json.loads((DATA / f"learning_{CHANNEL['id']}.json").read_text(encoding="utf-8"))
        ours = json.dumps([{k: x.get(k) for k in ("title", "views", "averageViewPercentage", "notes")}
                           for x in learn.get("videos", [])][-10:], ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass
    table = json.dumps([{"title": d["title"], "views": d["views"], "seconds": d["seconds"], **d["analysis"]} for d in done],
                       ensure_ascii=False)
    pb = ask(cfg, f"""You are the head writer of the science/tech YouTube channel "{cfg['channel']['name']}".
Below are analyses of the most-viewed Shorts in our niche this month, and our own recent results.
Find the PATTERNS that the successful ones share and turn them into concrete rules for our script writer.
Rules must be about structure, hooks, pacing, language, visuals and sound - NEVER copy anyone's sentences,
titles or catchphrases. Only rules supported by several videos. If something differs a lot between videos, say what works when.
OUR FIXED FORMAT (rules must fit it, don't contradict it): narrated Shorts (always a voice-over) built from real/stock/NASA
footage plus our own animated graphics; length is fixed (news 20-25 s, big question 30-35 s); every Short ends with our line
"Follow Tomorrowly for tomorrow's tech, today."; facts must be true.

VIRAL SHORTS: {table}
OUR RECENT VIDEOS: {ours or '(no data yet)'}

Return ONLY JSON:
{{
 "shorts_rules": ["8-12 short, concrete, testable rules for writing our Shorts (e.g. 'Name the real subject in the first sentence')"],
 "visual_sound_notes": ["3-6 notes about visuals, captions, cuts, music"],
 "typical": {{"seconds": 0, "words_per_second": 0.0, "cuts_per_10_seconds": 0.0}},
 "summary_roman_urdu": "4-6 sentences in Roman Urdu for the channel owner: what is working this month and what we should change"
}}""", json_mode=True, temperature=0.3)
    pb["updated"] = dt.date.today().isoformat()
    pb["studied"] = [{"title": d["title"], "views": d["views"], "id": d["id"]} for d in done]
    DATA.mkdir(exist_ok=True)
    (DATA / f"study_{CHANNEL['id']}.json").write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / f"playbook_{CHANNEL['id']}.json").write_text(json.dumps(pb, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Playbook updated from {len(done)} viral Shorts:")
    for r in pb.get("shorts_rules", []):
        log("  -", r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default="future")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    cfg = load_config(a.channel)
    run(cfg, a.limit)


if __name__ == "__main__":
    main()
