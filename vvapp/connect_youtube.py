"""Finishes the YouTube login on GitHub's servers.

Started by the "Connect YouTube" workflow with the code from the browser address bar
(http://localhost/?code=...). Exchanges it for a long-lived refresh token and saves it
in Supabase (app_tokens, name "youtube"), where vvapp/platforms/youtube.py reads it.
"""
import urllib.parse

import requests

from . import db
from .config import env


def main():
    raw = env("YOUTUBE_CODE").strip()
    if raw.startswith("http"):
        raw = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get("code", [""])[0]
    code = urllib.parse.unquote(raw)
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": env("YOUTUBE_CLIENT_ID"),
        "client_secret": env("YOUTUBE_CLIENT_SECRET"),
        "redirect_uri": "http://localhost",
        "grant_type": "authorization_code",
    }, timeout=30).json()
    if "refresh_token" not in r:
        raise SystemExit(f"YouTube login failed: {r.get('error')} {r.get('error_description', '')}")
    db.set_token("youtube", {"refresh_token": r["refresh_token"]})
    # quick check: which channel is connected
    ch = requests.get("https://www.googleapis.com/youtube/v3/channels",
                      params={"part": "snippet", "mine": "true"},
                      headers={"Authorization": f"Bearer {r['access_token']}"}, timeout=30)
    name = ""
    if ch.ok and ch.json().get("items"):
        name = ch.json()["items"][0]["snippet"]["title"]
    print(f"YouTube connected and saved. Channel: {name or '(upload-only permission, name not shown)'}")


if __name__ == "__main__":
    main()
