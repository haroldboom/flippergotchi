"""``flippergotchi doctor`` -- a friendly preflight readout.

Turns :func:`core.preflight.preflight` into a human checklist with OK / MISSING /
WARN markers grouped by concern (Tools, Privileges, Interface, Wordlist, Scope),
then a one-line capability summary ("you can: [passive scan] [capture] [crack]")
derived from what's actually present, plus actionable hints for whatever's
missing.

:func:`report` is pure string-building (it only CALLS preflight),
so it's fully testable without hardware. :func:`run` just prints it -- the CLI
``doctor`` subcommand is wired up elsewhere.
"""
from __future__ import annotations

from ..core import preflight as _preflight
from ..core.authz import _as_needles

# Markers (ASCII so they render on the Flipper's tiny terminal too).
OK = "[ OK ]"
MISS = "[MISS]"
WARN = "[WARN]"

# Tools that are essential vs. merely nice-to-have, for marker severity.
_ESSENTIAL_TOOLS = {"hcxdumptool", "hcxpcapngtool", "hashcat", "iw", "ip"}


def _scope(cfg) -> dict:
    """The optional convenience scope (home_networks). The game's real gate is
    the on-screen consent warning, not a network list."""
    home = _as_needles(getattr(cfg, "home_networks", []))
    return {"home": home, "any": bool(home)}


def report(cfg) -> str:
    """Build the multi-line doctor report for ``cfg`` (pure string building)."""
    pf = _preflight.preflight(cfg)
    scope = _scope(cfg)
    lines: list = []

    lines.append("Flippergotchi doctor -- preflight check")
    lines.append("=" * 40)

    # -- Tools ------------------------------------------------------------
    lines.append("")
    lines.append("Tools:")
    tools = pf["tools"]
    for name in _preflight.TOOLS:
        present = tools.get(name, False)
        if present:
            mark = OK
        else:
            mark = MISS if name in _ESSENTIAL_TOOLS else WARN
        line = f"  {mark} {name}"
        if not present:
            line += f"   (install {name})"
        lines.append(line)

    # -- Privileges -------------------------------------------------------
    priv = pf["privileges"]
    lines.append("")
    lines.append("Privileges:")
    lines.append(f"  {OK if priv['is_root'] else WARN} root (euid 0)")
    lines.append(
        f"  {OK if priv['has_cap_net_admin'] else WARN} CAP_NET_ADMIN")
    if not priv["can_monitor"]:
        lines.append("  hint: run as root (sudo) for monitor mode + injection")

    # -- Interface --------------------------------------------------------
    iface = pf["interface"]
    lines.append("")
    lines.append("Interface:")
    if iface["exists"]:
        lines.append(f"  {OK} {iface['name']} present")
        mark = OK if iface["wireless"] else WARN
        lines.append(f"  {mark} {iface['name']} is wireless")
        if not iface["wireless"]:
            lines.append("  hint: this iface has no phy80211; set cfg.interface "
                         "to your WiFi device")
    else:
        lines.append(f"  {MISS} {iface['name']} not found")
        lines.append("  hint: set cfg.interface to your monitor-capable WiFi iface")

    reg = pf["regdomain"]
    if reg["available"]:
        lines.append(f"  {OK} regdomain {reg['country']}")
    else:
        lines.append(f"  {WARN} regdomain unknown (iw reg get) -- channels may "
                     "be limited")

    # -- Wordlist ---------------------------------------------------------
    wl = pf["wordlist"]
    lines.append("")
    lines.append("Wordlist:")
    if wl["exists"]:
        mb = wl["size"] / (1024 * 1024)
        lines.append(f"  {OK} {wl['path']} ({mb:.1f} MiB)")
    else:
        lines.append(f"  {MISS} {wl['path']} not found")
        lines.append("  hint: install a wordlist (e.g. rockyou.txt) or set "
                     "cfg.wordlist")

    # -- Authorization ----------------------------------------------------
    lines.append("")
    lines.append("Authorization:")
    lines.append(f"  {OK} on-screen consent -- you agree to the WARNING once "
                 "(in-game, no config)")
    if scope["home"]:
        lines.append(f"  {OK} home_networks hint: {', '.join(scope['home'])}")

    # -- Capability summary ----------------------------------------------
    caps = _capabilities(pf, scope)
    lines.append("")
    lines.append("You can: " + " ".join(f"[{c}]" for c in caps))

    return "\n".join(lines)


def _capabilities(pf: dict, scope: dict) -> list:
    """Derive the [passive scan] [capture] [crack] capability list."""
    tools = pf["tools"]
    priv = pf["privileges"]
    iface = pf["interface"]
    caps: list = []

    # Passive scan: an iface + a way to scan it (iw or airmon/bettercap).
    if iface["exists"] and (tools.get("iw") or tools.get("bettercap")):
        caps.append("passive scan")

    # Capture: privileged + a wireless iface + a capture tool. Active deauth is
    # enabled once you agree to the on-screen consent (no scope list).
    if (priv["can_monitor"] and iface["exists"]
            and (tools.get("hcxdumptool") or tools.get("bettercap"))):
        caps.append("capture")

    # Crack: hashcat + a wordlist present.
    if tools.get("hashcat") and pf["wordlist"]["exists"]:
        caps.append("crack")

    return caps or ["nothing yet -- see hints above"]


def run(cfg) -> None:
    """Print the doctor report."""
    print(report(cfg))
