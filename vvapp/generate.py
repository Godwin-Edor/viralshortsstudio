"""Makes new videos and puts them in the approval queue.

Usage:
  python -m vvapp.generate               # makes `videos_per_run` videos (uses all APIs)
  python -m vvapp.generate --count 2
  python -m vvapp.generate --topic "Why the sky is blue"
  python -m vvapp.generate --offline     # test render only: no API keys, no upload
"""
import argparse
import math
import random
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .captions import build_ass
from .config import ROOT, load_config
from .render import color_shot, concat_audio, concat_shots, final_render, make_shot

OUT_DIR = ROOT / "out"


def _next_topic_from_file(cfg: dict, used: list[str]) -> str | None:
    path = ROOT / cfg.get("topics_file", "topics.txt")
    if not path.exists():
        return None
    used_lower = {u.lower().strip() for u in used}
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t and not t.startswith("#") and t.lower() not in used_lower:
            return t
    return None


def _pick_music(cfg: dict) -> str | None:
    d = ROOT / cfg.get("music_dir", "music")
    tracks = list(d.glob("*.mp3")) if d.exists() else []
    return str(random.choice(tracks)) if tracks else None


def _offline_script(topic: str) -> dict:
    return {
        "topic": topic,
        "title": "Offline test video",
        "hook_text": "This metal melts in your hand",
        "scenes": [
            {"text": "This metal melts in the palm of your hand.", "footage": ["metal"]},
            {"text": "It is called gallium, and it melts at about thirty degrees Celsius.", "footage": ["lab"]},
            {"text": "Your body is warmer than that, so it turns into a shiny liquid.", "footage": ["hand"]},
            {"text": "Would you hold it? Tell me in the comments.", "footage": ["question"]},
        ],
        "caption": "Test caption",
        "hashtags": ["science", "chemistry"],
        "fact_check": "Gallium melting point is 29.76 C.",
    }


def _offline_voice(text: str, out_path: str) -> tuple[list[dict], float]:
    tokens = text.split()
    duration = max(1.5, len(tokens) * 0.36)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={duration}",
         "-af", "volume=0.05", out_path],
        check=True,
    )
    step = duration / len(tokens)
    return [{"word": w, "start": i * step, "end": (i + 1) * step} for i, w in enumerate(tokens)], duration


