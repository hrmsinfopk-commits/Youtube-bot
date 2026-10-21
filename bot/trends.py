"""Find what to make next: fresh real news + what people are watching on YouTube right now.

1) Headlines from Google News RSS, NASA news and Hacker News (all free, no key).
2) YouTube Data API (same login as uploads): most-viewed videos of the last 7 days for our keywords
   + the Science & Technology trending chart -> shows demand and competition.
3) Gemini picks the topic with high demand, fresh news and room for us, and writes a short FACT SHEET
   in its own words (we never copy articles) plus the search keywords people use.
"""
import datetime as dt
import html
import json
import random
import re
import xml.etree.ElementTree as ET

import requests

from .common import DATA, log
from .llm import ask

UA = {"User-Agent": "Mozilla/5.0 (compatible; tomorrowly-bot/1.0)"}
WEAPON_WORDS = ("weapon", "missile", "military", "drone strike", "fighter jet", "tank", "laser weapon", "hypersonic",
                "army", "navy", "air force", "defense", "defence", "warship", "bomb")


def _clean(t, n=260):
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    return re.sub(r"\s+", " ", t).strip()[:n]


def _rss(url, source, limit=15):
    try:
        r = requests.get(url, headers=UA, timeout=25)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except Exception as e:  # noqa: BLE001
        log(f"News feed failed ({source}):", str(e)[:80])
        return []
    out = []
    for it in root.iter("item"):
        title = _clean(it.findtext("title"), 200)
        if not title:
            continue
        out.append({"title": title, "summary": _clean(it.findtext("description")),
                    "date": (it.findtext("pubDate") or "")[:25], "source": source,
                    "link": (it.findtext("link") or "").strip()})
        if len(out) >= limit:
            break
    return out


def google_news(query, region="US", limit=12):
    url = ("https://news.google.com/rss/search?q=" + requests.utils.quote(f"{query} when:7d")
           + f"&hl=en-{region}&gl={region}&ceid={region}:en")
    items = _rss(url, "Google News", limit)
    for i in items:  # Google News titles end with " - Publisher"
        if " - " in i["title"]:
            i["title"], pub = i["title"].rsplit(" - ", 1)
            i["source"] = pub
        i["summary"] = ""   # Google's description just repeats the headline
    return items


def nasa_news():
    items = []
    for url in ("https://www.nasa.gov/news-release/feed/", "https://www.nasa.gov/feed/"):
        items += _rss(url, "NASA", 12)
    return items


def hacker_news(limit=40):
    try:
        ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=20).json()[:limit]
    except Exception:  # noqa: BLE001
        return []
    out = []
    for i in ids:
        try:
            s = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json", timeout=10).json()
        except Exception:  # noqa: BLE001
            continue
        if s and s.get("title") and s.get("score", 0) >= 150:
            out.append({"title": s["title"], "summary": "", "source": "Hacker News", "date": "",
                        "link": s.get("url", ""), "score": s.get("score")})
    return out


def collect_news(cfg):
    tr = cfg["trends"]
    news = []
    for q in tr["news_queries"]:
        news += google_news(q, tr.get("region", "US"))
    news += nasa_news()
    news += hacker_news()
    seen, uniq = set(), []
    for n in news:
        key = re.sub(r"[^a-z0-9 ]", "", n["title"].lower())[:60]
        if key and key not in seen:
            seen.add(key)
            uniq.append(n)
    log(f"News headlines collected: {len(uniq)}")
    return uniq


# ------------------------------------------------------------------ YouTube demand
def youtube_demand(cfg):
    from . import upload
    if not upload.ready():
        log("YouTube login missing - trend data from news only")
        return []
    try:
        yt = upload._service()
    except Exception as e:  # noqa: BLE001
        log("YouTube API unavailable:", str(e)[:100])
        return []
    tr = cfg["trends"]
    since = (dt.datetime.utcnow() - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids, src = [], {}
    for kw in tr["youtube_keywords"]:
        try:
            res = yt.search().list(part="id", q=kw, type="video", order="viewCount", publishedAfter=since,
                                   maxResults=8, regionCode=tr.get("region", "US"), relevanceLanguage="en").execute()
            for it in res.get("items", []):
                vid = it["id"]["videoId"]
                ids.append(vid)
                src[vid] = kw
        except Exception as e:  # noqa: BLE001
            log(f"YouTube search failed ({kw}):", str(e)[:100])
            break
    try:
        chart = yt.videos().list(part="id", chart="mostPopular", regionCode=tr.get("region", "US"),
                                 videoCategoryId="28", maxResults=15).execute()
        for it in chart.get("items", []):
            ids.append(it["id"])
            src[it["id"]] = "trending: science & tech"
    except Exception as e:  # noqa: BLE001
        log("Trending chart failed:", str(e)[:100])
    out = []
    ids = list(dict.fromkeys(ids))
    for i in range(0, len(ids), 50):
        try:
            res = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50])).execute()
        except Exception as e:  # noqa: BLE001
            log("YouTube video stats failed:", str(e)[:100])
            break
        for v in res.get("items", []):
            sn, stt = v["snippet"], v.get("statistics", {})
            out.append({"title": sn["title"], "channel": sn["channelTitle"], "views": int(stt.get("viewCount", 0)),
                        "published": sn["publishedAt"][:10], "tags": (sn.get("tags") or [])[:12],
                        "found_by": src.get(v["id"], ""), "duration": v["contentDetails"].get("duration", "")})
    out.sort(key=lambda x: -x["views"])
    log(f"YouTube videos analysed: {len(out)}")
    return out


