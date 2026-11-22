"""Finds and downloads free stock clips.

Uses Pixabay (PIXABAY_API_KEY). Pexels (PEXELS_API_KEY) still works if you ever get a key;
when both keys are set, Pixabay is tried first.
Landscape clips are fine: render.py crops every clip to vertical 1080x1920.
"""
import os
import random

import requests


def _pixabay(query: str) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    r = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": key, "q": query[:100], "per_page": 30, "safesearch": "true"},
        timeout=30,
    )
    if r.status_code >= 400:
        return []
    out = []
    for hit in r.json().get("hits", []):
        files = [f for f in (hit.get("videos") or {}).values() if f.get("url") and f.get("height")]
        # prefer portrait, then the size closest to 1920 px tall (but at least 720)
        good = [f for f in files if f["height"] >= 720] or files
        if not good:
            continue
        good.sort(key=lambda f: (f["width"] > f["height"], abs(max(f["height"], f["width"]) - 1920)))
        out.append({"id": f"pb{hit['id']}", "duration": hit.get("duration", 0), "link": good[0]["url"]})
    return out


def _pexels(query: str) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    r = requests.get(
        "https://api.pexels.com/videos/search",
        params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 15},
        headers={"Authorization": key},
        timeout=30,
    )
    if r.status_code >= 400:
        return []
    out = []
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", [])
                 if f.get("height") and f.get("width") and f["height"] >= 720 and f.get("file_type") == "video/mp4"]
        if files:
            files.sort(key=lambda f: (f["width"] > f["height"], abs(f["height"] - 1920)))
            out.append({"id": f"px{v['id']}", "duration": v.get("duration", 0), "link": files[0]["link"]})
    return out


def _search(query: str) -> list[dict]:
    return _pixabay(query) or _pexels(query)


class FootageFinder:
    def __init__(self, fallback_query: str):
        if not (os.environ.get("PIXABAY_API_KEY") or os.environ.get("PEXELS_API_KEY")):
            raise RuntimeError("Missing secret PIXABAY_API_KEY. Add it in GitHub > Settings > Secrets > Actions.")
        self.used_ids: set[str] = set()
        self.fallback_query = fallback_query
        self.cache: dict[str, list[dict]] = {}

    def find(self, queries: list[str], min_seconds: float) -> str | None:
        """Returns a download URL for a clip not yet used in this video."""
        for q in list(queries) + [self.fallback_query, "science", "abstract background"]:
            if q not in self.cache:
                self.cache[q] = _search(q)
            candidates = [v for v in self.cache[q] if v["id"] not in self.used_ids]
            long_enough = [v for v in candidates if v.get("duration", 0) >= min_seconds]
            pool = long_enough or candidates
            if pool:
                v = random.choice(pool[:8])
                self.used_ids.add(v["id"])
                return v["link"]
        return None


def download(url: str, out_path: str) -> str:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return out_path
