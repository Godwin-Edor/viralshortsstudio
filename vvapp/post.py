"""Posts every APPROVED video to the platforms ticked on the dashboard.

Usage: python -m vvapp.post
"""
import importlib
import tempfile
import traceback
from pathlib import Path

import requests

from . import db
from .config import load_config

MODULES = {
    "youtube": "vvapp.platforms.youtube",
    "tiktok": "vvapp.platforms.tiktok",
    "instagram": "vvapp.platforms.instagram",
    "facebook": "vvapp.platforms.facebook",
    "x": "vvapp.platforms.x_twitter",
}


def _download(url: str, path: str) -> str:
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return path


def post_video(video: dict, cfg: dict) -> None:
    results = dict(video.get("results") or {})
    db.update_video(video["id"], {"status": "posting"})
    with tempfile.TemporaryDirectory() as tmp:
        local = _download(video["video_url"], str(Path(tmp) / "video.mp4"))
        for platform in video.get("platforms") or []:
            if results.get(platform, {}).get("ok"):
                continue  # already posted on an earlier run
            try:
                mod = importlib.import_module(MODULES[platform])
                results[platform] = mod.post(video, local, cfg)
                print(f"  {platform}: OK {results[platform].get('url', '')}")
            except Exception as e:
                traceback.print_exc()
                results[platform] = {"ok": False, "error": str(e)[:500]}
                print(f"  {platform}: FAILED - {e}")

    all_ok = all(results.get(p, {}).get("ok") for p in video.get("platforms") or [])
    fields = {"results": results, "status": "posted" if all_ok else "failed"}
    if all_ok and cfg.get("cleanup_after_post", True) and video.get("video_path"):
        try:
            db.delete_file(video["video_path"])
            fields["video_url"] = None
        except Exception as e:
            print(f"  cleanup skipped: {e}")
    db.update_video(video["id"], fields)


def main():
    cfg = load_config()
    videos = db.list_videos("approved")
    print(f"{len(videos)} approved video(s) to post")
    for v in videos:
        print(f"Posting: {v['title']}")
        post_video(v, cfg)


if __name__ == "__main__":
    main()
