"""Mascot rendering: variants produce distinct colours and unique ids."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.view.mascot import VARIANTS, _PAL, mascot_svg


def test_every_variant_renders():
    for v in VARIANTS:
        svg = mascot_svg("content", None, "adult", v)
        assert svg.startswith("<defs>") and "</g>" in svg


def test_variant_uses_its_body_colour():
    for v in VARIANTS:
        top = _PAL[v]["b"][0]
        assert top in mascot_svg("content", None, "adult", v)


def test_ids_are_unique_per_call():
    # two renders on one "page" must not share gradient ids
    a = mascot_svg("content", None, "adult", "blue")
    b = mascot_svg("content", None, "adult", "blue")
    import re
    ida = set(re.findall(r'id="(body_\d+)"', a))
    idb = set(re.findall(r'id="(body_\d+)"', b))
    assert ida and idb and ida.isdisjoint(idb)


def test_patterns_present_for_tiger_and_reef():
    assert "clip-path" in mascot_svg("content", None, "adult", "tiger")   # stripes
    assert "clip-path" in mascot_svg("content", None, "adult", "reef")    # spots
    assert "clip-path" not in mascot_svg("content", None, "adult", "blue")


def test_egg_renders_for_any_variant():
    for v in VARIANTS:
        assert "M" in mascot_svg("content", None, "egg", v)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
