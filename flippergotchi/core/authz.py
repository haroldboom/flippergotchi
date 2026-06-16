"""Authorization scope guard -- the single source of truth for "may I actively
touch this network?".

Flippergotchi's hard rule: *collecting/scanning is always fine, but every ACTIVE
RF action (deauth / handshake capture / crack) is only permitted against networks
you OWN or are explicitly cleared to test.* This module centralises that decision
so the capture backend (:mod:`core.wifi.capture`) and the crack gate
(:mod:`game.battle`) agree on exactly one definition of "in scope".

Two ways a target lands in scope:

1. It matches ``cfg.home_networks`` -- a list of SSID/BSSID substrings (your
   "dojo"), matched case-insensitively. This mirrors ``battle.is_authorized``.
2. It appears in an explicit BSSID/SSID allowlist file (one entry per line,
   ``#`` comments) at ``cfg.allowlist_path`` (default
   ``~/.flippergotchi/allowlist.txt``).

Deny by default: an empty scope authorises nothing. Defensive throughout --
a string where a list was expected, ``None``, ints, a missing/unreadable file:
all fold into "denied", never an exception.

:class:`Authorizer` wraps this with the callable form the capture backend wants
(``is_authorized(bssid, ssid) -> bool``) plus :meth:`Authorizer.require`, which
makes the allow/deny decision for a named action AND appends a JSON audit line
to ``cfg.audit_log`` (default ``~/.flippergotchi/audit.log``) for every active
action -- permitted or refused -- so there is always a tamper-evident record of
what the tool was asked to do.

Config fields read (all via getattr, defaults shown):
    home_networks   list  []                              -- your dojo (ssid/bssid substrings)
    allowlist_path  str   ~/.flippergotchi/allowlist.txt  -- explicit BSSID/SSID allowlist
    audit_log       str   ~/.flippergotchi/audit.log      -- JSONL audit trail
"""
from __future__ import annotations

import json
import logging
import os
import time

log = logging.getLogger(__name__)

DEFAULT_ALLOWLIST = "~/.flippergotchi/allowlist.txt"
DEFAULT_AUDIT_LOG = "~/.flippergotchi/audit.log"

# Active RF actions that MUST be authorized + audited.
ACTIVE_ACTIONS = ("deauth", "capture", "crack")


def _as_needles(home) -> list:
    """Normalise cfg.home_networks into a lowercase list of non-empty needles.

    Defensive: a bare string is wrapped (never iterated char-by-char), None /
    other scalars become an empty list, and falsy entries are dropped.
    """
    if not home:
        return []
    if isinstance(home, str):
        home = [home]
    try:
        items = list(home)
    except TypeError:               # not iterable -> nothing usable
        return []
    return [str(n).strip().lower() for n in items if n is not None and str(n).strip()]


def load_allowlist(path) -> list:
    """Read an allowlist file into a list of lowercase entries.

    One BSSID/SSID per line; blank lines and ``#`` comments (including inline)
    are ignored. Returns [] on a missing/unreadable file -- never raises.
    """
    if not path:
        return []
    p = os.path.expanduser(str(path))
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as fh:
            raw = fh.read()
    except OSError:
        return []
    out: list = []
    for line in raw.splitlines():
        entry = line.split("#", 1)[0].strip().lower()
        if entry:
            out.append(entry)
    return out


def in_scope(bssid, ssid, cfg) -> bool:
    """True if actively touching (bssid, ssid) is authorised.

    A target is in scope when its BSSID or SSID matches any ``cfg.home_networks``
    needle OR any entry in the allowlist file, by case-insensitive substring.
    Deny by default: empty scope (no home networks, no allowlist) => False.
    Never raises on weird input.
    """
    hay = f"{'' if ssid is None else ssid} {'' if bssid is None else bssid}".lower()
    if not hay.strip():
        return False

    needles = _as_needles(getattr(cfg, "home_networks", []))
    needles += load_allowlist(getattr(cfg, "allowlist_path", DEFAULT_ALLOWLIST))
    if not needles:                 # empty scope -> deny by default
        return False
    return any(n in hay for n in needles)


class Authorizer:
    """Stateful scope guard bound to a Config.

    Use :meth:`is_authorized` as the ``callable(bssid, ssid) -> bool`` gate the
    capture backend expects, or :meth:`require` for an audited allow/deny on a
    named active action.
    """

    def __init__(self, cfg, clock=None):
        self.cfg = cfg
        # Injectable clock for deterministic tests; defaults to wall time.
        self._clock = clock or (lambda: time.strftime("%Y-%m-%dT%H:%M:%S%z"))

    # -- gate -------------------------------------------------------------
    def is_authorized(self, bssid, ssid: str = "") -> bool:
        """Pure scope check (no audit). Safe to hand to a capture backend."""
        try:
            return in_scope(bssid, ssid, self.cfg)
        except Exception as exc:    # noqa: BLE001 - a broken gate fails CLOSED
            log.warning("authz check raised (%s); treating as DENIED", exc)
            return False

    # -- audited decision -------------------------------------------------
    def require(self, action, bssid, ssid: str = ""):
        """Decide + audit-log an active action; return ``(allowed, reason)``.

        ``allowed`` is True only when the target is in scope. Every call -- allow
        or deny -- appends one JSON line to the audit log. Never raises; if the
        log can't be written we log a warning and carry on with the decision.
        """
        allowed = self.is_authorized(bssid, ssid)
        if allowed:
            reason = "in authorized scope (home_networks/allowlist)"
        else:
            reason = "target not in authorized scope (home_networks/allowlist)"
        self._audit(action, bssid, ssid, allowed, reason)
        return allowed, reason

    # -- audit ------------------------------------------------------------
    def _audit(self, action, bssid, ssid, allowed: bool, reason: str) -> None:
        path = getattr(self.cfg, "audit_log", DEFAULT_AUDIT_LOG)
        if not path:
            return
        try:
            ts = self._clock()
        except Exception:           # noqa: BLE001 - never let the clock break audit
            ts = ""
        record = {
            "ts": ts,
            "action": str(action),
            "bssid": "" if bssid is None else str(bssid),
            "ssid": "" if ssid is None else str(ssid),
            "allowed": bool(allowed),
            "reason": str(reason),
        }
        line = json.dumps(record, ensure_ascii=False)
        p = os.path.expanduser(str(path))
        try:
            d = os.path.dirname(p)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:
            # Audit is best-effort: a read-only FS must not block the decision.
            log.warning("could not write audit log %s (%s); continuing", p, exc)
