"""TikTok upload (Content Posting API).

mode "inbox": video lands in your TikTok inbox as a draft; you tap the notification, add a
              sound if you like, and post. Works before TikTok audits your app.
mode "direct": posts straight to the profile. Before the audit TikTok forces it to private.
"""
import os
import time

import requests

from .. import db
from ..config import env

API = "https://open.tiktokapis.com/v2"
MAX_SINGLE = 64 * 1024 * 1024
CHUNK = 10 * 1024 * 1024


def _access_token() -> str:
    tok = db.get_token("tiktok")
    if tok.get("expires_at", 0) > time.time() + 300:
        return tok["access_token"]
    r = requests.post(
        f"{API}/oauth/token/",
        data={
            "client_key": env("TIKTOK_CLIENT_KEY"),
            "client_secret": env("TIKTOK_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok token refresh failed: {data}. Run tools/tiktok_login.py again.")
    db.set_token("tiktok", {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", tok["refresh_token"]),
        "expires_at": time.time() + int(data.get("expires_in", 86400)),
        "open_id": data.get("open_id", tok.get("open_id")),
    })
    return data["access_token"]


def post(video: dict, local_file: str, cfg: dict) -> dict:
    tt = cfg.get("tiktok", {})
    mode = tt.get("mode", "inbox")
    token = _access_token()
    size = os.path.getsize(local_file)
    if size <= MAX_SINGLE:
        chunk_size, total_chunks = size, 1
    else:
        chunk_size, total_chunks = CHUNK, size // CHUNK  # last chunk absorbs the remainder

    source_info = {"source": "FILE_UPLOAD", "video_size": size,
                   "chunk_size": chunk_size, "total_chunk_count": total_chunks}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    if mode == "direct":
        tags = " ".join(f"#{t}" for t in video.get("hashtags") or [])
        body = {
            "post_info": {
                "title": f"{video.get('caption', video['title'])} {tags}"[:2200],
                "privacy_level": tt.get("direct_privacy", "SELF_ONLY"),
                "disable_comment": False, "disable_duet": False, "disable_stitch": False,
            },
            "source_info": source_info,
        }
        url = f"{API}/post/publish/video/init/"
    else:
        body = {"source_info": source_info}
        url = f"{API}/post/publish/inbox/video/init/"

    r = requests.post(url, json=body, headers=headers, timeout=60)
    data = r.json()
    if data.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok init failed: {data['error']}")
    upload_url = data["data"]["upload_url"]
    publish_id = data["data"]["publish_id"]

    with open(local_file, "rb") as f:
        for i in range(total_chunks):
            start = i * chunk_size
            end = size - 1 if i == total_chunks - 1 else start + chunk_size - 1
            f.seek(start)
            part = f.read(end - start + 1)
            up = requests.put(
                upload_url,
                data=part,
                headers={"Content-Type": "video/mp4", "Content-Length": str(len(part)),
                         "Content-Range": f"bytes {start}-{end}/{size}"},
                timeout=300,
            )
            if up.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok upload failed ({up.status_code}): {up.text[:300]}")

    note = ("Sent to your TikTok inbox: open TikTok, tap the notification, then post."
            if mode == "inbox" else "Posted (private until TikTok audits the app).")
    return {"ok": True, "id": publish_id, "url": "", "note": note}