# ------------------------------------------------------------------ pick the topic
def _weapon_share(history):
    recent = history["videos"][-10:]
    if not recent:
        return 0.0
    return sum(any(w in v.get("topic", "").lower() for w in WEAPON_WORDS) for v in recent) / len(recent)


STOP = set("""a an the and or of to in on for with by from at as is are was were be this that these those its it's it
how why what who when where which new just now first big real really vs versus inside into about after before over
can could will would may might than then their they them our your you we his her he she has have had not no yes
breaking down explained explaining explain story video short shorts actually make makes made using use""".split())


def _words(t):
    import re as _re
    w = {x.strip("'").removesuffix("'s") for x in _re.findall(r"[a-z0-9'\-]+", t.lower())}
    return {x for x in w if len(x) > 2 and x not in STOP}


def _clash(topic, past):
    """Returns the past topic this one repeats (same story / same main subject), else None."""
    tw = _words(topic)
    for p in past:
        pw = _words(p)
        common = tw & pw
        if len(common) >= 3 or (pw and len(common) >= 2 and len(common) / min(len(tw), len(pw)) >= 0.5):
            return p
    return None


def find_topic(cfg, history, kind, learning=None):
    news = collect_news(cfg)
    if not news:
        return None
    yt = youtube_demand(cfg)
    past = [v.get("topic", "") for v in history["videos"]][-60:]
    recent = [v.get("topic", "") for v in history["videos"]][-14:]   # about the last week, Shorts + long
    long_fmt = None
    if kind == "long":
        fmts = cfg["long"].get("formats", ["deep dive"])
        n_long = sum(1 for v in history["videos"] if v.get("type") == "long")
        long_fmt = fmts[n_long % len(fmts)]
    weapons_ok = _weapon_share(history) < cfg["trends"].get("avoid_weapons_ratio", 0.2)
    random.shuffle(news)
    news_txt = "\n".join(f"[{i}] {n['title']} ({n['source']}{', ' + n['date'] if n['date'] else ''})"
                         + (f" - {n['summary']}" if n['summary'] else "") for i, n in enumerate(news[:160]))
    yt_txt = "\n".join(f"- \"{v['title']}\" | {v['views']:,} views | {v['published']} | {v['channel']} | via {v['found_by']}"
                       for v in yt[:60]) or "(no YouTube data available)"
    learn_txt = ""
    if learning and learning.get("insights"):
        learn_txt = "\nWHAT WORKED / DIDN'T ON OUR CHANNEL SO FAR:\n" + "\n".join(f"- {x}" for x in learning["insights"][:10]) + "\n"
    what = ("a YouTube Short (one punchy idea)" if kind == "short" else
            "a long video in format: WEEKLY ROUNDUP of the 5 biggest stories" if long_fmt == "weekly roundup" else
            "a long DEEP DIVE video on one big story")
    prompt = f"""You are the content strategist for the YouTube channel "{cfg['channel']['name']}".
Niche: {cfg['channel']['niche']}
Audience: {cfg['channel']['audience']}
We need to choose the topic for {what}.

FRESH NEWS (last 7 days):
{news_txt}

WHAT IS GETTING VIEWS ON YOUTUBE RIGHT NOW (last 7 days, our keywords + Science & Tech trending):
{yt_txt}
{learn_txt}
ALREADY MADE (do not repeat): {"; ".join(past) or "nothing yet"}
MADE IN THE LAST FEW DAYS - the new topic must be a COMPLETELY DIFFERENT story and subject (not the same mission, spacecraft,
company, product or technology, not a new angle on it):
{chr(10).join("- " + t for t in recent) or "- nothing yet"}{{banned}}
{"Military/weapons topics are allowed this time." if weapons_ok else "Do NOT choose a military/weapons topic this time."}

Choose the best topic by: (1) fresh, real news from the list, (2) proven audience demand (similar videos getting many views),
(3) room for us: avoid topics where huge channels already uploaded many near-identical videos unless we have a clearly different angle,
(4) a strong curiosity hook that works for a global English audience,
(5) something to SHOW: prefer stories with free real visuals (NASA/space, science, nature, public institutions) or that can be
explained with generic footage; avoid stories whose whole point is seeing one brand-new product nobody has free images of -
unless you turn it into an explainer (e.g. "how flying cars actually fly"). Never pick rumours, celebrity gossip or politics.

Return ONLY JSON:
{{
 "topic": "short working title",
 "angle": "the specific angle/hook that makes our video different",
 "news_ids": [list of the [numbers] of the headlines used{', exactly 5 different stories for the roundup' if long_fmt == 'weekly roundup' else ''}],
 "why": "2 sentences: demand evidence (views of similar videos) + freshness + competition",
 "keywords": ["10-15 phrases people search/watch for this topic, taken from the YouTube titles/tags above and common search wording"],
 "facts": ["8-25 short factual points rewritten in your own words, only from the chosen headlines/summaries or well-established background knowledge; mark anything that is only announced/planned/claimed"]
}}"""
    banned, res = [], None
    for attempt in range(3):
        extra = ("\nREJECTED because they repeat a recent video - choose something else entirely: " + "; ".join(banned)) if banned else ""
        try:
            res = ask(cfg, prompt.replace("{banned}", extra), json_mode=True, temperature=0.6 + 0.15 * attempt)
        except Exception as e:  # noqa: BLE001
            log("Topic selection failed:", str(e)[:120])
            return None
        hit = _clash(f"{res.get('topic', '')} {res.get('angle', '')}", recent)
        if not hit:
            break
        log(f"Topic '{res.get('topic')}' repeats recent video '{hit[:70]}' - choosing again")
        banned.append(res.get("topic", ""))
    else:
        log("Could not find a fresh topic - skipping this run instead of repeating")
        return None
    used = [news[i] for i in res.get("news_ids", []) if isinstance(i, int) and 0 <= i < len(news)]
    # more angles on the same story from other outlets -> better facts
    if res.get("topic"):
        extra = google_news(res["topic"], cfg["trends"].get("region", "US"), limit=10)
        if extra:
            try:
                more = ask(cfg, "From these headlines about \"" + res["topic"] + "\", list up to 10 additional short factual points in your "
                           "OWN words (no copying), only things clearly stated; mark claims/plans as such. Return JSON {\"facts\": [...]}.\n"
                           + "\n".join(f"- {n['title']} ({n['source']})" for n in extra), json_mode=True, temperature=0.3)
                res["facts"] = (res.get("facts") or []) + (more.get("facts") or [])
            except Exception:  # noqa: BLE001
                pass
    brief = {"topic": res.get("topic"), "angle": res.get("angle", ""), "why": res.get("why", ""),
             "keywords": res.get("keywords", []), "facts": res.get("facts", []), "long_format": long_fmt,
             "sources": [{"title": n["title"], "source": n["source"], "link": n["link"]} for n in used],
             "youtube_top": [{"title": v["title"], "views": v["views"]} for v in yt[:10]]}
    if not brief["topic"]:
        return None
    log(f"Trend topic: {brief['topic']} | why: {brief['why']}")
    DATA.mkdir(exist_ok=True)
    (DATA / f"last_topic_{kind}.json").write_text(json.dumps(brief, ensure_ascii=False, indent=1), encoding="utf-8")
    return brief


