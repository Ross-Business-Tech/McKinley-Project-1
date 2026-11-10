"""Make the narrator's voice: one WAV per 'say' line in script.json, plus voice.json with each line's length.

Uses Kokoro, a free voice model that runs on this machine (no API key, nothing sent anywhere).
Usage: python3 demo-video/voice.py <work_dir>
"""

import json
import sys
import urllib.request
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).resolve().parent
MODEL_DIR = HERE / ".cache"
FILES = {
    "kokoro.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx",
    "voices.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}


def ensure_model() -> None:
    MODEL_DIR.mkdir(exist_ok=True)
    for name, url in FILES.items():
        dest = MODEL_DIR / name
        if not dest.exists() or dest.stat().st_size < 1_000_000:
            print(f"Downloading voice model file {name}…")
            urllib.request.urlretrieve(url, dest)


def main() -> None:
    work = Path(sys.argv[1])
    (work / "voice").mkdir(parents=True, exist_ok=True)
    script = json.loads((HERE / "script.json").read_text())
    ensure_model()
    kokoro = Kokoro(str(MODEL_DIR / "kokoro.onnx"), str(MODEL_DIR / "voices.bin"))
    out = []
    total = 0.0
    for si, scene in enumerate(script["scenes"]):
        for li, step in enumerate(scene["steps"]):
            samples, rate = kokoro.create(
                step["say"], voice=script.get("voice", "af_heart"), speed=script.get("speed", 1.0), lang="en-us"
            )
            path = work / "voice" / f"{si:02d}_{li:02d}.wav"
            sf.write(path, samples, rate)
            dur = len(samples) / rate
            total += dur
            out.append({"scene": si, "line": li, "wav": str(path), "duration": dur})
    (work / "voice.json").write_text(json.dumps(out, indent=1))
    print(f"Voice: {len(out)} lines, {total:.1f}s of speech")


if __name__ == "__main__":
    main()
