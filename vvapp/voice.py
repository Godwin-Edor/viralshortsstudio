"""Free neural voiceover with word timings (for captions) using edge-tts."""
import asyncio
import subprocess

import edge_tts


def audio_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


async def _speak(text: str, voice: str, rate: str, out_path: str) -> list[dict]:
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    except TypeError:  # older edge-tts versions sent word boundaries by default
        comm = edge_tts.Communicate(text, voice, rate=rate)
    words = []
    with open(out_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append({"word": chunk["text"], "start": start, "end": start + chunk["duration"] / 1e7})
    return words


def synthesize(text: str, voice: str, rate: str, out_path: str) -> tuple[list[dict], float]:
    """Returns (word timings in seconds, audio duration)."""
    for attempt in range(3):
        try:
            words = asyncio.run(_speak(text, voice, rate, out_path))
            break
        except Exception:
            if attempt == 2:
                raise
    duration = audio_duration(out_path)
    if not words:  # fallback: spread words evenly if no timings came back
        tokens = text.split()
        step = duration / max(len(tokens), 1)
        words = [{"word": w, "start": i * step, "end": (i + 1) * step} for i, w in enumerate(tokens)]
    return words, duration
