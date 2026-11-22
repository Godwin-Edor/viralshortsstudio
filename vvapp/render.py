"""FFmpeg video assembly: vertical 1080x1920, 30 fps, captions burned in."""
import random
import subprocess
from pathlib import Path

W, H, FPS = 1080, 1920, 30


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("FFmpeg failed:\n" + p.stderr[-2000:])


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def make_shot(src: str, seconds: float, out_path: str) -> str:
    """Crop a clip to vertical full-screen, trim to `seconds`, with a slow push-in zoom."""
    src_len = _duration(src)
    start = 0.0
    if src_len > seconds + 1:
        start = random.uniform(0, min(src_len - seconds - 0.5, 8))
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},"
        f"zoompan=z='1+0.0009*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"
        f"eq=contrast=1.05:saturation=1.12"
    )
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.2f}"]
    if src_len and src_len < seconds:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", src, "-t", f"{seconds:.3f}", "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", out_path]
    _run(cmd)
    return out_path


def color_shot(seconds: float, out_path: str) -> str:
    """Fallback shot when no stock footage is found: animated gradient."""
    _run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        f"gradients=s={W}x{H}:d={seconds:.3f}:speed=0.02:c0=0x0b1e3f:c1=0x1f6f8b:r={FPS}",
        "-t", f"{seconds:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", out_path,
    ])
    return out_path


def concat_shots(shots: list[str], out_path: str) -> str:
    list_file = Path(out_path).with_suffix(".txt")
    list_file.write_text("".join(f"file '{Path(s).resolve()}'\n" for s in shots))
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", out_path])
    return out_path


def concat_audio(parts: list[str], out_path: str, music: str | None = None, music_volume: float = 0.1) -> str:
    cmd = ["ffmpeg", "-y"]
    for p in parts:
        cmd += ["-i", p]
    n = len(parts)
    filt = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[voice]"
    if music:
        cmd += ["-stream_loop", "-1", "-i", music]
        filt += (f";[{n}:a]volume={music_volume}[bg];"
                 f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=0,"
                 f"loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    else:
        filt += ";[voice]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    cmd += ["-filter_complex", filt, "-map", "[a]", "-ar", "48000", "-c:a", "pcm_s16le", out_path]
    _run(cmd)
    return out_path


def final_render(video: str, audio: str, ass_file: str, out_path: str, fonts_dir: str | None = None,
                 duration: float | None = None, bar_color: str = "00E5FF") -> str:
    """Burns in captions/headline and a progress bar along the top edge."""
    ass_arg = Path(ass_file).resolve().as_posix().replace(":", "\\:")
    ass = f"ass='{ass_arg}'" + (f":fontsdir='{fonts_dir}'" if fonts_dir else "")
    dur = duration or _duration(audio) or 40
    filt = (f"[0:v]{ass}[v1];"
            f"color=c=0x{bar_color}:s={W}x14:r={FPS}[bar];"
            f"[v1][bar]overlay=x='-w+w*t/{dur:.3f}':y=0:shortest=1[v]")
    _run([
        "ffmpeg", "-y", "-i", video, "-i", audio, "-filter_complex", filt,
        "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k",
        "-shortest", "-movflags", "+faststart", out_path,
    ])
    return out_path
