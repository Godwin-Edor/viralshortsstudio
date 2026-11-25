"""AI comedy skits: one photorealistic Veo clip with its own voices and sound (like the viral
"baby on the phone" reels). Everything shown is AI-generated and fictional, and labelled as such.

Needs Veo on the Gemini API key (paid tier, about $0.05 per second with Veo 3.1 Lite at 720p).
"""
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile

import requests

from . import db
from .config import env
from .script_writer import SAFETY_RULES, _gemini

BASE = "https://generativelanguage.googleapis.com/v1beta"


class VeoUnavailable(RuntimeError):
    """Veo can't be used with this key (no billing / no access): the caller falls back."""


SKIT_PROMPT = """You create ONE viral, family-friendly comedy short for the series "{series}": {niche}
Style: {format}
It becomes a single {seconds}-second photorealistic AI video WITH its own sound (voices, lip-sync,
ambience), filmed vertically like a real phone video. Think of the most-shared reels: one instantly
readable situation, a character with BIG facial expressions, a relatable joke, and a funny final
beat that makes people rewatch and tag a friend.

Rules:
- One continuous shot, one location, one or two characters. Everything fictional: no real or
  famous people, no brands/logos, no text on screen.
- Dialogue: at most {words} words in total, short punchy lines, in quotes, said by a named character
  (e.g. The baby says: "..."). Toddler babble mixed with a few clear adult words is great.
- Wholesome and kind: nobody is mocked, hurt, scared or in danger; babies and pets are always safe
  and supervised; no food or objects that are hazardous for babies.
{safety}
Do NOT repeat these past ideas:
{past}

Return ONLY JSON:
{{
  "topic": "short name of the idea",
  "title": "funny title under 60 characters, no hashtags",
  "video_prompt": "a detailed prompt for the video model: who, where, camera (handheld vertical phone video,
     natural light), what happens second by second, exact dialogue lines in quotes with who says them,
     facial expressions, background sounds, ending beat",
  "caption": "1 short funny caption ending with a question or 'tag someone who...'",
  "hashtags": ["5 to 7 hashtags without #, include shorts and funny"],
  "fun_score": number 1-10 (be harsh),
  "safe": true or false
}}"""


def write_skit(cfg: dict, cat: dict, past: list[str]) -> dict:
    seconds = int(cfg.get("veo", {}).get("seconds", 8))
    best = None
    for _ in range(2):  # keep the funnier of two ideas
        data = _gemini(SKIT_PROMPT.format(series=cat["series"], niche=cat["niche"], format=cat.get("format", ""),
                                          seconds=seconds, words=int(seconds * 2.2), safety=SAFETY_RULES,
                                          past="\n".join(f"- {p}" for p in past[:150]) or "- (none)"),
                       cfg["gemini_model"], temperature=1.1, label="Skit")
        if not data.get("safe", True):
            continue
        if best is None or float(data.get("fun_score") or 0) > float(best.get("fun_score") or 0):
            best = data
        if float(best.get("fun_score") or 0) >= 8:
            break
    if not best:
        raise RuntimeError("No safe skit idea")
    print(f"Skit: {best['topic']} (fun {best.get('fun_score')})")
    return best


def veo_clip(cfg: dict, prompt: str, out_path: str) -> str:
    vcfg = cfg.get("veo", {})
    key = env("GEMINI_API_KEY")
    h = {"x-goog-api-key": key, "Content-Type": "application/json"}
    last = ""
    for model in vcfg.get("models", ["veo-3.1-lite-generate-preview", "veo-3.1-fast-generate-preview"]):
        params = {"aspectRatio": "9:16", "resolution": vcfg.get("resolution", "720p"),
                  "durationSeconds": int(vcfg.get("seconds", 8)), "personGeneration": "allow_all"}
        r = requests.post(f"{BASE}/models/{model}:predictLongRunning", headers=h, timeout=60,
                          json={"instances": [{"prompt": prompt}], "parameters": params})
        if r.status_code == 400 and "personGeneration" in r.text:
            params.pop("personGeneration")
            r = requests.post(f"{BASE}/models/{model}:predictLongRunning", headers=h, timeout=60,
                              json={"instances": [{"prompt": prompt}], "parameters": params})
        if r.status_code != 200:
            last = f"{model}: {r.status_code} {r.text[:300]}"
            print(f"Veo start failed - {last}")
            continue
        op = r.json()["name"]
        deadline = time.time() + 600
        while time.time() < deadline:
            time.sleep(10)
            s = requests.get(f"{BASE}/{op}", headers=h, timeout=60).json()
            if s.get("done"):
                if "error" in s:
                    last = f"{model}: {s['error']}"
                    break
                resp = s.get("response", {}).get("generateVideoResponse", {})
                samples = resp.get("generatedSamples") or []
                if not samples:  # blocked by Google's safety filter
                    last = f"{model}: no video returned ({json.dumps(resp)[:300]})"
                    break
                v = requests.get(samples[0]["video"]["uri"], headers={"x-goog-api-key": key},
                                 timeout=300, allow_redirects=True)
                v.raise_for_status()
                Path(out_path).write_bytes(v.content)
                print(f"Veo model: {model}")
                return out_path
        else:
            last = f"{model}: timed out"
    raise VeoUnavailable(last)  # no access, blocked or timed out: the caller makes a normal video instead


def make_skit(cfg: dict, cat: dict) -> dict:
    from .generate import publish_time, run_ffmpeg_vertical
    past = db.recent_topics()
    idea = write_skit(cfg, cat, past)
    work = Path(tempfile.mkdtemp(prefix="skit_"))
    try:
        raw = veo_clip(cfg, idea["video_prompt"], str(work / "veo.mp4"))
        final = run_ffmpeg_vertical(raw, str(work / "final.mp4"))
        vid_id = str(uuid.uuid4())
        dest = f"{datetime.now(timezone.utc):%Y-%m-%d}/{vid_id}.mp4"
        url = db.upload_file(final, dest)
        tags = [t.lstrip("#") for t in idea.get("hashtags", [])]
        for must in ("shorts", cat.get("hashtag", "funny")):
            if must not in [t.lower() for t in tags]:
                tags.append(must)
        auto = bool(cfg.get("auto_post"))
        script = {"topic": idea["topic"], "title": idea["title"], "scenes": [{"text": idea["video_prompt"]}],
                  "category": cat["key"], "series": cat["series"], "youtube_category": cat.get("youtube_category"),
                  "ai_people": True, "ai_video": True, "fun_score": idea.get("fun_score"),
                  "publish_at": publish_time(cat) if auto else None}
        row = db.insert_video({
            "id": vid_id, "topic": idea["topic"], "title": idea["title"][:95],
            "caption": idea.get("caption", ""), "hashtags": tags, "script": script,
            "duration_s": float(cfg.get("veo", {}).get("seconds", 8)), "video_path": dest, "video_url": url,
            "platforms": cfg.get("auto_platforms" if auto else "platforms_default", []),
            "status": "posting" if auto else "pending",
            "results": {"review": {"ok": True, "note": f"AI comedy clip (fun {idea.get('fun_score')}/10)"}},
        })
        print(f"Posting skit: {row['id']} - {row['title']}")
        if auto:
            from .post import post_video
            post_video(row, cfg, local_file=final)
        return row
    finally:
        shutil.rmtree(work, ignore_errors=True)
