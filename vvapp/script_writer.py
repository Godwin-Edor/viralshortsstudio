"""Writes the video script with the free Gemini API."""
import json
import re

import requests

from .config import env

PROMPT = """You write scripts for viral faceless short videos (YouTube Shorts, TikTok, Reels).

Channel niche: {niche}
Audience: {audience}
Language: {language}
Video topic: {topic}
Target length: about {seconds} seconds of narration (about {words} words in total).

Rules for a script that people watch to the end:
1. Scene 1 is the HOOK: at most 12 words, a surprising claim or question that creates curiosity. No greetings, no "did you know", no channel name.
2. Every following sentence must add a new surprising detail or answer part of the hook. Short, punchy, spoken-style sentences.
3. Be scientifically accurate. Do not invent numbers, dates or quotes. If unsure, leave the detail out.
4. Final scene: a one-line payoff, then a short question that invites comments.
5. 6 to 9 scenes. Each scene is 1-2 sentences.
6. For each scene give 2 stock-footage search terms (simple, visual, 1-3 English words, e.g. "ice cubes", "lab beaker", "galaxy"), things that exist in stock-video libraries.

Return ONLY valid JSON with this shape:
{{
  "topic": "short topic name",
  "title": "catchy title under 70 characters, no hashtags",
  "scenes": [{{"text": "narration", "footage": ["term 1", "term 2"]}}],
  "caption": "1-2 sentence post caption that adds curiosity",
  "hashtags": ["5 to 8 relevant hashtags without the # sign"],
  "fact_check": "the key facts in this script that a human should double-check before posting"
}}
"""

TOPIC_PROMPT = """Suggest ONE fresh topic for a viral short video.
Channel niche: {niche}
Audience: {audience}
The topic must be specific, surprising, true, and explainable in 40 seconds.
Do NOT repeat or closely resemble any of these past topics:
{past}

Return ONLY JSON: {{"topic": "..."}}"""


def _gemini(prompt: str, model: str, temperature: float = 0.9) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    r = requests.post(url, json=body, headers={"x-goog-api-key": env("GEMINI_API_KEY")}, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:500]}")
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
    return json.loads(text)


def pick_topic(cfg: dict, past_topics: list[str]) -> str:
    past = "\n".join(f"- {t}" for t in past_topics[:150]) or "- (none yet)"
    data = _gemini(
        TOPIC_PROMPT.format(niche=cfg["niche"], audience=cfg["audience"], past=past),
        cfg["gemini_model"],
        temperature=1.1,
    )
    return data["topic"].strip()


def write_script(cfg: dict, topic: str) -> dict:
    seconds = int(cfg.get("target_seconds", 40))
    data = _gemini(
        PROMPT.format(
            niche=cfg["niche"],
            audience=cfg["audience"],
            language=cfg.get("language", "English"),
            topic=topic,
            seconds=seconds,
            words=int(seconds * 2.6),
        ),
        cfg["gemini_model"],
    )
    scenes = [s for s in data.get("scenes", []) if s.get("text", "").strip()]
    if len(scenes) < 3:
        raise RuntimeError("Gemini returned too few scenes; try again.")
    data["scenes"] = scenes
    data["hashtags"] = [h.lstrip("#").replace(" ", "") for h in data.get("hashtags", [])][:8]
    data.setdefault("topic", topic)
    return data
