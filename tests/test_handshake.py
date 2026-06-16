"""Pure-python pcap EAPOL validator checks (no external tools needed).

We hand-build tiny binary pcap fixtures with EAPOL-Key frames so the stdlib
fallback in core.handshake is exercised end to end.
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.core import handshake as hs

LINKTYPE_ETHERNET = 1


def _pcap_global_header(linktype: int = LINKTYPE_ETHERNET) -> bytes:
    # magic, ver_major, ver_minor, thiszone, sigfigs, snaplen, network
    return struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, linktype)


def _pcap_record(frame: bytes) -> bytes:
    return struct.pack("<IIII", 0, 0, len(frame), len(frame)) + frame


def _eapol_key_frame(key_info: int, key_data: bytes = b"") -> bytes:
    """Ethernet frame carrying an EAPOL-Key with the given key-info flags."""
    dst = bytes.fromhex("aabbccddee01")
    src = bytes.fromhex("aabbccddee02")
    ethertype = struct.pack(">H", 0x888E)
    # EAPOL header: version=2, type=3 (EAPOL-Key), length
    # Key frame body: desc(1) key_info(2) key_len(2) replay(8) nonce(32)
    #   iv(16) rsc(8) id(8) mic(16) key_data_len(2) key_data...
    body = b"\x02"                       # descriptor type
    body += struct.pack(">H", key_info)  # key information
    body += struct.pack(">H", 16)        # key length
    body += b"\x00" * 8                  # replay counter
    body += b"\x11" * 32                 # nonce
    body += b"\x00" * 16                 # key iv
    body += b"\x00" * 8                  # key rsc
    body += b"\x00" * 8                  # key id
    body += b"\x00" * 16                 # key mic
    body += struct.pack(">H", len(key_data)) + key_data
    eapol = b"\x02\x03" + struct.pack(">H", len(body)) + body
    return dst + src + ethertype + eapol


# key-info flag helpers (mirrors core.handshake._classify_eapol)
PAIRWISE = 0x0008
INSTALL = 0x0040
ACK = 0x0080
MIC = 0x0100
SECURE = 0x0200


def _m1() -> bytes:
    return _eapol_key_frame(PAIRWISE | ACK)


def _m2() -> bytes:
    return _eapol_key_frame(PAIRWISE | MIC)


def _m3() -> bytes:
    return _eapol_key_frame(PAIRWISE | ACK | MIC | INSTALL | SECURE)


def _write(path: str, frames: list) -> None:
    blob = _pcap_global_header()
    for f in frames:
        blob += _pcap_record(f)
    with open(path, "wb") as fh:
        fh.write(blob)


def test_missing_file_is_safe(tmp_path):
    info = hs.analyze_capture(str(tmp_path / "nope.pcap"))
    assert info.exists is False
    assert not info            # falsey
    assert info.has_complete_4way is False
    assert info.is_crackable is False


def test_empty_file_is_safe(tmp_path):
    p = tmp_path / "empty.pcap"
    p.write_bytes(b"")
    info = hs.analyze_capture(str(p))
    assert info.exists is True and info.size == 0
    assert not info


def test_garbage_file_is_safe(tmp_path):
    p = tmp_path / "garbage.pcap"
    p.write_bytes(os.urandom(64))
    info = hs.analyze_capture(str(p))
    # Should not raise, and should not claim a crackable handshake.
    assert info.eapol_messages == set()
    assert info.has_complete_4way is False


def test_detects_single_eapol_message(tmp_path):
    p = tmp_path / "m1.pcap"
    _write(str(p), [_m1()])
    info = hs.analyze_capture(str(p))
    assert 1 in info.eapol_messages
    assert info.has_complete_4way is False    # one message alone isn't enough


def test_complete_4way_m1_m2(tmp_path):
    p = tmp_path / "hs.pcap"
    _write(str(p), [_m1(), _m2()])
    info = hs.analyze_capture(str(p))
    assert {1, 2} <= info.eapol_messages
    assert info.has_complete_4way is True
    assert info.is_crackable is True
    assert bool(info) is True


def test_complete_4way_m2_m3(tmp_path):
    p = tmp_path / "hs23.pcap"
    _write(str(p), [_m2(), _m3()])
    info = hs.analyze_capture(str(p))
    assert {2, 3} <= info.eapol_messages
    assert info.has_complete_4way is True


def test_classifies_m3(tmp_path):
    p = tmp_path / "m3.pcap"
    _write(str(p), [_m3()])
    info = hs.analyze_capture(str(p))
    assert 3 in info.eapol_messages


def test_records_bssid(tmp_path):
    p = tmp_path / "b.pcap"
    _write(str(p), [_m1()])
    info = hs.analyze_capture(str(p))
    assert "aa:bb:cc:dd:ee:01" in info.bssids
    assert "aa:bb:cc:dd:ee:02" in info.bssids


def test_pmkid_in_m1_keydata(tmp_path):
    # RSN PMKID KDE: dd 14 00 0f ac 04 <16-byte PMKID>
    kde = b"\xdd\x14\x00\x0f\xac\x04" + b"\x42" * 16
    frame = _eapol_key_frame(PAIRWISE | ACK, key_data=kde)
    p = tmp_path / "pmkid.pcap"
    _write(str(p), [frame])
    info = hs.analyze_capture(str(p))
    assert info.contains_pmkid is True
    assert info.is_crackable is True


def test_to_hc22000_no_tool_returns_none(tmp_path, monkeypatch):
    import shutil as _sh
    monkeypatch.setattr(_sh, "which", lambda *_a, **_k: None)
    p = tmp_path / "x.pcap"
    _write(str(p), [_m1(), _m2()])
    assert hs.to_hc22000(str(p)) is None


def test_to_hc22000_missing_path_returns_none():
    assert hs.to_hc22000("/does/not/exist.pcap") is None


def test_pcapng_section_header_does_not_crash(tmp_path):
    # A bare pcapng Section Header Block: must parse safely (no packets).
    shb = struct.pack("<I", 0x0A0D0D0A)          # block type
    shb += struct.pack("<I", 28)                  # total length
    shb += struct.pack("<I", 0x1A2B3C4D)          # byte-order magic
    shb += struct.pack("<HH", 1, 0)               # version
    shb += struct.pack("<q", -1)                  # section length
    shb += struct.pack("<I", 28)                  # trailing total length
    p = tmp_path / "ng.pcapng"
    p.write_bytes(shb)
    info = hs.analyze_capture(str(p))
    assert info.exists is True
    assert info.has_complete_4way is False


if __name__ == "__main__":
    import tempfile
    import types

    class _TP:
        def __init__(self, d):
            self._d = d

        def __truediv__(self, name):
            return types.SimpleNamespace(
                __fspath__=lambda: os.path.join(self._d, name),
                write_bytes=lambda b: open(os.path.join(self._d, name), "wb").write(b),
            )

    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                import inspect
                kwargs = {}
                params = inspect.signature(fn).parameters
                if "tmp_path" in params:
                    kwargs["tmp_path"] = _TP(d)
                if "monkeypatch" in params:
                    continue  # skip monkeypatch tests in standalone mode
                fn(**kwargs)
            print(f"ok  {name}")
    print("all good")
