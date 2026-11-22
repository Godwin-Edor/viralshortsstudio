"""X (Twitter) video post. X has no free API tier: each post costs a small amount of credit."""
import os
import time

import requests
from requests_oauthlib import OAuth1

from ..config import env

API = "https://api.x.com/2"
CHUNK = 4 * 1024 * 1024


def _auth() -> OAuth1:
    return OAuth1(env("X_API_KEY"), env("X_API_SECRET"), env("X_ACCESS_TOKEN"), env("X_ACCESS_SECRET"))


def post(video: dict, local_file: str, cfg: dict) -> dict:
    if not cfg.get("x", {}).get("enabled", False):
        raise RuntimeError("X is turned off in config.yaml (x: enabled: false).")
    auth = _auth()
    size = os.path.getsize(local_file)
    init = requests.post(f"{API}/media/upload/initialize", auth=auth, json={
        "media_type": "video/mp4", "total_bytes": size, "media_category": "tweet_video"}, timeout=60)
    if init.status_code >= 400:
        raise RuntimeError(f"X init failed: {init.text[:300]}")
    media_id = init.json()["data"]["id"]

    with open(local_file, "rb") as f:
        i = 0
        while chunk := f.read(CHUNK):
            r = requests.post(f"{API}/media/upload/{media_id}/append", auth=auth,
                              files={"media": ("chunk", chunk, "application/octet-stream")},
                              data={"segment_index": str(i)}, timeout=300)
            if r.status_code >= 400:
                raise RuntimeError(f"X append failed: {r.text[:300]}")
            i += 1

    fin = requests.post(f"{API}/media/upload/{media_id}/finalize", auth=auth, timeout=60)
    if fin.status_code >= 400:
        raise RuntimeError(f"X finalize failed: {fin.text[:300]}")
    info = fin.json().get("data", {}).get("processing_info")
    while info and info.get("state") in ("pending", "in_progress"):
        time.sleep(info.get("check_after_secs", 5))
        st = requests.get(f"{API}/media/upload", auth=auth,
                          params={"media_id": media_id, "command": "STATUS"}, timeout=30).json()
        info = st.get("data", {}).get("processing_info")
    if info and info.get("state") == "failed":
        raise RuntimeError(f"X processing failed: {info}")

    tags = " ".join(f"#{t}" for t in (video.get("hashtags") or [])[:3])
    text = f"{video['title']} {tags}"[:280]
    tw = requests.post(f"{API}/tweets", auth=auth, json={"text": text, "media": {"media_ids": [media_id]}},
                       timeout=60)
    if tw.status_code >= 400:
        raise RuntimeError(f"X post failed: {tw.text[:300]}")
    tid = tw.json()["data"]["id"]
    return {"ok": True, "id": tid, "url": f"https://x.com/i/status/{tid}", "note": ""}
