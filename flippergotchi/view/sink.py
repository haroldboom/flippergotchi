"""The single place the view layer touches the filesystem.

Every ``*_screen`` renderer builds a standalone HTML document as a PURE string
(``..._html(...)``), then routes the actual write through here. This is the
Renderer/sink seam the UI review asked for: today the only sink is a file sink
(``os.makedirs`` + ``open().write()``), but a device sink (push the HTML to a
real Flipper One instead of a file) can be dropped in later without touching a
single renderer.

Keep this tiny and dependency-free: it mirrors, byte-for-byte, the inline I/O
each screen used to do, so on-disk output is unchanged.
"""
from __future__ import annotations

import os


class FileSink:
    """Writes a rendered HTML document to the local filesystem.

    ``write`` expands ``~``, creates the parent directory if needed, writes the
    document, and returns the (expanded) path -- exactly what every screen used
    to do inline.
    """

    def write(self, path: str, html: str) -> str:
        path = os.path.expanduser(path)
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w") as f:
            f.write(html)
        return path


# The process-wide default sink. Swap this for a DeviceSink (same ``.write``
# duck-type) to target a real device without editing any renderer.
default_sink: FileSink = FileSink()


def write(path: str, html: str) -> str:
    """Route an HTML document through the default sink; return the written path."""
    return default_sink.write(path, html)
