"""YouTube upload via the official Data API (OAuth refresh token stored as GitHub secret)."""
import re

from .common import log, secret, yt_secret_suffix

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]


def _service():
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=_creds(), cache_discovery=False)


def _creds():
    from google.oauth2.credentials import Credentials
    return Credentials(None, refresh_token=secret("YT_REFRESH_TOKEN" + yt_secret_suffix()),
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=secret("YT_CLIENT_ID"), client_secret=secret("YT_CLIENT_SECRET"),
                        scopes=SCOPES)


def ready():
    return all(secret(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN" + yt_secret_suffix()))


def clean_tags(tags, budget=450):
    """YouTube rejects the whole upload ("invalidTags") if tags contain < or >, or all tags together pass 500
    characters (a tag with a space counts 2 extra for its quotes, plus 1 per comma). Keep it safely under."""
    out, seen, used = [], set(), 0
    for t in tags or []:
        t = " ".join(re.sub(r"<[^>]*>", " ", str(t)).replace("<", " ").replace(">", " ").replace(",", " ").replace('"', "").lstrip("#").split())[:60]
        if len(t) < 2 or t.lower() in seen:
            continue
        cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)
        if used + cost > budget:
            break
        out.append(t)
        seen.add(t.lower())
        used += cost
    return out


def upload(cfg, video, meta, thumb=None):
    from googleapiclient.http import MediaFileUpload
    yt = _service()
    lang = {"urdu": "ur", "hindi": "hi", "english": "en"}[cfg["channel"]["language"]]
    privacy = cfg["upload"].get(f"{meta.get('kind', '')}_privacy") or cfg["upload"]["privacy"]
    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["description"][:4900],
            "tags": clean_tags(meta.get("tags", []))[:30],
            "categoryId": str(cfg["upload"]["category_id"]),
            "defaultLanguage": lang,
            "defaultAudioLanguage": lang,
        },
        "status": {"privacyStatus": privacy,
                   "selfDeclaredMadeForKids": bool(cfg["upload"]["made_for_kids"]),
                   # honest label when realistic AI images are used (YouTube's altered/synthetic content disclosure)
                   "containsSyntheticMedia": bool(meta.get("synthetic"))},
    }
    for attempt in range(2):
        req = yt.videos().insert(part="snippet,status", body=body,
                                 media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024,
                                                            resumable=True, mimetype="video/mp4"))
        resp = None
        try:
            while resp is None:
                status, resp = req.next_chunk()
                if status:
                    log(f"Upload {int(status.progress() * 100)}%")
            break
        except Exception as e:  # noqa: BLE001
            if attempt == 0 and "invalidTags" in str(e):   # never lose a finished video over its tags
                log("YouTube rejected the tags - uploading again without tags:", body["snippet"]["tags"])
                body["snippet"]["tags"] = []
                continue
            raise
    vid = resp["id"]
    log(f"Uploaded: https://youtu.be/{vid}")
    got = resp.get("status", {}).get("privacyStatus")
    if privacy == "public" and got and got != "public":
        log("NOTE: YouTube ne video ko private rakha hai (API project audit ki zaroorat). "
            "YouTube Studio se public kar dein - SETUP guide dekhein.")
    if thumb:
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
            log("Thumbnail set")
        except Exception as e:  # noqa: BLE001
            log("Thumbnail set nahi hua (channel phone-verify karein):", str(e)[:150])
    return vid
