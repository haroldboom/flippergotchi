"""Validate that a capture file actually contains a usable WPA handshake/PMKID
*before* we burn CPU/GPU time trying to crack it.

Two layers, best-first:

  1. ``hcxpcapngtool`` (the modern hcxtools) if it's installed -- it understands
     pcap/pcapng, radiotap, every EAPOL quirk, and PMKIDs, and emits a tidy
     ``--info`` summary on stderr. We parse that.
  2. A tiny pure-stdlib pcap/pcapng EAPOL sniffer fallback so validation still
     works on a box with NO external tools (and so our unit tests can run on
     hand-built fixtures). It walks the packet records, finds EAPOL-Key frames
     (ethertype 0x888e), and classifies M1..M4 from the WPA key-info flags.

Nothing in here ever raises: every entry point returns a safe, falsey-ish
``CaptureInfo`` (or ``None`` for the converter) on any error.

The pure-python sniffer is best-effort: it handles the common
Ethernet / 802.11+radiotap link types well enough to spot EAPOL and tell M1-M4
apart, which is all the validator needs. It is NOT a full 802.11 stack.
NEEDS ON-HARDWARE VALIDATION against real Flipper One captures.
"""
from __future__ import annotations

import binascii  # noqa: F401  (kept for hex debugging / house API parity)
import logging
import os
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# pcap/pcapng magic numbers + the link-layer types we know how to peel.
_PCAP_MAGIC_LE = 0xA1B2C3D4
_PCAP_MAGIC_BE = 0xD4C3B2A1
_PCAP_MAGIC_NS_LE = 0xA1B23C4D  # nanosecond-resolution variant
_PCAP_MAGIC_NS_BE = 0x4D3CB2A1
_PCAPNG_MAGIC = 0x0A0D0D0A      # pcapng Section Header Block type

LINKTYPE_ETHERNET = 1
LINKTYPE_IEEE802_11 = 105
LINKTYPE_IEEE802_11_RADIOTAP = 127
LINKTYPE_PRISM = 119
LINKTYPE_PPI = 192

_EAPOL_ETHERTYPE = 0x888E

# How many bytes we're willing to read from any one record (sanity cap).
_MAX_REC = 65535


@dataclass
class CaptureInfo:
    """Everything we can cheaply learn about a capture file.

    Falsey/empty by default so callers can treat a failed parse as "nothing
    crackable here" without special-casing exceptions.
    """

    path: str = ""
    exists: bool = False
    size: int = 0
    contains_pmkid: bool = False
    eapol_messages: set = field(default_factory=set)   # subset of {1,2,3,4}
    bssids: list = field(default_factory=list)
    essids: list = field(default_factory=list)
    tool: str = "none"                                  # which parser produced this

    @property
    def has_complete_4way(self) -> bool:
        """Enough EAPOL frames to compute a crackable MIC.

        The MIC lives in M2/M3/M4; we need the ANonce (M1) and at least one
        MIC-bearing reply. M1+M2 (the classic pair) or M2+M3 both qualify.
        A lone PMKID is handled separately via ``is_crackable``.
        """
        m = self.eapol_messages
        return (1 in m and 2 in m) or (2 in m and 3 in m)

    @property
    def is_crackable(self) -> bool:
        """A capture is worth handing to hashcat if it has a PMKID OR a usable
        4-way exchange."""
        return self.contains_pmkid or self.has_complete_4way

    def __bool__(self) -> bool:
        return self.exists and self.is_crackable


def analyze_capture(path: str | None) -> CaptureInfo:
    """Inspect *path* and report what's crackable inside. Never raises."""
    info = CaptureInfo(path=path or "")
    try:
        if not path or not os.path.exists(path):
            return info
        info.exists = True
        info.size = os.path.getsize(path)
        if info.size <= 0:
            return info

        # Prefer hcxpcapngtool's authoritative summary when available.
        if shutil.which("hcxpcapngtool"):
            try:
                if _analyze_with_hcx(path, info):
                    return info
            except Exception:  # noqa: BLE001 - fall through to python sniffer
                log.debug("hcxpcapngtool analysis failed; using python fallback",
                          exc_info=True)

        # Pure-stdlib fallback.
        try:
            _analyze_with_python(path, info)
        except Exception:  # noqa: BLE001 - never raise out of validation
            log.debug("python capture analysis failed", exc_info=True)
        return info
    except Exception:  # noqa: BLE001 - belt and suspenders
        log.debug("analyze_capture failed", exc_info=True)
        return info


