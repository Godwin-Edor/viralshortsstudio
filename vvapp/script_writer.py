"""Writes, reviews and checks video scripts with the free Gemini API."""
import base64
import json
import re
import time

import requests

from .config import env

SAFETY_RULES = """FAMILY-FRIENDLY RULES (the audience includes people under 18 - all must hold):
- No violence, injury, gore, death, weapons, horror or scary/disturbing imagery.
- No dangerous stunts or experiments a viewer could copy. Never give steps, amounts or
  instructions for anything hazardous (fire, explosives, toxic or reactive chemicals, electricity).
  If a hazardous thing is mentioned, keep it descriptive and say it is done by professionals.
- No drugs, alcohol, smoking, vaping, gambling, romance or sexual content.
- No medical, diet or health advice; no politics, religion or other divisive topics.
- No insults, stereotypes, swearing, brand promotion, or fear-mongering.
- Kind, curious, positive tone."""

PROMPT = """You write scripts for faceless educational short videos (YouTube Shorts, TikTok, Reels)
that people watch to the end, comment on and follow the channel for.

Series: "{series}" - {niche}
Audience: {audience}
Language: {language}
Video topic: {topic}
Target length: about {seconds} seconds of narration (about {words} words in total).

WHAT MAKES PEOPLE WATCH TO THE END:
1. Scene 1 = HOOK, max 10 words, spoken in the first 2 seconds. Use ONE of: a shocking
   true claim, a "you've been doing X wrong", a counter-intuitive question, or a "this
   shouldn't be possible" statement. Never start with "Did you know", greetings or the channel name.
2. Open a curiosity loop in the hook and do NOT fully close it until the last 2 scenes.
3. Every scene adds a NEW surprising detail. Use "but here's the weird part", "and it gets
   stranger" style turns around the middle to re-hook viewers.
4. Concrete, vivid, visual language; compare numbers to everyday things.
   Short spoken sentences (max 14 words), like an excited friend explaining.
5. Be accurate (facts, history, science). Only state dates, places and names you are certain of;
   when unsure, say "in the early 1930s" or "in America" instead of guessing. Do not invent numbers, dates, names or quotes. If unsure, leave it out.
6. Last scene: the satisfying payoff, then ONE short line that turns viewers into followers:
   "Follow for {series} every morning." (you may shorten the series name naturally).
7. LOOP: write the final payoff so it flows naturally back into the hook, so when the video
   replays from the start it feels like one continuous thought (viewers rewatch without noticing).
8. 7 to 10 scenes, 1-2 sentences each.
9. For each scene give 3 stock-footage search terms: simple, concrete, filmable things that
   match what the narration says at that moment (1-3 English words, e.g. "folding paper",
   "ice cubes", "lab beaker", "galaxy"). The first term must be the most literal match.
10. AI PEOPLE: in up to {ai_people} scenes where a person on screen would make it more gripping
   (a shopper reacting, a scientist at work, someone yawning), add "person": a short visual
   description of an ORDINARY, FICTIONAL ADULT doing that action in that setting/era, e.g.
   "a 1930s shopper in a hat staring in amazement". NEVER a real, famous or named person
   (no historical figures, celebrities, inventors), never a child; fully clothed, everyday, kind.
   Leave "person" out of all other scenes.

{safety}

Return ONLY valid JSON:
{{
  "topic": "short topic name",
  "hook_text": "3 to 6 word on-screen headline shown at the start (ALL CAPS friendly)",
  "title": "curiosity title under 70 characters, no hashtags, no clickbait lies",
  "scenes": [{{"text": "narration", "footage": ["term 1", "term 2", "term 3"], "person": "optional"}}],
  "caption": "1-2 sentence post caption ending with a question that invites comments",
  "hashtags": ["5 to 8 relevant hashtags without the # sign; include shorts and {hashtag}"],
  "fact_check": "the key facts in this script and why they are true"
}}
"""

