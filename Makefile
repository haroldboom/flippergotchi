# Flippergotchi dev tasks. Core install is dependency-free; the preview harness
# needs Playwright + Pillow/numpy (see `make previews-deps`).

PY      ?= python3
BROWSER ?= webkit          # device engine; use BROWSER=chromium as a fallback
DITHER  ?= floyd           # floyd | ordered | none
SCALE   ?= 4               # nearest-neighbour upscale for viewing
SHOT_DIR ?= docs/device
TMP     ?= /tmp/flippergotchi
TICKS   ?= 60

.PHONY: help test previews previews-deps

help:
	@echo "Targets:"
	@echo "  test           run the test suite"
	@echo "  previews-deps  install the preview harness deps (Playwright + WebKit)"
	@echo "  previews       regenerate docs/device/ device-accurate render previews"
	@echo "Vars: PY=$(PY) BROWSER=$(BROWSER) DITHER=$(DITHER) SCALE=$(SCALE) SHOT_DIR=$(SHOT_DIR)"

test:
	$(PY) -m pytest -q

# One-time (dev/CI): the harness deps are NOT package runtime deps.
previews-deps:
	$(PY) -m pip install playwright pillow numpy
	$(PY) -m playwright install --with-deps $(BROWSER)

# Regenerate the device-accurate preview set: drive the app in --simulate to
# write each screen's HTML, then render HTML -> 256x144 WebKit -> 6-bit grayscale
# + dithering via tools/shoot.py. See docs/device/README.md for the caveats.
previews:
	rm -rf $(TMP)
	$(PY) tools/gen_preview_html.py >/dev/null
	$(PY) tools/shoot.py --browser $(BROWSER) --dither $(DITHER) --scale $(SCALE) \
		-o $(SHOT_DIR) $(TMP)/*.html $(TMP)/capture/*.html
	@test -s $(SHOT_DIR)/face.floyd.png || { echo "ERROR: no previews produced"; exit 1; }
	@echo "previews written to $(SHOT_DIR)/"
