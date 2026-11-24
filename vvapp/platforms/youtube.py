"""YouTube Shorts upload (YouTube Data API v3, free)."""
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import os

from .. import db
from ..config import env


def post(video: dict, local_file: str, cfg: dict) -> dict:
    yt_cfg = cfg.get("youtube", {})
    creds = Credentials(
        None,
        refresh_token=os.environ.get("YOUTUBE_REFRESH_TOKEN") or db.get_token("youtube")["refresh_token"],
        client_id=env("YOUTUBE_CLIENT_ID"),
        client_secret=env("YOUTUBE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    tags = video.get("hashtags") or []
    script = video.get("script") or {}
    series = script.get("series")
    description = (f"{series} - a new one every morning. Subscribe so you don't miss tomorrow's!\n\n" if series else "") \
        + f"{video.get('caption', '')}\n\n" + " ".join(f"#{t}" for t in tags) + " #Shorts"
    publish_at = script.get("publish_at")
    body = {
        "snippet": {
            "title": video["title"][:100],
            "description": description[:4900],
            "tags": tags[:15],
            "categoryId": str(script.get("youtube_category") or yt_cfg.get("category_id", "28")),
        },
        "status": {
            "privacyStatus": yt_cfg.get("privacy", "public"),
            "selfDeclaredMadeForKids": bool(yt_cfg.get("made_for_kids", False)),
            "containsSyntheticMedia": bool(yt_cfg.get("synthetic_media", False)),
        },
    }
    if publish_at:  # scheduled: YouTube keeps it private and makes it public at publish_at
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at
    media = MediaFileUpload(local_file, mimetype="video/mp4", resumable=True, chunksize=-1)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    vid = response["id"]
    privacy = response.get("status", {}).get("privacyStatus", "")
    note = ""
    if publish_at:
        note = f"Scheduled to go public at {publish_at} (UTC)"
    elif privacy == "private" and yt_cfg.get("privacy") == "public":
        note = "Uploaded as private (API project not yet audited). Make it public in YouTube Studio."
    return {"ok": True, "id": vid, "url": f"https://youtube.com/shorts/{vid}", "note": note}
