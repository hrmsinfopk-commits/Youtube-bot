"""Daily self-check: how are our videos doing, why, and what should the bot do differently?

python -m bot.analytics            -> refresh numbers + learning (daily)
python -m bot.analytics --report   -> also write REPORT.md (weekly, in Roman Urdu)
"""
import argparse
import datetime as dt
import json
import math

from .common import CHANNEL, DATA, ROOT, load_config, load_history, log
from .llm import ask

METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained"


def _services():
    from googleapiclient.discovery import build
    from . import upload
    yt = upload._service()
    ya = build("youtubeAnalytics", "v2", credentials=upload._creds(), cache_discovery=False)
    return yt, ya


def _iso(d):
    return d.strftime("%Y-%m-%d")


def _rows(resp):
    cols = [c["name"] for c in resp.get("columnHeaders", [])]
    return [dict(zip(cols, r)) for r in resp.get("rows", []) or []]


def video_stats(ya, ids, start):
    out = {}
    today = _iso(dt.date.today())
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        try:
            resp = ya.reports().query(ids="channel==MINE", startDate=start, endDate=today, metrics=METRICS,
                                      dimensions="video", filters="video==" + ",".join(chunk), maxResults=200).execute()
            for r in _rows(resp):
                out[r["video"]] = r
        except Exception as e:  # noqa: BLE001
            log("Analytics query failed:", str(e)[:150])
    return out


def retention(ya, vid, start):
    try:
        resp = ya.reports().query(ids="channel==MINE", startDate=start, endDate=_iso(dt.date.today()),
                                  metrics="audienceWatchRatio", dimensions="elapsedVideoTimeRatio",
                                  filters=f"video=={vid}").execute()
        return [(float(r["elapsedVideoTimeRatio"]), float(r["audienceWatchRatio"])) for r in _rows(resp)]
    except Exception as e:  # noqa: BLE001
        log(f"Retention for {vid} failed:", str(e)[:100])
        return []


def traffic(ya, vid, start):
    try:
        resp = ya.reports().query(ids="channel==MINE", startDate=start, endDate=_iso(dt.date.today()),
                                  metrics="views", dimensions="insightTrafficSourceType",
                                  filters=f"video=={vid}").execute()
        rows = _rows(resp)
        tot = sum(r["views"] for r in rows) or 1
        return {r["insightTrafficSourceType"]: round(100 * r["views"] / tot) for r in rows}
    except Exception:  # noqa: BLE001
        return {}


def biggest_drop(curve, seconds, scenes):
    """Where do people leave? returns (second, scene caption) of the steepest fall after the first 5%."""
    pts = [p for p in curve if p[0] >= 0.05]
    if len(pts) < 3:
        return None
    worst, at = 0, None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if y0 - y1 > worst:
            worst, at = y0 - y1, x1
    if at is None or worst < 0.03:
        return None
    sec = at * (seconds or 0)
    line = ""
    for t0, cap in scenes or []:
        if t0 <= sec:
            line = cap
    return {"second": round(sec, 1), "drop": round(worst * 100, 1), "line": line}


def diagnose(v, avg):
    """Plain-language reason, comparing the video with the channel average."""
    views, pct = v.get("views", 0), v.get("averageViewPercentage", 0)
    a_views, a_pct = avg["views"] or 1, avg["pct"] or 1
    notes = []
    if views < 0.5 * a_views and pct >= a_pct:
        notes.append("Jo log aaye unhon ne achhi dekhi, lekin bohat kam log aaye: topic/title/thumbnail ne kashish nahi ki.")
    if pct < 0.75 * a_pct:
        notes.append("Log jaldi chhod gaye: hook ya shuru ka hissa kamzor tha.")
    if views >= 1.5 * a_views:
        notes.append("Average se kaafi behtar: yeh topic/andaaz dobara try karna chahiye.")
    if v.get("comments", 0) == 0 and views > 300:
        notes.append("Comments nahi aaye: aakhri sawal behtar hona chahiye.")
    if v.get("drop"):
        d = v["drop"]
        notes.append(f"Sab se zyada log {d['second']}s par chhod gaye ({d['drop']}% gire) - wahan line thi: \"{d['line'][:80]}\".")
    return notes


