# Device-accurate render previews

These PNGs approximate what each screen looks like on the **actual Flipper One
panel** — 256×144, 6-bit (64-level) grayscale — rather than the colour/browser
renders in `../` (the README showcase). They are produced by `tools/shoot.py`:
the screen's HTML is rendered in **headless WebKit** (the same engine the device
runs on DRM) at exactly 256×144, then pushed through a 6-bit grayscale + **Floyd–
Steinberg dithering** step, and finally nearest-neighbour upscaled 4× for viewing.

The dithering is why the dark backgrounds show a fine stipple instead of smooth
gradients — that is deliberate: on a 64-level panel the smooth CSS gradients would
otherwise band, and dithering is what the review recommended to fix it.

## Fidelity caveats — read before trusting these

- **WebKit engine, but not on-device.** These were shot with Playwright's headless
  WebKit on a Linux host, which is the correct *engine* but **not the device's
  WebKit-on-DRM surface**. Font hinting/metrics, the exact panel gamma, and refresh
  behaviour can still differ. Treat these as a faithful *proxy*, not ground truth —
  only real hardware confirms the final look.
- **Fonts may differ.** The screens use `DejaVu Sans Mono`; if the device WebKit
  lacks it, small text will fall back to a different face. (Flagged in the UI review.)
- **Static snapshots.** Animated screens (capture, BLE battle) are shown as
  individual frames (`capture_0..3`); the review separately notes the current
  file-per-frame model won't animate smoothly on-device.
- **Regenerate, don't hand-edit.** To refresh:
  ```
  pip install playwright pillow numpy && python -m playwright install webkit --with-deps
  python -m flippergotchi --simulate --ticks 40 --interval 0    # write the HTML
  python -m flippergotchi --simulate encounter feed achievements gear   # more screens
  python tools/shoot.py --browser webkit --dither floyd --scale 4 -o docs/device \
      /tmp/flippergotchi/*.html /tmp/flippergotchi/capture/*.html
  ```

## The set

| File | Screen |
|---|---|
| `face.floyd.png` | Main HUD (pet + HP/XP/food/energy + dialogue) |
| `prime.floyd.png` | The HUD at the `prime` evolution stage (L20) |
| `encounter.floyd.png` | WiFi-monster encounter (capture / run) |
| `capture_0..3.floyd.png` | Net-gun capture animation frames |
| `feed.floyd.png` | Feeding / larder screen |
| `equip.floyd.png` | Equipment / gear screen |
| `badges.floyd.png` | Achievement badge wall |
| `battlemenu.floyd.png` | Battle Dojo menu |
| `battlelist.floyd.png` | Battle target list |

Screen content is from a `--simulate` session, so names/levels/SSIDs are sample data.
