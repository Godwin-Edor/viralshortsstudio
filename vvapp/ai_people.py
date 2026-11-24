"""Photorealistic AI-generated people (fictional, never real or named individuals).

Uses Pollinations' free image API (no key needed; set POLLINATIONS_API_KEY for higher limits
and no watermark). Each image is turned into a moving shot with a slow zoom.
"""
import os
import random
import subprocess
import time
import urllib.parse

import requests

from .render import FPS, H, W, _run

STYLE = ("photorealistic vertical photo, natural light, sharp focus, realistic skin texture, candid, "
         "documentary style, fully clothed, family friendly, adult, fictional ordinary person, "
         "not a celebrity, no text, no logo, no watermark")
_last_call = [0.0]


def generate(prompt: str, out_path: str) -> str | None:
    """Downloads one 1080x1920 AI image for `prompt`. Returns the file path, or None on failure."""
    key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    full = f"{prompt}, {STYLE}"
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(full)
    params = {"width": W, "height": H, "model": "flux", "nologo": "true", "safe": "true",
              "private": "true", "seed": random.randint(1, 10**9)}
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    for attempt in range(3):
        wait = (5 if key else 16) - (time.time() - _last_call[0])  # free tier: 1 request / 15 s
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        try:
            r = requests.get(url, params=params, headers=headers, timeout=120)
        except requests.RequestException as e:
            print(f"  AI person image failed: {e}")
            continue
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            with open(out_path, "wb") as f:
                f.write(r.content)
            return out_path
        print(f"  AI person image: HTTP {r.status_code}")
        time.sleep(10 * (attempt + 1))
    return None


def image_shot(img: str, seconds: float, out_path: str) -> str:
    """Still image -> vertical clip with a slow push-in and slight drift (looks like a camera move)."""
    frames = max(1, int(seconds * FPS) + 2)
    vf = (
        f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},setsar=1,"
        f"zoompan=z='1+0.10*on/{frames}':x='iw/2-(iw/zoom/2)+on*0.4':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={W}x{H}:fps={FPS},eq=contrast=1.04:saturation=1.08"
    )
    _run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-t", f"{seconds:.3f}", "-vf", vf, "-an",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-r", str(FPS),
          out_path])
    return out_path


if __name__ == "__main__":  # quick local test: python -m vvapp.ai_people
    p = generate("a 1930s department store shopper in a hat smiling in amazement", "test_person.jpg")
    print(p)
    if p:
        image_shot(p, 2.6, "test_person.mp4")
        subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "test_person.mp4"])
