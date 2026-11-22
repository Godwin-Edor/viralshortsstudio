"""Run ONCE on your own computer to connect your TikTok account.

Needs these environment variables set in your terminal first:
  SUPABASE_URL, SUPABASE_SERVICE_KEY, TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET
and your dashboard's oauth page added as a Redirect URI in the TikTok developer app, e.g.
  https://viralshortsstudio.netlify.app/oauth.html

  python tools/tiktok_login.py https://viralshortsstudio.netlify.app/oauth.html
"""
import os
import secrets
import sys
import time
import urllib.parse
import webbrowser

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from vvapp import db  # noqa: E402

SCOPES = "user.info.basic,video.upload"   # add ",video.publish" after TikTok approves Direct Post


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    redirect = sys.argv[1]
    key, secret = os.environ["TIKTOK_CLIENT_KEY"], os.environ["TIKTOK_CLIENT_SECRET"]
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": key, "scope": SCOPES, "response_type": "code",
        "redirect_uri": redirect, "state": secrets.token_urlsafe(12),
    })
    print("Opening TikTok login... if it does not open, visit:\n" + url)
    webbrowser.open(url)
    code = urllib.parse.unquote(input("\nPaste the code shown on the page: ").strip())
    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
        "client_key": key, "client_secret": secret, "code": code,
        "grant_type": "authorization_code", "redirect_uri": redirect,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30).json()
    if "access_token" not in r:
        sys.exit(f"TikTok login failed: {r}")
    db.set_token("tiktok", {
        "access_token": r["access_token"], "refresh_token": r["refresh_token"],
        "expires_at": time.time() + int(r.get("expires_in", 86400)), "open_id": r.get("open_id"),
    })
    print("TikTok connected and saved.")


if __name__ == "__main__":
    main()
