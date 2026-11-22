"""Run ONCE on your own computer to get the YouTube refresh token.

  python tools/youtube_login.py CLIENT_ID CLIENT_SECRET

A browser opens; log in with the Google account that owns your YouTube channel and allow access.
The script prints YOUTUBE_REFRESH_TOKEN. Paste it into GitHub > Settings > Secrets > Actions.
"""
import http.server
import secrets
import sys
import urllib.parse
import webbrowser

import requests

PORT = 8765
REDIRECT = f"http://127.0.0.1:{PORT}/"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    client_id, client_secret = sys.argv[1], sys.argv[2]
    state = secrets.token_urlsafe(16)
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
    })
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Done. You can close this tab and go back to the terminal.</h2>")

        def log_message(self, *a):
            pass

    print("Opening your browser... if it does not open, visit:\n" + url)
    webbrowser.open(url)
    with http.server.HTTPServer(("127.0.0.1", PORT), Handler) as srv:
        while "code" not in result and "error" not in result:
            srv.handle_request()
    if result.get("state") != state or "code" not in result:
        sys.exit(f"Login failed: {result}")
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "code": result["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code",
    }, timeout=30).json()
    if "refresh_token" not in r:
        sys.exit(f"No refresh token returned: {r}")
    print("\nYOUTUBE_REFRESH_TOKEN =", r["refresh_token"])


if __name__ == "__main__":
    main()