def seo_audit(yt, ids):
    """Show exactly what YouTube has for our latest uploads (title, tags, description, chapters...)."""
    import re as _re
    try:
        items = yt.videos().list(part="snippet,status,contentDetails", id=",".join(ids)).execute().get("items", [])
    except Exception as e:  # noqa: BLE001
        log("SEO audit failed:", str(e)[:120])
        return
    for v in items:
        sn, st = v["snippet"], v["status"]
        desc = sn.get("description", "")
        log("SEO AUDIT -------------------------------------------")
        log(f"  Video: https://youtu.be/{v['id']} | {st.get('privacyStatus')} | {v['contentDetails'].get('duration')}")
        log(f"  Title ({len(sn['title'])} chars): {sn['title']}")
        log(f"  Tags ({len(sn.get('tags') or [])}): {', '.join(sn.get('tags') or [])}")
        log(f"  Category: {sn.get('categoryId')} | Language: {sn.get('defaultAudioLanguage')} / {sn.get('defaultLanguage')}")
        log(f"  Description ({len(desc)} chars), first lines: {desc[:300]!r}")
        log(f"  Hashtags: {' '.join(_re.findall(r'#[A-Za-z0-9_]+', desc)) or 'none'} | Chapters: {'yes' if _re.search(r'^0?0:00', desc, _re.M) else 'no'}"
            f" | Credits line: {'yes' if 'credits' in desc.lower() or 'reporting from' in desc.lower() else 'no'}")
        log(f"  Description end: {desc[-220:]!r}")


