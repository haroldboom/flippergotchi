# Packaging & on-device install (Flipper One / aarch64)

The Flipper One is an **RK3576 aarch64 Arm-Linux** device. This document covers
building/installing Flippergotchi on it, which optional extras to install for
each backend, the `llama-cpp-python` aarch64 wheel-vs-source story, and the
systemd install pointer.

> Version: `pyproject.toml` and `flippergotchi/__init__.py` are both `0.9.0`.

## Core install is dependency-free

The runtime core needs **nothing beyond the Python 3.10+ stdlib**. Everything
else is an opt-in extra. The bare install (and the `--simulate` dev path) never
pulls a C extension:

```bash
pip install .
# or, for development:
pip install -e .
```

## Extras: which one for which backend

Declared in `pyproject.toml` under `[project.optional-dependencies]` and
mirrored in `requirements.txt` comments:

| Extra      | Installs                  | Enables |
|------------|---------------------------|---------|
| `ai-cpu`   | `llama-cpp-python==0.3.32` | `ai_backend = "cpu"` — run a local GGUF model via llama.cpp |
| `ai`       | (alias of `ai-cpu`)       | back-compat name |
| `ble`      | `bleak>=0.22`             | live BLE scanning + Flippergotchi peer discovery (BlueZ on Linux) |
| `wifi`     | `scapy>=2.5.0`            | native 802.11 capture parsing |
| `dev`      | `pytest`                  | the test suite |
| `tools`    | `numpy`, `Pillow`         | **host-only** sprite regeneration (`tools/gen_sprite.py`) — NOT a device dep |

Install one or several:

```bash
pip install ".[ai-cpu]"          # CPU AI backend
pip install ".[ble]"             # BLE peers
pip install ".[ai-cpu,ble]"      # combine
```

`ai_backend = "npu"` uses the on-device **RKLLM runtime** that ships with the
NPU driver and is not a pip dependency. `wifi` recon on the device also relies
on the system packages `bettercap` and (for the walking mechanic) `gpsd`.

## `llama-cpp-python` on aarch64: wheel vs. source build

`llama-cpp-python` is a C++ extension. Installation depends on whether a
prebuilt wheel exists for your (arch, Python) pair:

- **Prebuilt CPU wheel (preferred).** The project publishes aarch64/arm64
  CPU wheels for **CPython 3.8–3.12**. Flippergotchi's classifiers target
  3.10–3.12, so on the device you should land on a wheel with no compiler
  needed:

  ```bash
  pip install ".[ai-cpu]"
  ```

  The maintainer also hosts a per-backend wheel index if the default PyPI wheel
  does not match; basic CPU wheels can be pulled with an `--extra-index-url`
  (see <https://abetlen.github.io/llama-cpp-python/whl/>).

- **Source build (fallback).** On **Python 3.13+**, or any arch/Python combo
  without a matching wheel, `pip` downloads the sdist and compiles it. Provide a
  toolchain first:

  ```bash
  # Debian/Ubuntu-based rootfs on the device:
  sudo apt-get install -y build-essential cmake python3-dev
  pip install ".[ai-cpu]"          # now builds from source
  ```

  The build is CPU-bound and slow on the RK3576; do it once and cache the wheel:

  ```bash
  pip wheel "llama-cpp-python==0.3.32" -w /var/cache/flippergotchi-wheels
  pip install --no-index --find-links /var/cache/flippergotchi-wheels ".[ai-cpu]"
  ```

Pin rationale: `0.3.32` is the current release at time of writing and is the
version whose aarch64 CPU wheels cover the supported interpreters.

## Building an sdist / wheel

`MANIFEST.in` ships the packaging artifacts (systemd unit(s) under
`packaging/*.service`, `config.example.toml`, and this doc) into the sdist:

```bash
pip install build
python -m build              # produces dist/*.tar.gz and dist/*.whl
```

## systemd install

A unit file is provided at **`packaging/flippergotchi.service`** (added
alongside this work). After installing the package on the device:

```bash
sudo cp packaging/flippergotchi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now flippergotchi.service
```

Copy `config.example.toml` to the runtime config location the service expects
before starting. Note that under systemd `HOME` may be unset, which affects
`~/.flippergotchi` state-dir resolution — configure an explicit state directory
(tracked separately as P1 item 12).

## CI coverage

`.github/workflows/ci.yml` runs:

- **`test`** — pytest on x86_64 across Python 3.10/3.11/3.12.
- **`smoke`** — a headless `--simulate` run.
- **`aarch64`** — core install + `--simulate` + full pytest inside an arm64
  container via `docker/setup-qemu-action` (guards arch-specific breakage).
- **`ble-import`** — installs the `ble` extra and validates the `bleak`/BlueZ
  import (functional BLE can't run on hosted runners: no adapter).
