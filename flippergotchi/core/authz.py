"""Authorization audit + an optional convenience scope check.

The game's authorization is the on-screen **WARNING the player agrees to** (the
`battle` command / on-the-fly consent), NOT a network allow-list -- you don't
edit a config file to play. This module just provides:

  * :func:`in_scope` -- an OPTIONAL convenience used by the standalone `capture`
    and `cloud` commands: does (bssid, ssid) match ``cfg.home_networks``?
    (deny-by-default when empty; pass ``--authorized`` to override there);
  * :class:`Authorizer` -- the callable form plus :meth:`Authorizer.require`,
    which appends a JSON **audit** line to ``cfg.audit_log`` for every active
    action (permitted or refused), so there's a tamper-evident record.

Defensive throughout: a string where a list was expected, ``None``, ints all
fold into "denied", never an exception.

Config fields read (all via getattr, defaults shown):
    home_networks   list  []                          -- optional convenience scope
    audit_log       str   ~/.flippergotchi/audit.log  -- JSONL audit trail
"""
from __future__ import annotations

import json
import logging
import os
import time

log = logging.getLogger(__name__)

DEFAULT_AUDIT_LOG = "~/.flippergotchi/audit.log"

# Active RF actions that MUST be authorized + audited.
ACTIVE_ACTIONS = ("deauth", "capture", "crack", "ble_enum")


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


def in_scope(bssid, ssid, cfg) -> bool:
    """True if actively touching (bssid, ssid) matches ``cfg.home_networks``.

    Used only by the standalone `capture` / `cloud` commands as an optional
    convenience; the game's authorization is the on-screen WARNING (consent),
    not a network list. Deny by default when home_networks is empty. Never
    raises on weird input.
    """
    hay = f"{'' if ssid is None else ssid} {'' if bssid is None else bssid}".lower()
    if not hay.strip():
        return False

    needles = _as_needles(getattr(cfg, "home_networks", []))
    if not needles:                 # empty -> deny by default
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
            reason = "in scope (home_networks)"
        else:
            reason = "target not in scope (home_networks)"
        self._audit(action, bssid, ssid, allowed, reason)
        return allowed, reason

    def audit(self, action, bssid, ssid: str = "", allowed: bool = True,
              reason: str = "") -> None:
        """Record one audit line for an action the CALLER already decided.

        Unlike :meth:`require` (which re-derives the decision from scope), this
        logs the outcome the caller actually took -- so a manual-mode override
        that transmits is recorded as ``allowed=True`` rather than diverging
        from a scope check. Used by the autonomous agent loop, whose deauth /
        crack / active-BLE decisions would otherwise leave no trail."""
        self._audit(action, bssid, ssid, bool(allowed), str(reason))

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
