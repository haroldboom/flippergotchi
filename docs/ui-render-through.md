# UI render-through: harness + app-delivery recommendation (P1 item 7)

*Decision-support spike. Measures the riskiest UI assumption before we build the
device UI layer. No app code changed. Verified claims are cited; anything that
needs real hardware is marked **[NEEDS HARDWARE]**.*

---

## Why this spike exists

Two coupled unknowns gate all the downstream UI work (items 6, 8, 9):

1. **Does our HTML actually render faithfully** through the device's renderer
   (headless WebKit on DRM) at 256x144, 6-bit grayscale? The screens lean on
   gradients, blurred `drop-shadow`s, tiny 6-8px fonts, and color-coded rarity/HP
   -- all of which the review flagged as risky on a 64-level mono panel.
2. **How is a full-screen animated app even delivered** on Flipper One? The
   README says "wrap the markup in a FlipCTL plugin." The review believes that is
   the wrong delivery model.

`tools/shoot.py` addresses (1) -- and finally commits the missing HTML->PNG step
the view layer never had. This doc covers how to run it, and gives a researched
recommendation for (2).

---

## The harness: `tools/shoot.py`

What it does, end to end:

1. Loads a screen's HTML (a file path, a glob of the `*.html` the view layer
   writes to `/tmp/flippergotchi/`, or `-` for stdin).
2. Renders it in **headless WebKit** -- the same engine the device uses -- at
   **exactly 256x144, deviceScaleFactor 1** (the verified panel size).
