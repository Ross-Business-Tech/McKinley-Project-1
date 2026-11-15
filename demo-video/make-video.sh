#!/usr/bin/env bash
# Builds the demo videos from demo-video/script.json. Run from the repository root:
#   bash demo-video/make-video.sh
# Output: demo-video/output/ (full video, 60-second clip, and caption .srt files)
set -euo pipefail
cd "$(dirname "$0")/.."
WORK="demo-video/.work"
OUT="demo-video/output"
PORT=4173
mkdir -p "$WORK" "$OUT"

python3 -c "import kokoro_onnx, soundfile" 2>/dev/null || pip install -q kokoro-onnx soundfile
command -v ffmpeg >/dev/null || { echo "ffmpeg is needed"; exit 1; }

# SITE=<url> records an app that is already running (e.g. the live local setup in README.md);
# otherwise the static preview is built and served.
if [ -z "${SITE:-}" ]; then
  echo "1/4 Building the app"
  npm run build >/dev/null
fi

echo "2/4 Making the narrator's voice"
python3 demo-video/voice.py "$WORK"

echo "3/4 Recording the screen"
if [ -z "${SITE:-}" ]; then
  python3 -m http.server "$PORT" --directory dist >/dev/null 2>&1 &
  SERVER=$!
  trap 'kill $SERVER 2>/dev/null || true' EXIT
  sleep 1
  SITE="http://localhost:$PORT"
fi
COVER_PNG="$OUT/cover.png" NODE_PATH="$(npm root -g)" node demo-video/record.cjs "$WORK" "$SITE"

echo "4/4 Adding voice and captions"
python3 demo-video/assemble.py "$WORK" "$OUT"
