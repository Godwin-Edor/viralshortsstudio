"""Finishes the TikTok login on GitHub's servers.

Started by the "Connect TikTok" workflow (from the dashboard's Connect TikTok button) with the
code TikTok sent back to oauth.html. Exchanges it for tokens and saves them in Supabase
(app_tokens, name "tiktok"), where vvapp/platforms/tiktok.py reads and refreshes them.
"""
import time
import urllib.parse

import requests

from . import db
from .config import env

REDIRECT = "https://viralshortsstudio.netlify.app/oauth.html"


def main():
    code = urllib.parse.unquote(env("TIKTOK_CODE").strip())
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
        "client_key": env("TIKTOK_CLIENT_KEY"),
        "client_secret": env("TIKTOK_CLIENT_SECRET"),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30).json()
    if "access_token" not in r:
        raise SystemExit(f"TikTok login failed: {r.get('error')} {r.get('error_description', '')}")
    db.set_token("tiktok", {
        "access_token": r["access_token"],
        "refresh_token": r["refresh_token"],
        "expires_at": time.time() + int(r.get("expires_in", 86400)),
        "open_id": r.get("open_id"),
    })
    who = requests.get("https://open.tiktokapis.com/v2/user/info/", params={"fields": "display_name"},
                       headers={"Authorization": f"Bearer {r['access_token']}"}, timeout=30)
    name = (who.json().get("data", {}).get("user", {}) or {}).get("display_name", "") if who.ok else ""
    print(f"TikTok connected and saved. Account: {name or '(name not shown)'}")


if __name__ == "__main__":
    main()
