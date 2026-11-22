"""Run ONCE on your own computer to save Instagram and/or Facebook Page logins.

Needs SUPABASE_URL and SUPABASE_SERVICE_KEY set in your terminal.

Instagram (Instagram API with Instagram Login):
  python tools/meta_login.py instagram LONG_LIVED_INSTAGRAM_TOKEN
  (get the token in your Meta app > Instagram > API setup with Instagram login > Generate token)

Facebook Page:
  python tools/meta_login.py facebook APP_ID APP_SECRET SHORT_USER_TOKEN
  (get SHORT_USER_TOKEN from Graph API Explorer with pages_show_list,
   pages_read_engagement and pages_manage_posts permissions)
"""
import os
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from vvapp import db  # noqa: E402

V = "v24.0"


def instagram(token: str):
    me = requests.get(f"https://graph.instagram.com/{V}/me",
                      params={"fields": "user_id,username", "access_token": token}, timeout=30).json()
    if "user_id" not in me:
        sys.exit(f"Instagram token check failed: {me}")
    db.set_token("instagram", {"access_token": token, "user_id": me["user_id"], "refreshed_at": time.time()})
    print(f"Instagram @{me.get('username')} saved.")


def facebook(app_id: str, app_secret: str, short_token: str):
    ll = requests.get(f"https://graph.facebook.com/{V}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret,
        "fb_exchange_token": short_token}, timeout=30).json()
    if "access_token" not in ll:
        sys.exit(f"Token exchange failed: {ll}")
    pages = requests.get(f"https://graph.facebook.com/{V}/me/accounts",
                         params={"access_token": ll["access_token"]}, timeout=30).json().get("data", [])
    if not pages:
        sys.exit("No Facebook Pages found for this account.")
    for i, p in enumerate(pages):
        print(f"[{i}] {p['name']} ({p['id']})")
    choice = int(input("Which page number? ") or 0)
    page = pages[choice]
    db.set_token("facebook", {"page_id": page["id"], "page_access_token": page["access_token"],
                              "page_name": page["name"]})
    print(f"Facebook Page '{page['name']}' saved (page tokens from a long-lived login do not expire).")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "instagram":
        instagram(sys.argv[2])
    elif len(sys.argv) >= 5 and sys.argv[1] == "facebook":
        facebook(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print(__doc__)
