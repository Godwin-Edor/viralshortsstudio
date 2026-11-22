"""YouTube Shorts upload (YouTube Data API v3, free)."""
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ..config import env


def post(video: dict, local_file: str, cfg: dict) -> dict:
    yt_cfg = cfg.get("youtube", {})
    creds = Credentials(
        None,
        refresh_token=env("YOUTUBE_REFRESH_TOKEN"),
        client_id=env("YOUTUBE_CLIENT_ID"),
        client_secret=env("YOUTUBE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    tags = video.get("hashtags") or []
    description = f"{video.get('caption', '')}\n\n" + " ".join(f"#{t}" for t in tags) + " #Shorts"
    body = {
        "snippet": {
            "title": video["title"][:100],
            "description": description[:4900],
            "tags": tags[:15],
            "categoryId": str(yt_cfg.get("category_id", "28")),
        },
        "status": {
            "privacyStatus": yt_cfg.get("privacy", "public"),
            "selfDeclaredMadeForKids": bool(yt_cfg.get("made_for_kids", False)),
            "containsSyntheticMedia": bool(yt_cfg.get("synthetic_media", False)),
        },
    }
    media = MediaFileUpload(local_file, mimetype="video/mp4", resumable=True, chunksize=-1)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    vid = response["id"]
    privacy = response.get("status", {}).get("privacyStatus", "")
    note = ""
    if privacy == "private" and yt_cfg.get("privacy") == "public":
        note = "Uploaded as private (API project not yet audited). Make it public in YouTube Studio."
    return {"ok": True, "id": vid, "url": f"https://youtube.com/shorts/{vid}", "note": note}