def to_hc22000(path: str | None, out: str | None = None) -> str | None:
    """Convert a capture to hashcat's 22000 format via hcxpcapngtool.

    Returns the output path on success, or ``None`` if there's no tool or
    nothing convertible (no handshake/PMKID). Never raises.
    NEEDS ON-HARDWARE VALIDATION.
    """
    try:
        if not path or not os.path.exists(path):
            return None
        hcx = shutil.which("hcxpcapngtool")
        if not hcx:
            return None
        if out is None:
            fd, out = tempfile.mkstemp(prefix="flippergotchi-", suffix=".hc22000")
            os.close(fd)
        proc = subprocess.run(
            [hcx, "-o", out, path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=60,
        )
        if proc.returncode != 0:
            _safe_unlink(out)
            return None
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            _safe_unlink(out)
            return None
        return out
    except Exception:  # noqa: BLE001 - never raise out of conversion
        log.debug("to_hc22000 failed", exc_info=True)
        return None


# --------------------------------------------------------------------------- #
# hcxpcapngtool path
# --------------------------------------------------------------------------- #
def _analyze_with_hcx(path: str, info: CaptureInfo) -> bool:
    """Populate *info* from hcxpcapngtool's ``--info`` summary (stderr).

    Returns True if hcx produced something useful. NEEDS ON-HARDWARE VALIDATION:
    hcxpcapngtool's summary wording varies by version, so we also cross-check by
    actually converting and inspecting the .hc22000 lines (WPA*01 = PMKID,
    WPA*02 = EAPOL), which is version-stable.
    """
    hcx = shutil.which("hcxpcapngtool")
    if not hcx:
        return False

    tmpdir = tempfile.mkdtemp(prefix="flippergotchi-hcx-")
    hc = os.path.join(tmpdir, "out.hc22000")
    try:
        proc = subprocess.run(
            [hcx, "--info=stdout", "-o", hc, path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=60,
        )
        text = (proc.stdout or b"").decode("utf-8", "replace")

        # The version-stable signal: inspect the converted hashlines.
        if os.path.exists(hc) and os.path.getsize(hc) > 0:
            _classify_hc22000(hc, info)

        # Pull ESSID/BSSID hints from the human summary, best-effort.
        for line in text.splitlines():
            low = line.lower()
            if "pmkid" in low and any(c.isdigit() for c in line):
                # "PMKID(s)............: 1" style line implies a PMKID present.
                if _trailing_count(line) > 0:
                    info.contains_pmkid = True

        info.tool = "hcxpcapngtool"
        return info.contains_pmkid or bool(info.eapol_messages) or bool(info.bssids)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _classify_hc22000(hc_path: str, info: CaptureInfo) -> None:
    """Read a .hc22000 file and fill PMKID/EAPOL + bssid/essid.

    Line shape: ``WPA*TT*MIC*MAC_AP*MAC_STA*ESSID_hex*...`` where TT is 01 for
    PMKID and 02 for EAPOL (the MIC-bearing handshake).
    """
    try:
        with open(hc_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.strip().split("*")
                if len(parts) < 6 or parts[0] != "WPA":
                    continue
                ttype = parts[1]
                if ttype == "01":
                    info.contains_pmkid = True
                    # PMKID still implies we *have* the AP; treat as M1-ish data
                    # but don't fake a 4-way -- is_crackable already covers it.
                elif ttype == "02":
                    # A converted EAPOL hashline means a MIC-bearing message pair
                    # was found -> at least M1+M2 worth of data.
                    info.eapol_messages.update({1, 2})
                mac_ap = parts[3]
                essid_hex = parts[5]
                bssid = _fmt_mac(mac_ap)
                if bssid and bssid not in info.bssids:
                    info.bssids.append(bssid)
                essid = _hex_to_str(essid_hex)
                if essid and essid not in info.essids:
                    info.essids.append(essid)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# pure-python pcap/pcapng fallback
# --------------------------------------------------------------------------- #
def _analyze_with_python(path: str, info: CaptureInfo) -> None:
    info.tool = "python"
    with open(path, "rb") as fh:
        head = fh.read(4)
        if len(head) < 4:
            return
        magic = struct.unpack(">I", head)[0]
        rest = fh.read()
    if magic == _PCAPNG_MAGIC:
        _walk_pcapng(head + rest, info)
    else:
        _walk_pcap(head + rest, info)


def _walk_pcap(data: bytes, info: CaptureInfo) -> None:
    if len(data) < 24:
        return
    # Read the 4 magic bytes big-endian: a value of 0xA1B2C3D4 means the file
    # is *big*-endian; the byte-swapped 0xD4C3B2A1 means little-endian.
    magic = struct.unpack(">I", data[:4])[0]
    if magic in (_PCAP_MAGIC_LE, _PCAP_MAGIC_NS_LE):
        endian = ">"
    elif magic in (_PCAP_MAGIC_BE, _PCAP_MAGIC_NS_BE):
        endian = "<"
    else:
        return
    linktype = struct.unpack(endian + "I", data[20:24])[0]
    off = 24
    n = len(data)
    while off + 16 <= n:
        _ts1, _ts2, caplen, _origlen = struct.unpack(endian + "IIII", data[off:off + 16])
        off += 16
        if caplen == 0 or caplen > _MAX_REC or off + caplen > n:
            break
        frame = data[off:off + caplen]
        off += caplen
        _inspect_frame(linktype, frame, info)


def _walk_pcapng(data: bytes, info: CaptureInfo) -> None:
    """Walk pcapng blocks. We track the link type from Interface Description
    Blocks and inspect Enhanced/Simple Packet Blocks."""
    off = 0
    n = len(data)
    endian = "<"          # refined from the Section Header Block byte-order magic
    linktype = LINKTYPE_ETHERNET
    while off + 12 <= n:
        # Block: type(4) total_len(4) body... total_len(4)
        btype = struct.unpack("<I", data[off:off + 4])[0]
        # The Section Header Block carries the byte-order magic; use it.
        if btype == _PCAPNG_MAGIC:
            if off + 12 > n:
                break
            bom = struct.unpack("<I", data[off + 8:off + 12])[0]
            endian = "<" if bom == 0x1A2B3C4D else ">"
        total_len = struct.unpack(endian + "I", data[off + 4:off + 8])[0]
        if total_len < 12 or off + total_len > n:
            break
        body = data[off + 8:off + total_len - 4]
        bt = struct.unpack(endian + "I", data[off:off + 4])[0]
        if bt == 0x00000001:        # Interface Description Block
            if len(body) >= 2:
                linktype = struct.unpack(endian + "H", body[0:2])[0]
        elif bt == 0x00000006:      # Enhanced Packet Block
            if len(body) >= 20:
                caplen = struct.unpack(endian + "I", body[12:16])[0]
                frame = body[20:20 + caplen]
                _inspect_frame(linktype, frame, info)
        elif bt == 0x00000003:      # Simple Packet Block
            frame = body[4:]
            _inspect_frame(linktype, frame, info)
        off += total_len


def _inspect_frame(linktype: int, frame: bytes, info: CaptureInfo) -> None:
    """Peel link-layer headers down to an EAPOL payload and classify it."""
    try:
        if linktype == LINKTYPE_ETHERNET:
            _inspect_ethernet(frame, info)
        elif linktype in (LINKTYPE_IEEE802_11, LINKTYPE_IEEE802_11_RADIOTAP,
                          LINKTYPE_PRISM, LINKTYPE_PPI):
            _inspect_dot11(linktype, frame, info)
        else:
            # Unknown link type: scan for the EAPOL ethertype as a last resort.
            _scan_for_eapol(frame, info)
    except Exception:  # noqa: BLE001
        return


def _inspect_ethernet(frame: bytes, info: CaptureInfo) -> None:
    if len(frame) < 14:
        return
    dst = frame[0:6]
    src = frame[6:12]
    ethertype = struct.unpack(">H", frame[12:14])[0]
    if ethertype == _EAPOL_ETHERTYPE:
        _record_bssid(_fmt_mac_bytes(src), info)
        _record_bssid(_fmt_mac_bytes(dst), info)
        _classify_eapol(frame[14:], info)


def _inspect_dot11(linktype: int, frame: bytes, info: CaptureInfo) -> None:
    """Strip radiotap/prism/ppi, then a data-frame 802.11 header + LLC/SNAP,
    landing on the EAPOL payload."""
    body = frame
    if linktype == LINKTYPE_IEEE802_11_RADIOTAP:
        if len(body) < 4:
            return
        rt_len = struct.unpack("<H", body[2:4])[0]
        if rt_len <= 0 or rt_len > len(body):
            return
        body = body[rt_len:]
    elif linktype == LINKTYPE_PRISM:
        body = body[144:]          # prism header is a fixed 144 bytes
    elif linktype == LINKTYPE_PPI:
        if len(body) < 4:
            return
        ppi_len = struct.unpack("<H", body[2:4])[0]
        if ppi_len <= 0 or ppi_len > len(body):
            return
        body = body[ppi_len:]

    if len(body) < 24:
        return
    fc = struct.unpack("<H", body[0:2])[0]
    ftype = (fc >> 2) & 0x3
    if ftype != 2:                 # only Data frames carry EAPOL
        return
    subtype = (fc >> 4) & 0xF
    addr1 = body[4:10]
    addr2 = body[10:16]
    addr3 = body[16:22]
    hdr_len = 24
    if (fc >> 8) & 0x3 == 0x3:     # ToDS & FromDS -> 4-address header
        hdr_len += 6
    if subtype & 0x8:             # QoS Data -> +2 QoS control bytes
        hdr_len += 2
    if (fc >> 14) & 0x1:          # protected frame: never carries plain EAPOL
        return
    payload = body[hdr_len:]
    # LLC/SNAP: AA AA 03 00 00 00 <ethertype>
    if len(payload) >= 8 and payload[0:3] == b"\xaa\xaa\x03":
        ethertype = struct.unpack(">H", payload[6:8])[0]
        if ethertype == _EAPOL_ETHERTYPE:
            for mac in (addr1, addr2, addr3):
                _record_bssid(_fmt_mac_bytes(mac), info)
            _classify_eapol(payload[8:], info)


def _scan_for_eapol(frame: bytes, info: CaptureInfo) -> None:
    """Last-resort: find the 0x888e ethertype anywhere and classify what follows."""
    idx = frame.find(b"\x88\x8e")
    if idx >= 0:
        _classify_eapol(frame[idx + 2:], info)


def _classify_eapol(payload: bytes, info: CaptureInfo) -> None:
    """Given the bytes *after* the EAPOL ethertype, classify the 4-way message.

    EAPOL header: version(1) type(1) length(2). type 3 == EAPOL-Key.
    Key frame: descriptor(1) key_info(2) key_len(2) replay(8) nonce(32)...
    We classify M1..M4 from the key-info flags, mirroring how wpa_supplicant /
    hcxtools do it:
        M1: Pairwise + ACK,            !MIC, !Install, !Secure
        M2: Pairwise + MIC,            !ACK,  !Secure   (and key-data present)
        M3: Pairwise + ACK + MIC + Install + Secure
        M4: Pairwise + MIC + Secure,   !ACK,  !Install
    PMKID lives in M1's key-data (RSN PMKID KDE), which hcx handles; here we
    only flag PMKID if we clearly see the KDE OUI in M1 key-data.
    """
    if len(payload) < 4:
        return
    etype = payload[1]
    if etype != 3:                 # not EAPOL-Key
        return
    body = payload[4:]
    if len(body) < 3:
        return
    key_info = struct.unpack(">H", body[1:3])[0]

    pairwise = bool(key_info & 0x0008)
    install = bool(key_info & 0x0040)
    ack = bool(key_info & 0x0080)
    mic = bool(key_info & 0x0100)
    secure = bool(key_info & 0x0200)

    if not pairwise:
        return                     # group-key handshake -> not our 4-way

    msg = 0
    if ack and not mic and not install and not secure:
        msg = 1
    elif mic and not ack and install and secure:
        msg = 4
    elif mic and ack and install and secure:
        msg = 3
    elif mic and not ack and not install:
        msg = 2

    if msg:
        info.eapol_messages.add(msg)

    # PMKID detection: M1 with key-data containing the RSN PMKID KDE.
    # Fixed key header is 93 bytes: desc(1) key_info(2) key_len(2) replay(8)
    # nonce(32) iv(16) rsc(8) id(8) mic(16); key_data_len(2) follows, then the
    # key-data. The RSN PMKID KDE starts dd 14 00 0f ac 04.
    if msg == 1 and len(body) >= 95:
        key_data_len = struct.unpack(">H", body[93:95])[0]
        key_data = body[95:95 + key_data_len]
        if b"\x00\x0f\xac\x04" in key_data and b"\xdd" in key_data:
            info.contains_pmkid = True


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _record_bssid(mac: str, info: CaptureInfo) -> None:
    if mac and mac not in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00") \
            and mac not in info.bssids:
        info.bssids.append(mac)


def _fmt_mac_bytes(b: bytes) -> str:
    if len(b) != 6:
        return ""
    return ":".join(f"{x:02x}" for x in b)


def _fmt_mac(hexstr: str) -> str:
    try:
        b = bytes.fromhex(hexstr)
        return _fmt_mac_bytes(b)
    except (ValueError, TypeError):
        return ""


def _hex_to_str(hexstr: str) -> str:
    try:
        return bytes.fromhex(hexstr).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return ""


def _trailing_count(line: str) -> int:
    tail = line.rstrip().split()[-1] if line.strip() else ""
    tail = tail.strip(".:")
    try:
        return int(tail)
    except ValueError:
        return 0


def _safe_unlink(p: str) -> None:
    try:
        os.unlink(p)
    except OSError:
        pass