def make_video(cfg: dict, topic: str | None = None, offline: bool = False) -> dict:
    work = Path(tempfile.mkdtemp(prefix="vv_"))
    try:
        # 1) topic + script
        if offline:
            script = _offline_script(topic or "Gallium")
        else:
            from . import db
            from .script_writer import pick_topic, write_and_review
            past = db.recent_topics()
            topic = topic or _next_topic_from_file(cfg, past) or pick_topic(cfg, past)
            print(f"Topic: {topic}")
            script, review = write_and_review(cfg, topic)
            script["topic"] = topic  # keep the exact topic text so topics.txt items are not reused
            script["review"] = review
            if not review.get("approve"):
                # the AI reviewer would not pass it: record why, make nothing, post nothing
                reason = "; ".join(review.get("problems") or []) or "did not pass the AI review"
                db.insert_video({
                    "topic": topic, "title": (script.get("title") or topic)[:95],
                    "caption": script.get("caption", ""), "hashtags": script.get("hashtags", []),
                    "script": script, "platforms": [], "status": "rejected",
                    "results": {"review": {"ok": False, "error": f"AI review rejected it: {reason}"}},
                })
                print(f"Rejected by AI review: {reason}")
                return {"status": "rejected", "topic": topic}

        # 2) voiceover per scene, collect word timings on one timeline
        audio_parts, all_words, scene_lengths = [], [], []
        offset = 0.0
        for i, scene in enumerate(script["scenes"]):
            mp3 = str(work / f"voice_{i:02d}.{'wav' if offline else 'mp3'}")
            if offline:
                words, dur = _offline_voice(scene["text"], mp3)
            else:
                from .voice import synthesize
                words, dur = synthesize(scene["text"], cfg["voice"], cfg.get("voice_rate", "+0%"), mp3)
            for w in words:
                all_words.append({"word": w["word"], "start": w["start"] + offset, "end": w["end"] + offset})
            audio_parts.append(mp3)
            scene_lengths.append(dur)
            offset += dur
        total = offset
        print(f"Narration length: {total:.1f} s")

        # 3) footage: several quick shots per scene; the AI checks every clip fits and is family-friendly
        shots = []
        finder = None
        plan = []  # [(scene_index, seconds, terms, clip)]
        if not offline:
            from .footage import FootageFinder, download
            finder = FootageFinder(fallback_query=cfg["niche"].split()[0])
        per_shot = float(cfg.get("seconds_per_shot", 3.2))
        for i, (scene, length) in enumerate(zip(script["scenes"], scene_lengths)):
            count = max(1, math.ceil(length / per_shot))
            each = length / count
            for k in range(count):
                terms = scene.get("footage") or []
                terms = terms[k % len(terms):] + terms[:k % len(terms)] if terms else []
                clip = finder.find(terms, each) if finder else None
                plan.append([i, each, terms, clip])

        if finder and cfg.get("check_footage", True):
            from .script_writer import check_footage
            for round_ in range(2):  # check, swap the bad clips, check the swaps once more
                idx = [j for j, p in enumerate(plan) if p[3] and p[3].get("thumb") and not p[3].get("ok")]
                if not idx:
                    break
                verdict = check_footage(cfg, [{"thumb": plan[j][3]["thumb"],
                                               "text": script["scenes"][plan[j][0]]["text"]} for j in idx])
                bad = 0
                for j, v in zip(idx, verdict):
                    if v["fits"] and v["safe"]:
                        plan[j][3]["ok"] = True
                    else:
                        bad += 1
                        if not v["safe"] or round_ == 1:
                            plan[j][3] = None  # unsafe, or still off-topic after a swap: use the backdrop
                        if round_ == 0:
                            plan[j][3] = finder.find(plan[j][2][1:] + plan[j][2][:1], plan[j][1]) or plan[j][3]
                print(f"Footage check round {round_ + 1}: {bad} of {len(idx)} clips replaced")

        for n, (i, each, terms, clip) in enumerate(plan):
            out = str(work / f"shot_{n:03d}.mp4")
            if clip:
                raw = download(clip["link"], str(work / f"raw_{n:03d}.mp4"))
                make_shot(raw, each, out)
            elif offline:
                subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                     f"testsrc2=s=1280x720:d={each + 1:.2f}:r=30", "-c:v", "libx264",
                     str(work / f"raw_{n:03d}.mp4")], check=True)
                make_shot(str(work / f"raw_{n:03d}.mp4"), each, out)
            else:
                color_shot(each, out)
            shots.append(out)

        # 4) assemble
        silent = concat_shots(shots, str(work / "silent.mp4"))
        audio = concat_audio(audio_parts, str(work / "audio.wav"), _pick_music(cfg), float(cfg.get("music_volume", 0.1)))
        ass = build_ass(all_words, total, cfg, str(work / "captions.ass"), hook_text=script.get("hook_text", ""))
        vid_id = str(uuid.uuid4())
        OUT_DIR.mkdir(exist_ok=True)
        final = final_render(silent, audio, ass, str(OUT_DIR / f"{vid_id}.mp4"),
                             fonts_dir=str(ROOT / "fonts") if (ROOT / "fonts").exists() else None,
                             duration=total, bar_color=cfg.get("captions", {}).get("highlight_color", "00E5FF"))
        print(f"Rendered: {final}")

        if offline:
            return {"id": vid_id, "file": final, **script}

        # 5) upload; with auto_post on, it goes straight to "approved" and post.py publishes it
        from . import db
        dest = f"{datetime.now(timezone.utc):%Y-%m-%d}/{vid_id}.mp4"
        url = db.upload_file(final, dest)
        row = db.insert_video({
            "id": vid_id,
            "topic": script["topic"],
            "title": script["title"][:95],
            "caption": script.get("caption", ""),
            "hashtags": script.get("hashtags", []),
            "script": script,
            "duration_s": round(total, 1),
            "video_path": dest,
            "video_url": url,
            "platforms": cfg.get("auto_platforms" if cfg.get("auto_post") else "platforms_default", []),
            "status": "approved" if cfg.get("auto_post") else "pending",
            "results": {"review": {"ok": True, "note": f"AI review passed (hook {script['review'].get('hook_score')}/10)"}},
        })
        Path(final).unlink(missing_ok=True)
        print(f"{'Ready to post' if cfg.get('auto_post') else 'Queued for approval'}: {row['id']} - {row['title']}")
        return row
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=None)
    ap.add_argument("--topic", type=str, default=None)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    count = args.count or int(cfg.get("videos_per_run", 1))
    failures = 0
    for i in range(count):
        try:
            make_video(cfg, topic=args.topic if i == 0 else None, offline=args.offline)
        except Exception as e:  # keep going with the next video
            failures += 1
            print(f"Video {i + 1} failed: {e}")
    if failures == count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
