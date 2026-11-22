"""Builds bold, word-by-word highlighted captions (ASS subtitle file)."""
import re


def _ass_color(hex_rgb: str) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}&".upper()


def _ts(t: float) -> str:
    t = max(t, 0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _clean(word: str) -> str:
    return word.replace("{", "").replace("}", "").replace("\\", "").upper()


def _group(words: list[dict], per_line: int) -> list[list[dict]]:
    groups, cur = [], []
    for w in words:
        cur.append(w)
        ends_sentence = bool(re.search(r"[.!?,;:]$", w["word"]))
        if len(cur) >= per_line or ends_sentence:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def build_ass(words: list[dict], total_duration: float, cfg: dict, out_path: str) -> str:
    """words: [{word, start, end}] with times in seconds over the WHOLE video."""
    c = cfg.get("captions", {})
    font = c.get("font", "Montserrat")
    size = int(c.get("size", 96))
    per_line = int(c.get("words_per_line", 3))
    hi = _ass_color(c.get("highlight_color", "00E5FF"))
    margin_v = int(c.get("position_from_bottom", 620))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,7,3,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    groups = _group(words, per_line)
    for gi, g in enumerate(groups):
        group_end = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else min(g[-1]["end"] + 0.4, total_duration)
        for wi, w in enumerate(g):
            start = w["start"]
            end = g[wi + 1]["start"] if wi + 1 < len(g) else group_end
            if end <= start:
                end = start + 0.05
            parts = []
            for wj, other in enumerate(g):
                text = _clean(other["word"])
                if wj == wi:
                    parts.append(f"{{\\c{hi}}}{text}{{\\c&H00FFFFFF&}}")
                else:
                    parts.append(text)
            pop = "{\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{pop}{' '.join(parts)}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")
    return out_path