3. Screenshots it to PNG.
4. Pushes the PNG through the **device panel simulation**: 6-bit (64-level)
   grayscale, mirroring `tools/device_gray.py`'s posterize, **plus dithering**
   (`floyd` = Floyd-Steinberg error diffusion, default; `ordered` = Bayer 8x8;
   `none` = posterize-only, i.e. today's `device_gray` behaviour). Dithering was
   added because the review found posterize-only truncation visibly **bands** the
   gradients every screen uses.

It is intentionally **not** a package runtime dependency (Playwright + a bundled
browser is ~100+ MB). It's a dev/CI tool.

### Install (optional deps)

```bash
pip install playwright pillow numpy
python -m playwright install webkit        # faithful: device runs WebKit
# fallback if WebKit host libs are missing in your sandbox:
python -m playwright install chromium
```

* **WebKit is preferred** and is the default `--browser`, because the device
  renders on headless WebKit-on-DRM. Chromium (Blink) is a convenient fallback
  but is a *different engine* -- treat Chromium output as indicative, not
  authoritative (font hinting, sub-pixel, gradient banding, and `filter`
  compositing all differ between Blink and WebKit).
* `numpy` powers the dithering; without it the harness falls back to
  posterize-only and warns.

### Run it against the project's screens

The app writes each screen as a standalone HTML doc (see `view/flipctl.py` and
`config.py`'s `*_html_out` keys, default `/tmp/flippergotchi/*.html`). So the
zero-touch workflow is: run the app / a screen, then shoot whatever it wrote.

```bash
# 1. one screen the app just wrote, dithered, 4x upscaled for eyeballing:
python tools/shoot.py -o docs/_shots --scale 4 /tmp/flippergotchi/face.html

# 2. every screen the app has produced:
python tools/shoot.py -o docs/_shots /tmp/flippergotchi/*.html

# 3. compare dithering strategies on the same screen (banding check):
python tools/shoot.py -o docs/_shots --dither none    /tmp/flippergotchi/face.html
python tools/shoot.py -o docs/_shots --dither ordered /tmp/flippergotchi/face.html
python tools/shoot.py -o docs/_shots --dither floyd   /tmp/flippergotchi/face.html

# 4. raw WebKit render (no grayscale) to inspect layout/fonts:
python tools/shoot.py --no-gray -o docs/_shots /tmp/flippergotchi/face.html

# 5. from stdin (e.g. piping a render_*() string once the view is refactored):
some_render | python tools/shoot.py -o docs/_shots -
```

Output filenames are `<screen><.dither>.png` in `--out`. `--scale N` does a
nearest-neighbour upscale of the *final* image only (the render itself is always
at native 256x144, so pixel fidelity is preserved).

### What was verified in this environment

* The harness **runs**: rendering + 256x144 clip + 6-bit grayscale + dithering
  all produce correct output (measured <=64 distinct grey levels, exact 256x144).
* **Chromium installs and runs cleanly** here. **WebKit's browser binary
  downloads but fails to launch** in this sandbox for lack of host system
  libraries (`playwright install webkit` warns about missing deps). The harness
  detects this and auto-falls-back to Chromium with a loud stderr warning. On a
  normal dev box, `python -m playwright install webkit` (or
  `--with-deps` on Debian/Ubuntu) fixes this and you get the faithful engine.

### What to test with it now (before hardware exists)

Use the harness to close the cheap, non-hardware risks the review raised:

1. **Gradient banding** -- diff `--dither none` vs `floyd`/`ordered` on `face`,
   `capture`, `blebattle`. Confirm dithering removes the contour lines; decide
   which dither to bake into the live render path.
2. **Color-as-information collapse** -- render rarity borders
   (`#5aa9ff` rare vs `#c07bf0` epic) and HP green/yellow/red; confirm they
   become near-identical luma in grayscale, then validate the redundant cues
   (patterns/letters/borders) the review recommended.
3. **Tiny fonts** -- eyeball 6-8px text legibility at 256x144; `badge_screen.py`'s
   `columns:2 + overflow:hidden` badge clipping.
4. **`filter`/`drop-shadow` cost & correctness** -- some CSS effects render
   differently (or slower) under WebKit than desktop Chrome.

These are all measurable **today** and don't need a device.

### Known limitation **[NEEDS HARDWARE]**

WebKit-in-Playwright is a *close* proxy, not the device. The real target is
headless-WebKit-**on-DRM** on an RK3576 (ARM software compositing, ~123 ppi
panel, possibly a different WebKit build and different available fonts --
`DejaVu Sans Mono` may be absent on the device). Font rendering, antialiasing,
and `filter` compositing performance can only be confirmed on a dev unit. The
harness de-risks *content/layout/grayscale*; it cannot certify on-device
performance or exact glyph rendering.

---

## Recommendation: delivery model

> **Ship Flippergotchi as a sandboxed full-screen WebKit app packaged as
> Flatpak/AppImage -- NOT as a FlipCTL plugin.** Keep FlipCTL only as an optional
> launcher entry. **[Partly unverified -- see open questions.]**

### Evidence

**FlipCTL plugins are menu wrappers around CLI tools, not full-bleed apps
(verified).** The FlipCTL docs state plugins *"are wrappers around cli tools or
services, written in any language"* -- the shipped examples are `ping`, `nmap`,
`traceroute`, `nginx` status, each rendered as a navigable D-pad menu. That is
structurally the opposite of a full-screen animated creature-collector that owns
the frame and its own input.
Sources: [FlipCTL docs](https://docs.flipper.net/one/cpu-software/flipctl),
[FlipCTL blog](https://blog.flipper.net/flipctl-our-gui-framework-for-embedded-linux-systems/).

**But FlipCTL's renderer is exactly our target (verified).** FlipCTL uses *"a
headless webkit instance running directly on top of drm (direct rendering
manager), without xorg or wayland"* and authors UI in **HTML/JS/CSS**. So the
project's core bet -- author HTML at 256x144, render on device WebKit -- is
**right**. The mismatch is only about *packaging*, not the rendering technology.
Source: [FlipCTL docs](https://docs.flipper.net/one/cpu-software/flipctl).

**The final OS is immutable; third-party apps come as Flatpak/AppImage
(reported, not yet in official docs).** Multiple write-ups describe an immutable
root filesystem with A/B partitions (SteamOS/OSTree-style) and third-party apps
sandboxed via **Flatpak or AppImage**; Flipper has posted a "Linux Distro
Engineer" role to build exactly this. This is credible and consistent, but it is
**journalism + a job posting, not a published SDK doc**, so treat it as *likely*
rather than *confirmed*.
Sources:
[XDA: "it's a pocket Linux PC"](https://www.xda-developers.com/dug-into-flipper-one-firmware-not-flipper-zero-sequel/),
[Gadget Hacks](https://mods-n-hacks.gadgethacks.com/news/flipper-one-hacking-tool-pocket-linux-pc-for-security-pros/),
[CNX Software](https://www.cnx-software.com/2026/05/21/flipper-one-a-rockchip-rk3576-powered-portable-arm-linux-computer-and-networking-multi-tool/).

**Note the FlipCTL long-term goal is `apt install flipctl` on any Debian device**
-- i.e. FlipCTL itself is a system/HMI component, reinforcing that it is
infrastructure for menu HMIs, not an app store for games.
Source: [FlipCTL blog](https://blog.flipper.net/flipctl-our-gui-framework-for-embedded-linux-systems/).

**Also confirmed by the earlier review:** FAP files are Flipper *Zero* only --
do **not** aim packaging at FAP. `lab.flipp.dev` and `playground.flippercloud.io`
are unrelated (Zero app catalog / a Ruby SaaS). There is no hosted Flipper One
emulator that runs arbitrary third-party UIs; the only official artifact is a
Figma mock, which cannot run our HTML.

### Why Flatpak/AppImage over a FlipCTL plugin

| | FlipCTL plugin | Flatpak/AppImage full-screen WebKit app |
|---|---|---|
| Fits a menu-of-CLI-tools model | Yes (that's what it's for) | n/a |
| Owns the full frame + animation loop | **No** -- designed for menus | **Yes** |
| Own input routing (D-pad -> game actions) | Constrained to menu nav | **Yes** |
| Matches immutable-OS app story | No | **Yes** (the documented sandbox path) |
| Renders our HTML on device WebKit | via FlipCTL's WebKit | run our own headless-WebKit-on-DRM surface |
| Non-TTY consent surface (item 9) | Awkward | Natural (app owns UI) |

The game is a persistent, full-bleed, animated app with its own input model and
its own (non-TTY) consent UI -- that is an *app*, and the OS's app format is
Flatpak/AppImage.

### Open questions -- **[NEEDS HARDWARE / SDK]**

1. **Does a third-party app get its own headless-WebKit-on-DRM surface**, or must
   all UI go *through* FlipCTL's compositor? If the device only exposes DRM to one
   privileged compositor, a "full-screen app" may still need to render *via*
   FlipCTL (as an HTML frontend it hosts) even while being *packaged* as a
   Flatpak. This is the single most important unknown and is unanswerable without
   the SDK / a dev unit.
2. **Is Flatpak or AppImage (or both) the blessed format**, and is there a signing
   / catalog requirement? Currently only inferred.
3. **How does an app claim the framebuffer and the D-pad/soft-buttons** (item 9)
   -- direct DRM/libinput, or a FlipCTL/OS-mediated API?
4. **Fonts and `filter` performance on-device** (see harness limitation above).

### What to do now (doesn't need hardware)

* Build to the harness: keep authoring HTML/CSS at 256x144, and make the render
  path pluggable (item 6) so the *sink* can be file / screenshot / device without
  touching screen code. This keeps us delivery-model-agnostic until (1) is
  answered.
* Bake the chosen dither into the live render path (not just docs PNGs).
* **Correct the README**: replace "wrap it in a FlipCTL plugin" with "package as a
  sandboxed full-screen WebKit app (Flatpak/AppImage), pending SDK confirmation;
  FlipCTL is the renderer/HMI framework, not the app-delivery format." *(README
  edit intentionally left to the owning change -- flagged here, not done.)*
* Do **not** invest in D-pad-menu-shaped UI or FAP packaging.

---

## Sources

* FlipCTL docs (plugin model + WebKit-on-DRM): https://docs.flipper.net/one/cpu-software/flipctl
* FlipCTL blog (framework goals, `apt install flipctl`): https://blog.flipper.net/flipctl-our-gui-framework-for-embedded-linux-systems/
* Flipper One tech specs (256x144, panel): https://docs.flipper.net/one/general/tech-specs
* CNX Software (RK3576 overview): https://www.cnx-software.com/2026/05/21/flipper-one-a-rockchip-rk3576-powered-portable-arm-linux-computer-and-networking-multi-tool/
* XDA (immutable OS / pocket Linux PC): https://www.xda-developers.com/dug-into-flipper-one-firmware-not-flipper-zero-sequel/
* Gadget Hacks (immutable OS, Flatpak/AppImage sandboxing): https://mods-n-hacks.gadgethacks.com/news/flipper-one-hacking-tool-pocket-linux-pc-for-security-pros/
* Playwright (harness dependency): https://playwright.dev/python/docs/browsers

*Verified = quoted from official Flipper docs. Reported/likely = tech press + a
Flipper job posting, not yet in official SDK docs. Unverified = the on-device
surface/framebuffer/input specifics, which need a dev unit.*
