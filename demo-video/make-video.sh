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

echo "1/4 Building the app"
npm run build >/dev/null

echo "2/4 Making the narrator's voice"
python3 demo-video/voice.py "$WORK"

echo "3/4 Recording the screen"
python3 -m http.server "$PORT" --directory dist >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
sleep 1
NODE_PATH="$(npm root -g)" node demo-video/record.cjs "$WORK" "http://localhost:$PORT"

echo "4/4 Adding voice and captions"
python3 demo-video/assemble.py "$WORK" "$OUT"