REVIEW_PROMPT = """You are a strict reviewer for a family-friendly educational Shorts channel (series: "{series}").
Review this script before it is posted publicly with NO human check. Audience: {audience} (includes under-18s).

SCRIPT (JSON):
{script}

Check:
A. Accuracy: is every factual claim true and not exaggerated? Check every date, place, name and
   "first/invented" claim carefully: if ANY of them may be wrong, accuracy fails. List any doubtful claim.
B. Safety: does it follow ALL these rules?
{safety}
C. Engagement: hook strength (1-10), does every scene add something new, is the ending satisfying.
D. Title/caption: honest (not misleading), no hashtags in title.

Approve only if A and B have NO problems and hook strength is at least 7.

Return ONLY JSON:
{{
  "approve": true or false,
  "accuracy_ok": true or false,
  "safety_ok": true or false,
  "hook_score": number,
  "problems": ["short, specific problems; empty if none"],
  "fix_instructions": "how to rewrite to fix every problem (empty if approved)"
}}
"""

TOPIC_PROMPT = """Suggest ONE fresh topic for a viral, family-friendly short video.
Series: "{series}" - {niche}
Audience: {audience} (includes under-18s)
The topic must be specific, surprising, TRUE and well documented (found in encyclopedias or museum
sources), safe to talk about with kids, and explainable in 40 seconds. The topic text itself must
follow the rules below (do not mention smoking, weapons, etc. even in passing).
Prefer topics people would want to share or comment on ("I never knew that!").
{safety}
Do NOT repeat or closely resemble any of these past topics:
{past}

Return ONLY JSON: {{"topic": "..."}}"""

FOOTAGE_PROMPT = """You check stock-video clips chosen for a family-friendly educational short.
Below are numbered thumbnails, each with the narration spoken while it is on screen.
For each clip decide:
- "fits": does the picture reasonably match or illustrate the narration? (a lighter for a sentence
  about a metal melting in your hand does NOT fit; an unrelated pretty background is borderline - say false)
- If a clip shows a person, they must be an ordinary unknown person: NOT a celebrity, politician,
  historical figure or any recognisable real individual (if they look like one, safe = false).
- "safe": is it suitable for under-18s (no violence, weapons, smoking, alcohol, revealing clothing,
  scary images, dangerous acts, brand logos as the focus)?

Return ONLY JSON: {{"clips": [{{"n": 1, "fits": true, "safe": true}}]}}"""


