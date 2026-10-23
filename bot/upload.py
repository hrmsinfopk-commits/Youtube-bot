"""YouTube upload via the official Data API (OAuth refresh token stored as GitHub secret)."""
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


def upload(cfg, video, meta, thumb=None):
    from googleapiclient.http import MediaFileUpload
    yt = _service()
    lang = {"urdu": "ur", "hindi": "hi", "english": "en"}[cfg["channel"]["language"]]
    privacy = cfg["upload"].get(f"{meta.get('kind', '')}_privacy") or cfg["upload"]["privacy"]
    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["description"][:4900],
            "tags": meta.get("tags", [])[:30],
            "categoryId": str(cfg["upload"]["category_id"]),
            "defaultLanguage": lang,
            "defaultAudioLanguage": lang,
        },
        "status": {"privacyStatus": privacy,
                   "selfDeclaredMadeForKids": bool(cfg["upload"]["made_for_kids"]),
                   # honest label when realistic AI images are used (YouTube's altered/synthetic content disclosure)
                   "containsSyntheticMedia": bool(meta.get("synthetic"))},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024,
                                                        resumable=True, mimetype="video/mp4"))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            log(f"Upload {int(status.progress() * 100)}%")
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
