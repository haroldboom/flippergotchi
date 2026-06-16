#!/usr/bin/env bash
# Watch the dolphin live in your terminal (no hardware needed).
# Fast-forwarded time so you can see it eat, walk, and level up.
set -e
cd "$(dirname "$0")"
exec python3 -m flippergotchi --simulate --reset \
  --interval 0.4 --time-scale 600 "$@"
