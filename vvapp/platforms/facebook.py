"""Facebook Page Reels (Reels Publishing API)."""
import requests

from .. import db


def post(video: dict, local_file: str, cfg: dict) -> dict:
    v = cfg.get("meta_graph_version", "v24.0")
    tok = db.get_token("facebook")
    page_id, at = tok["page_id"], tok["page_access_token"]
    tags = " ".join(f"#{t}" for t in video.get("hashtags") or [])
    description = f"{video.get('caption', '')}\n\n{tags}"

    start = requests.post(f"https://graph.facebook.com/{v}/{page_id}/video_reels",
                          json={"upload_phase": "start", "access_token": at}, timeout=60).json()
    if "video_id" not in start:
        raise RuntimeError(f"Facebook start failed: {start}")
    video_id = start["video_id"]

    up = requests.post(f"https://rupload.facebook.com/video-upload/{v}/{video_id}",
                       headers={"Authorization": f"OAuth {at}", "file_url": video["video_url"]},
                       timeout=300).json()
    if not up.get("success"):
        raise RuntimeError(f"Facebook upload failed: {up}")

    fin = requests.post(f"https://graph.facebook.com/{v}/{page_id}/video_reels", params={
        "upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED",
        "description": description, "access_token": at,
    }, timeout=60).json()
    if not fin.get("success"):
        raise RuntimeError(f"Facebook publish failed: {fin}")
    return {"ok": True, "id": video_id, "url": f"https://www.facebook.com/reel/{video_id}", "note": ""}