def brief_for(cfg, topic, kind):
    """For a topic you queued yourself: collect today's headlines about it and turn them into a fact sheet
    (own words, no copying) + search keywords, so the script is based on real, current reporting."""
    items = google_news(topic, cfg["trends"].get("region", "US"), limit=15)
    if not items:
        return None
    try:
        res = ask(cfg, f"Topic for our next YouTube video: \"{topic}\".\nRecent headlines:\n"
                  + "\n".join(f"- {n['title']} ({n['source']})" for n in items)
                  + "\nReturn ONLY JSON {\"facts\": [\"8-20 short factual points in your OWN words, only what the headlines clearly"
                  " support or well-established background; mark announced/planned/claimed things as such\"], "
                  "\"keywords\": [\"10 phrases people search for this\"]}", json_mode=True, temperature=0.3)
    except Exception as e:  # noqa: BLE001
        log("Fact sheet for queued topic failed:", str(e)[:100])
        return None
    long_fmt = None
    if kind == "long":
        long_fmt = "deep dive"
    log(f"Fact sheet for queued topic: {len(res.get('facts', []))} facts")
    return {"topic": topic, "angle": "", "why": "Topic chosen by channel owner", "keywords": res.get("keywords", []),
            "facts": res.get("facts", []), "long_format": long_fmt,
            "sources": [{"title": n["title"], "source": n["source"], "link": n["link"]} for n in items[:8]],
            "youtube_top": []}
