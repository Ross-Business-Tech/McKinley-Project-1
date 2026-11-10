# Demo video

Finished videos are in [`output/`](output/):

| File | What it is |
| --- | --- |
| `mckinley-demo-full.mp4` | About 2 min 10 s: the full walkthrough, narrated, captions burned in (1920×1080) |
| `mckinley-demo-60s.mp4` | About 56 s: the short clip, cut from the full video |
| `mckinley-demo-full.srt`, `mckinley-demo-60s.srt` | The same captions as separate files, for YouTube, Canvas or a video editor |

Everything is made automatically: a browser clicks through the app's preview (made-up data only), a free voice
model that runs on the machine reads the narration, and the captions come from the same text, so they always match.

## Changing the words or the clicks

Edit [`script.json`](script.json). Each line has:

- `say`: what the narrator says. It is also the caption.
- `caption` (optional): use when the caption should be written differently from how it is spoken
  (for example `say` "nine one one", `caption` "911").
- `do`: what happens on screen while the line is spoken: `click`, `hover`, `select` (a demo sign-in such as `R001`),
  `scroll`, `wait` (seconds) or `goto` (a page such as `/staff/`).
- `short`: scenes with `"short": true` go into the 60-second clip; a line with `"short": false` is left out of it.

Other settings: `voice` (for example `af_heart`, `af_bella`, `am_michael`, `bf_emma`) and `speed` (1.0 is normal).

Then, from the repository root (takes about 6 minutes):

```bash
bash demo-video/make-video.sh
```

Needs Node, Python 3, ffmpeg and Playwright's Chromium (all already in the Business+Tech cloud environment). The
first run downloads the voice model (about 120 MB) from GitHub into `demo-video/.cache/`.

## Files

- `voice.py`: makes one voice recording per line (Kokoro voice model, nothing sent to any service).
- `record.cjs`: clicks through the app and records the screen, waiting for each line to finish.
- `assemble.py`: joins screen, voice and captions; cuts the short clip.
- `make-video.sh`: runs all of the above.
