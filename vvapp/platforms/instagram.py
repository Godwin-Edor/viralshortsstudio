"""Instagram Reels (Instagram API with Instagram Login). Needs a Professional (Business/Creator) account."""
import time

import requests

from .. import db

GRAPH = "https://graph.instagram.com"


def _token(cfg: dict) -> dict:
    tok = db.get_token("instagram")
    # long-lived tokens last 60 days; refresh every ~20 days
    if time.time() - tok.get("refreshed_at", 0) > 20 * 86400:
        r = requests.get(f"{GRAPH}/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": tok["access_token"]},
                         timeout=30)
        data = r.json()
        if "access_token" in data:
            tok = {**tok, "access_token": data["access_token"], "refreshed_at": time.time()}
            db.set_token("instagram", tok)
    return tok


def post(video: dict, local_file: str, cfg: dict) -> dict:
    v = cfg.get("meta_graph_version", "v24.0")
    tok = _token(cfg)
    uid, at = tok["user_id"], tok["access_token"]
    tags = " ".join(f"#{t}" for t in video.get("hashtags") or [])
    caption = f"{video.get('caption', '')}\n\n{tags}"[:2200]

    r = requests.post(f"{GRAPH}/{v}/{uid}/media", data={
        "media_type": "REELS", "video_url": video["video_url"], "caption": caption,
        "share_to_feed": "true", "access_token": at,
    }, timeout=60)
    data = r.json()
    if "id" not in data:
        raise RuntimeError(f"Instagram container failed: {data}")
    container = data["id"]

    for _ in range(60):  # wait up to ~10 min for Instagram to process the video
        s = requests.get(f"{GRAPH}/{v}/{container}",
                         params={"fields": "status_code,status", "access_token": at}, timeout=30).json()
        code = s.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing failed: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timed out.")

    pub = requests.post(f"{GRAPH}/{v}/{uid}/media_publish",
                        data={"creation_id": container, "access_token": at}, timeout=60).json()
    if "id" not in pub:
        raise RuntimeError(f"Instagram publish failed: {pub}")
    link = requests.get(f"{GRAPH}/{v}/{pub['id']}",
                        params={"fields": "permalink", "access_token": at}, timeout=30).json()
    return {"ok": True, "id": pub["id"], "url": link.get("permalink", ""), "note": ""}
