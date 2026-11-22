"""Tiny Supabase client (database + storage) using plain REST calls."""
import mimetypes
from datetime import datetime, timezone

import requests

from .config import env

BUCKET = "videos"


def _base() -> str:
    return env("SUPABASE_URL").rstrip("/")


def _headers(extra: dict | None = None) -> dict:
    key = env("SUPABASE_SERVICE_KEY")
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    if extra:
        h.update(extra)
    return h


def _check(r: requests.Response) -> requests.Response:
    if r.status_code >= 400:
        raise RuntimeError(f"Supabase error {r.status_code}: {r.text[:500]}")
    return r


# ---------------- videos table ----------------

def insert_video(row: dict) -> dict:
    r = requests.post(
        f"{_base()}/rest/v1/videos",
        json=row,
        headers=_headers({"Prefer": "return=representation"}),
        timeout=30,
    )
    return _check(r).json()[0]


def list_videos(status: str) -> list[dict]:
    r = requests.get(
        f"{_base()}/rest/v1/videos",
        params={"status": f"eq.{status}", "order": "created_at.asc"},
        headers=_headers(),
        timeout=30,
    )
    return _check(r).json()


def update_video(video_id: str, fields: dict) -> None:
    fields = dict(fields, updated_at=datetime.now(timezone.utc).isoformat())
    r = requests.patch(
        f"{_base()}/rest/v1/videos",
        params={"id": f"eq.{video_id}"},
        json=fields,
        headers=_headers({"Prefer": "return=minimal"}),
        timeout=30,
    )
    _check(r)


def recent_topics(limit: int = 200) -> list[str]:
    r = requests.get(
        f"{_base()}/rest/v1/videos",
        params={"select": "topic", "order": "created_at.desc", "limit": str(limit)},
        headers=_headers(),
        timeout=30,
    )
    return [row["topic"] for row in _check(r).json() if row.get("topic")]


# ---------------- storage ----------------

def upload_file(local_path: str, dest: str) -> str:
    ctype = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
    with open(local_path, "rb") as f:
        r = requests.post(
            f"{_base()}/storage/v1/object/{BUCKET}/{dest}",
            data=f,
            headers=_headers({"Content-Type": ctype, "x-upsert": "true"}),
            timeout=600,
        )
    _check(r)
    return public_url(dest)


def public_url(dest: str) -> str:
    return f"{_base()}/storage/v1/object/public/{BUCKET}/{dest}"


def delete_file(dest: str) -> None:
    r = requests.delete(
        f"{_base()}/storage/v1/object/{BUCKET}",
        json={"prefixes": [dest]},
        headers=_headers(),
        timeout=60,
    )
    _check(r)


# ---------------- tokens (platform logins) ----------------

def get_token(name: str) -> dict:
    r = requests.get(
        f"{_base()}/rest/v1/app_tokens",
        params={"name": f"eq.{name}"},
        headers=_headers(),
        timeout=30,
    )
    rows = _check(r).json()
    if not rows:
        raise RuntimeError(
            f"No saved login for '{name}'. Run the matching tool in tools/ first (see README)."
        )
    return rows[0]["data"]


def set_token(name: str, data: dict) -> None:
    r = requests.post(
        f"{_base()}/rest/v1/app_tokens",
        json={"name": name, "data": data, "updated_at": datetime.now(timezone.utc).isoformat()},
        headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        timeout=30,
    )
    _check(r)