def run_analytics(cfg, write_report=False):
    if not __import__("bot.upload", fromlist=["ready"]).ready():
        log("YouTube login missing - analytics skipped")
        return
    yt, ya = _services()
    try:
        me = yt.channels().list(part="snippet,statistics", mine=True).execute()["items"][0]
        log(f"Logged in as YouTube channel: {me['snippet']['title']} (subscribers: {me['statistics'].get('subscriberCount')})")
    except Exception as e:  # noqa: BLE001
        log("Channel check failed:", str(e)[:200])
        return
    hist = load_history()
    ours = [v for v in hist["videos"] if v.get("youtube_id")]
    if not ours:
        log("No uploaded videos yet")
        return
    seo_audit(yt, [v["youtube_id"] for v in ours[-4:]])
    start = min(v["date"][:10] for v in ours)
    stats = video_stats(ya, [v["youtube_id"] for v in ours], start)
    # channel totals
    chan = {}
    try:
        c = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
        chan = {"subscribers": int(c.get("subscriberCount", 0)), "total_views": int(c.get("viewCount", 0)),
                "videos": int(c.get("videoCount", 0))}
        y = ya.reports().query(ids="channel==MINE", startDate=_iso(dt.date.today() - dt.timedelta(days=365)),
                               endDate=_iso(dt.date.today()), metrics="estimatedMinutesWatched,views").execute()
        r = _rows(y)
        chan["watch_hours_12m"] = round((r[0]["estimatedMinutesWatched"] if r else 0) / 60, 1)
    except Exception as e:  # noqa: BLE001
        log("Channel totals failed:", str(e)[:120])

    rows = []
    for v in ours:
        s = stats.get(v["youtube_id"])
        if not s:
            continue
        age = (dt.date.today() - dt.date.fromisoformat(v["date"][:10])).days
        row = {**v, **{k: s.get(k, 0) for k in METRICS.split(",")}, "age_days": age}
        if age <= 21:  # detailed look only at recent videos (saves API calls)
            row["drop"] = biggest_drop(retention(ya, v["youtube_id"], v["date"][:10]), v.get("seconds"), v.get("scene_times"))
            row["traffic"] = traffic(ya, v["youtube_id"], v["date"][:10])
        rows.append(row)

    learning = {"updated": _iso(dt.date.today()), "channel": chan, "style_scores": {}, "insights": [], "videos": []}
    for kind in ("short", "long"):
        group = [r for r in rows if r.get("type") == kind and r["age_days"] >= 2]
        if not group:
            continue
        avg = {"views": sum(r["views"] for r in group) / len(group),
               "pct": sum(r["averageViewPercentage"] for r in group) / len(group)}
        for r in group:
            # score: retention matters as much as reach (log views), relative to channel average
            r["score"] = round((r["averageViewPercentage"] / (avg["pct"] or 1)) * 0.5 +
                               (math.log1p(r["views"]) / (math.log1p(avg["views"]) or 1)) * 0.5, 2)
            r["notes"] = diagnose(r, avg)
        by_style = {}
        for r in group:
            by_style.setdefault(r.get("style", "?"), []).append(r["score"])
        for st, sc in by_style.items():
            prev = learning["style_scores"].get(st)
            val = sum(sc) / len(sc)
            learning["style_scores"][st] = round((prev + val) / 2, 2) if prev else round(val, 2)
    for r in rows:
        learning["videos"].append({k: r.get(k) for k in ("title", "type", "style", "views", "averageViewPercentage",
                                                          "likes", "comments", "shares", "subscribersGained",
                                                          "score", "notes", "traffic", "age_days", "youtube_id")})

    if len([r for r in rows if r["age_days"] >= 2]) >= 3:
        try:
            table = json.dumps(learning["videos"][-40:], ensure_ascii=False)
            res = ask(cfg, "You analyse a small YouTube channel's performance data and find patterns the content bot should act on.\n"
                      f"Data (per video): {table}\nReturn ONLY JSON {{\"insights\": [\"5-8 short, concrete lessons in English for choosing "
                      "topics, hooks, styles, length and titles - e.g. 'Space topics get 2x the views of AI topics', "
                      "'Shorts over 45s lose viewers at the end'\"]}}. Only conclusions supported by the numbers; say when data is too thin.",
                      json_mode=True, temperature=0.3)
            learning["insights"] = res.get("insights", [])[:8]
        except Exception as e:  # noqa: BLE001
            log("Insights failed:", str(e)[:100])

    DATA.mkdir(exist_ok=True)
    (DATA / f"learning_{CHANNEL['id']}.json").write_text(json.dumps(learning, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Analytics updated: {len(rows)} videos, subs={chan.get('subscribers')}, watch_hours_12m={chan.get('watch_hours_12m')}")
    if write_report:
        write_weekly_report(cfg, learning, rows)


def write_weekly_report(cfg, learning, rows):
    chan = learning.get("channel", {})
    week = [r for r in rows if r["age_days"] <= 7]
    best = sorted(rows, key=lambda r: -(r.get("score") or 0))[:3]
    worst = sorted([r for r in rows if r.get("score") is not None], key=lambda r: r["score"])[:3]
    subs, hours = chan.get("subscribers", 0), chan.get("watch_hours_12m", 0)

    def line(r):
        return (f"| {r['title'][:60]} | {r['type']} | {r['views']:,} | {r['averageViewPercentage']:.0f}% | "
                f"{r['likes']} | {r['comments']} | {r['subscribersGained']} |")

    md = [f"# 📊 {cfg['channel']['name']} - Haftawar Report ({learning['updated']})", "",
          "## Monetization ki taraf safar", "",
          f"- **Subscribers:** {subs:,} / 1,000 ({min(100, subs / 10):.0f}%)",
          f"- **Watch hours (12 mahine):** {hours:,} / 4,000 ({min(100, hours / 40):.0f}%)", "",
          "## Is hafte ki videos", "",
          "| Video | Qisam | Views | Kitna dekha | Likes | Comments | Naye subs |", "|---|---|---|---|---|---|---|"]
    md += [line(r) for r in week] or ["| (is hafte koi video data ke saath nahi) | | | | | | |"]
    md += ["", "## ⭐ Sab se achhi videos", ""]
    for r in best:
        md.append(f"- **{r['title'][:70]}** - {r['views']:,} views, {r['averageViewPercentage']:.0f}% dekhi gayi")
        md += [f"  - {n}" for n in r.get("notes", [])]
    md += ["", "## ⚠️ Sab se kamzor videos (aur wajah)", ""]
    for r in worst:
        md.append(f"- **{r['title'][:70]}** - {r['views']:,} views, {r['averageViewPercentage']:.0f}% dekhi gayi")
        md += [f"  - {n}" for n in r.get("notes", [])]
    if learning.get("style_scores"):
        md += ["", "## 🎬 Kaun sa andaaz chal raha hai (1.0 = average)", ""]
        for st, sc in sorted(learning["style_scores"].items(), key=lambda x: -x[1]):
            md.append(f"- {sc:.2f} - {st.split(':')[0]}")
    if learning.get("insights"):
        md += ["", "## 🧠 Bot ne kya seekha (aagey isi hisaab se topics/andaaz chunega)", ""]
        md += [f"- {x}" for x in learning["insights"]]
    md += ["", "## ✅ Aap ke liye (5 minute)", "",
           "- YouTube Studio mein har video ka **impressions click-through rate** dekhein (yeh API se nahi milta). 4% se kam ho to title/thumbnail kamzor hai.",
           "- Achhe comments ka jawab dein aur pin karein - engagement barhta hai.",
           "- Koi khaas trending khabar ho to `topics.txt` mein likh dein.", "",
           "_Note: naye channel par shuru ke 2-3 hafte data kam hota hai, is liye andaze kamzor ho sakte hain._"]
    (ROOT / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    log("REPORT.md written")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default="future")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    cfg = load_config(a.channel)
    run_analytics(cfg, write_report=a.report or dt.date.today().weekday() == 0)


if __name__ == "__main__":
    main()
