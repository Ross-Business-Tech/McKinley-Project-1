"""Put the recording, voice and captions together.

Makes, in <out_dir>:
  mckinley-demo-full.mp4    the full demo, captions burned in
  mckinley-demo-full.srt    the same captions as a separate file (for YouTube, Canvas, etc.)
  mckinley-demo-60s.mp4     the short clip, cut from scenes marked "short": true
  mckinley-demo-60s.srt
Usage: python3 demo-video/assemble.py <work_dir> <out_dir>
"""

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import soundfile as sf

FPS = 30
RATE = 24000
STYLE = (
    "FontName=Inter,FontSize=12,PrimaryColour=&H00FFFFFF,OutlineColour=&H28000000,BackColour=&H28000000,"
    "BorderStyle=3,Outline=5,Shadow=0,MarginV=12,MarginL=40,MarginR=40,Alignment=2"
)


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode:
        sys.exit(f"ffmpeg failed:\n{r.stderr[-2000:]}")


def ts(t: float) -> str:
    ms = int(round(max(t, 0) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def chunk(text: str, limit: int = 84) -> list[str]:
    """Split a line into caption-sized pieces, preferring to break after punctuation."""
    pieces: list[str] = []
    for p in re.split(r"(?<=[.,:;?!])\s+", text):
        if pieces and len(pieces[-1]) < 12:  # don't leave a tiny piece like "Next," on its own
            pieces[-1] += " " + p
        else:
            pieces.append(p)
    out: list[str] = []
    for p in pieces:
        if out and len(out[-1]) + 1 + len(p) <= limit:
            out[-1] += " " + p
        elif len(p) <= limit:
            out.append(p)
        else:
            words, cur = p.split(), ""
            n = -(-len(p) // limit)  # balanced split
            target = len(p) / n
            for w in words:
                if cur and len(cur) + 1 + len(w) > target + 6:
                    out.append(cur)
                    cur = w
                else:
                    cur = f"{cur} {w}".strip()
            out.append(cur)
    return out


def captions(lines: list[dict]) -> list[tuple[float, float, str]]:
    """One or more captions per spoken line (at most two rows each), timed by length."""
    out = []
    for ln in lines:
        chunks = [c if len(c) <= 46 else "\n".join(textwrap.wrap(c, len(c) // 2 + 6)) for c in chunk(ln["text"])]
        total = sum(len(c) for c in chunks)
        t = ln["start"]
        for c in chunks:
            d = ln["duration"] * len(c) / total
            out.append((t, t + d, c))
            t += d
    return out


def write_srt(caps: list[tuple[float, float, str]], path: Path) -> None:
    path.write_text("".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(caps, 1)))


def main() -> None:
    work, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    frames = json.loads((work / "frames.json").read_text())
    tl = json.loads((work / "timeline.json").read_text())
    t0 = frames[0]["t"]
    end = tl["end"] - t0

    # 1. Silent video from the screen frames, each shown until the next one arrived.
    concat = work / "frames.txt"
    with concat.open("w") as f:
        for i, fr in enumerate(frames):
            nxt = frames[i + 1]["t"] if i + 1 < len(frames) else tl["end"]
            f.write(f"file '{Path(fr['file']).resolve()}'\nduration {max(nxt - fr['t'], 0.001):.4f}\n")
        f.write(f"file '{Path(frames[-1]['file']).resolve()}'\n")
    raw = work / "raw.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-vf",
         f"fps={FPS},scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
         "-t", f"{end:.3f}", str(raw)])

    # 2. Narration track: every line placed where it was spoken during the recording.
    audio = np.zeros(int((end + 1) * RATE), dtype=np.float32)
    lines = []
    for ln in tl["lines"]:
        s, rate = sf.read(Path(ln["wav"]).resolve(), dtype="float32")
        assert rate == RATE
        start = max(ln["t"] - t0, 0.0)
        i = int(start * RATE)
        audio[i : i + len(s)] += s[: len(audio) - i]
        lines.append({**ln, "start": start})
    peak = float(np.abs(audio).max()) or 1.0
    sf.write(work / "voice.wav", audio * (0.89 / peak), RATE)

    # 3. Full video with captions and gentle fades.
    caps = captions(lines)
    write_srt(caps, out / "mckinley-demo-full.srt")
    srt_in = work / "full.srt"
    write_srt(caps, srt_in)
    full = out / "mckinley-demo-full.mp4"
    run(["ffmpeg", "-y", "-i", str(raw), "-i", str(work / "voice.wav"), "-vf",
         f"subtitles={srt_in}:force_style='{STYLE}',fade=t=in:st=0:d=0.6,fade=t=out:st={end - 0.8:.2f}:d=0.8",
         "-af", f"afade=t=out:st={end - 0.8:.2f}:d=0.8",
         "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "160k",
         "-t", f"{end:.3f}", "-movflags", "+faststart", str(full)])
    print(f"Full video: {end:.1f}s -> {full}")

    # 4. Short clip: the lines marked short, joined with quick fades.
    #    Each line runs until the next line starts; touching lines are kept as one piece.
    runs = []
    for i, ln in enumerate(lines):
        if not ln.get("short"):
            continue
        a = ln["start"]
        b = lines[i + 1]["start"] if i + 1 < len(lines) else end
        if runs and abs(runs[-1][1] - a) < 0.01:
            runs[-1][1] = b
        else:
            runs.append([a, b])
    parts, short_caps, offset = [], [], 0.0
    for a, b in runs:
        d = b - a
        part = work / f"short_{len(parts)}.mp4"
        run(["ffmpeg", "-y", "-ss", f"{a:.3f}", "-i", str(raw), "-ss", f"{a:.3f}", "-i", str(work / "voice.wav"),
             "-t", f"{d:.3f}", "-vf", f"fade=t=in:st=0:d=0.25,fade=t=out:st={d - 0.3:.2f}:d=0.3",
             "-af", f"afade=t=in:st=0:d=0.05,afade=t=out:st={d - 0.25:.2f}:d=0.25",
             "-c:v", "libx264", "-crf", "16", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "48000", str(part)])
        parts.append(part)
        short_caps += [(s - a + offset, e - a + offset, t) for s, e, t in caps if a - 0.01 <= s < b]
        offset += d
    lst = work / "short.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    joined = work / "short_joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    write_srt(short_caps, out / "mckinley-demo-60s.srt")
    srt_s = work / "short.srt"
    write_srt(short_caps, srt_s)
    short = out / "mckinley-demo-60s.mp4"
    run(["ffmpeg", "-y", "-i", str(joined), "-vf", f"subtitles={srt_s}:force_style='{STYLE}'",
         "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(short)])
    print(f"Short clip: {offset:.1f}s -> {short}")
    if offset > 60.5:
        print(f"  ! The short clip is {offset:.0f}s, over 60s. Mark fewer scenes \"short\": true or shorten their lines.")


if __name__ == "__main__":
    main()
