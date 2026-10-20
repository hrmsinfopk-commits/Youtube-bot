"""YouTube upload via the official Data API (OAuth refresh token stored as GitHub secret)."""
from .common import log, secret

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(None, refresh_token=secret("YT_REFRESH_TOKEN"),
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=secret("YT_CLIENT_ID"), client_secret=secret("YT_CLIENT_SECRET"),
                        scopes=SCOPES)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def ready():
    return all(secret(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def upload(cfg, video, meta, thumb=None):
    from googleapiclient.http import MediaFileUpload
    yt = _service()
    lang = {"urdu": "ur", "hindi": "hi", "english": "en"}[cfg["channel"]["language"]]
    privacy = cfg["upload"]["privacy"]
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
                   "selfDeclaredMadeForKids": bool(cfg["upload"]["made_for_kids"])},
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