def _models(model) -> list[str]:
    if isinstance(model, (list, tuple)):
        return list(model)
    return [model, "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]


def _gemini(prompt, model, temperature: float = 0.9, label: str = "Script") -> dict:
    """prompt: text, or a list of Gemini 'parts' (text + images).
    Tries each free model in turn; waits and retries when a model is busy (429/500/503)."""
    parts = [{"text": prompt}] if isinstance(prompt, str) else prompt
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    last = ""
    for m in dict.fromkeys(_models(model)):
        for attempt in range(3):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
            try:
                r = requests.post(url, json=body, headers={"x-goog-api-key": env("GEMINI_API_KEY")}, timeout=90)
            except requests.RequestException as e:  # slow or dropped connection: next model
                last = f"{m}: {e}"
                break
            if r.status_code == 200:
                try:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
                    data = json.loads(text)
                    print(f"{label} model: {m}")
                    return data
                except Exception as e:  # odd reply: try again
                    last = f"{m}: unreadable reply ({e})"
                    continue
            last = f"{m}: {r.status_code} {r.text[:200]}"
            if r.status_code in (429, 500, 503):
                time.sleep(10 * (attempt + 1))
                continue
            break  # 400/403/404: this model is not usable, try the next one
    raise RuntimeError(f"Gemini failed on all models. Last error: {last}")


def _cat(cfg: dict, cat: dict | None) -> dict:
    cat = cat or {}
    return {"series": cat.get("series", "Viral Scientist"), "niche": cat.get("niche", cfg["niche"]),
            "hashtag": cat.get("hashtag", "science")}


def pick_topic(cfg: dict, past_topics: list[str], cat: dict | None = None) -> str:
    past = "\n".join(f"- {t}" for t in past_topics[:200]) or "- (none yet)"
    data = _gemini(
        TOPIC_PROMPT.format(audience=cfg["audience"], past=past, safety=SAFETY_RULES, **_cat(cfg, cat)),
        cfg["gemini_model"], temperature=1.1, label="Topic",
    )
    return data["topic"].strip()


def write_script(cfg: dict, topic: str, fix: str = "", cat: dict | None = None) -> dict:
    seconds = int(cfg.get("target_seconds", 40))
    prompt = PROMPT.format(
        audience=cfg["audience"], language=cfg.get("language", "English"),
        topic=topic, seconds=seconds, words=int(seconds * 2.6), safety=SAFETY_RULES, **_cat(cfg, cat),
        ai_people=int(cfg.get("ai_people_per_video", 3)),
    )
    if fix:
        prompt += f"\n\nA reviewer rejected the previous version. Fix ALL of this:\n{fix}\n"
    data = _gemini(prompt, cfg["gemini_model"])
    scenes = [s for s in data.get("scenes", []) if s.get("text", "").strip()]
    if len(scenes) < 3:
        raise RuntimeError("Gemini returned too few scenes; try again.")
    data["scenes"] = scenes
    tags = [h.lstrip("#").replace(" ", "") for h in data.get("hashtags", [])]
    for must in ("shorts", _cat(cfg, cat)["hashtag"]):
        if must.lower() not in [t.lower() for t in tags]:
            tags.append(must)
    data["hashtags"] = tags[:8]
    data.setdefault("topic", topic)
    data.setdefault("hook_text", data.get("title", ""))
    return data


def review_script(cfg: dict, script: dict, cat: dict | None = None) -> dict:
    shown = {k: script.get(k) for k in ("title", "hook_text", "scenes", "caption", "hashtags")}
    data = _gemini(
        REVIEW_PROMPT.format(audience=cfg["audience"], script=json.dumps(shown, ensure_ascii=False),
                             safety=SAFETY_RULES, series=_cat(cfg, cat)["series"]),
        cfg["gemini_model"], temperature=0.1, label="Review",
    )
    data["approve"] = bool(data.get("approve")) and bool(data.get("safety_ok")) and bool(data.get("accuracy_ok")) \
        and float(data.get("hook_score") or 0) >= float(cfg.get("min_hook_score", 7))
    return data


def write_and_review(cfg: dict, topic: str, cat: dict | None = None) -> tuple[dict, dict]:
    """Writes a script and has the AI reviewer check it; rewrites up to `review_rewrites` times."""
    fix = ""
    review = {}
    for attempt in range(int(cfg.get("review_rewrites", 2)) + 1):
        script = write_script(cfg, topic, fix, cat)
        review = review_script(cfg, script, cat)
        print(f"Review {attempt + 1}: approve={review['approve']} hook={review.get('hook_score')} "
              f"problems={review.get('problems')}")
        if review["approve"]:
            return script, review
        fix = review.get("fix_instructions") or "; ".join(review.get("problems") or [])
    return script, review


def check_footage(cfg: dict, items: list[dict]) -> list[dict]:
    """items: [{"thumb": url, "text": narration}]. Returns [{"fits": bool, "safe": bool}] per item.
    If the check cannot run, every clip is treated as fitting and safe (Pixabay safesearch is on)."""
    parts = [{"text": FOOTAGE_PROMPT}]
    for i, it in enumerate(items, 1):
        parts.append({"text": f"Clip {i}. Narration: {it['text']}"})
        try:
            if not str(it["thumb"]).startswith("http"):  # a local AI image
                data, mime = open(it["thumb"], "rb").read(), "image/jpeg"
            else:
                img = requests.get(it["thumb"], timeout=20)
                img.raise_for_status()
                data, mime = img.content, img.headers.get("content-type", "image/jpeg").split(";")[0]
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}})
        except Exception:
            parts.append({"text": "(thumbnail unavailable)"})
    try:
        data = _gemini(parts, cfg["gemini_model"], temperature=0.1, label="Footage check")
        res = {int(c.get("n", 0)): c for c in data.get("clips", [])}
        return [{"fits": bool(res.get(i, {}).get("fits", True)), "safe": bool(res.get(i, {}).get("safe", True))}
                for i in range(1, len(items) + 1)]
    except Exception as e:
        print(f"Footage check skipped: {e}")
        return [{"fits": True, "safe": True} for _ in items]
