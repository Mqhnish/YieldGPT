# YieldGPT pitch deck (HTML)

`index.html` is a self-contained, 13-slide 16:9 deck in the team's visual style, with motion:
permission checks A to F animated as documents flow and drop out, a hash chain that breaks when
a row is edited, the trust boundaries as a 3D stack, and the live proof numbers counting up.

Present: open `index.html` in Chrome or Safari (fonts load from Google Fonts; without a
connection it falls back to system fonts). Keys: arrows, space or Page Up/Down to move, F for
fullscreen. `index.html#8` opens slide 8. Respects "reduce motion".

PDF for the submission form: `yieldgpt-deck.pdf` (13 pages, 16:9). To regenerate after edits:

```bash
python3 -m http.server 8790 --bind 127.0.0.1   # from this folder, then in another terminal:
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --virtual-time-budget=6000 --no-pdf-header-footer --print-to-pdf=yieldgpt-deck.pdf http://127.0.0.1:8790/
```

Every number on the slides comes from a dated report in `evaluation/reports/` and carries its
label (live, fixture or synthetic). Update the slide when a report changes.
