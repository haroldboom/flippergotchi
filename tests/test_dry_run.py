"""On-hardware dry-run mode: drive the real capture/crack paths but suppress the
two irreversible/expensive actions -- deauth INJECTION and running hashcat.

These are hermetic (no radio, no hashcat): they assert that under cfg.dry_run the
crack pipeline validates + builds the command but never executes it, and the
capture path stays passive even against an authorized target.
"""
from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import test_handshake as T  # reuse its tiny binary pcap fixture builders

from flippergotchi.config import Config
from flippergotchi.core.wifi import capture as capture_mod
from flippergotchi.game.cracking import LocalCracker


def _monster(name="HomeNet", defense=40):
    return types.SimpleNamespace(name=name, defense=defense)


def test_dry_run_crack_builds_command_without_running_hashcat(tmp_path, monkeypatch):
    cap = tmp_path / "hs.pcap"
    T._write(str(cap), [T._m1(), T._m2(), T._m3()])  # a usable 4-way
    wl = tmp_path / "wl.txt"
    wl.write_text("password\n")

    cfg = Config()
    cfg.dry_run = True
    cfg.wordlists = [str(wl)]

    # if hashcat is ever invoked, fail loudly
    import flippergotchi.game.cracking as cracking_mod
    monkeypatch.setattr(cracking_mod.subprocess, "run",
                        lambda *a, **k: pytest.fail("hashcat must NOT run in dry-run"))

    res = LocalCracker(cfg).crack(_monster(), str(cap))
    assert res.result == "dry-run"
    assert res.mode == "handshake"
    assert "would run: hashcat -m 22000" in res.detail
    assert str(wl) in res.detail


def test_dry_run_crack_reports_uncrackable_capture(tmp_path):
    cap = tmp_path / "junk.pcap"
    T._write(str(cap), [T._m1()])  # only M1 -> not a complete handshake, no PMKID
    cfg = Config()
    cfg.dry_run = True
    res = LocalCracker(cfg).crack(_monster(), str(cap))
    assert res.result == "dry-run"
    assert "would NOT crack" in res.detail


def test_dry_run_crack_with_no_capture_is_honest():
    cfg = Config()
    cfg.dry_run = True
    res = LocalCracker(cfg).crack(_monster(), None)
    assert res.result == "dry-run"
    assert "no capture file" in res.detail


def test_dry_run_capture_stays_passive_even_when_authorized(tmp_path, monkeypatch):
    """With dry_run on, an AUTHORIZED target must still go out passively: the
    hcxdumptool invocation carries the --disable_* (no-transmit) flags."""
    cfg = Config()
    cfg.dry_run = True
    cfg.capture_dir = str(tmp_path)

    calls = {}
    monkeypatch.setattr(capture_mod, "have_hcxdumptool", lambda: True)
    monkeypatch.setattr(capture_mod.shutil, "which", lambda name: "/usr/bin/" + name)

    def _fake_run(args, **kwargs):
        calls["args"] = args
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(capture_mod.subprocess, "run", _fake_run)

    cap = capture_mod.HandshakeCapture(cfg, "mon0", is_authorized=lambda b, s: True)
    # no output file is created by the fake run -> capture() returns None, but we
    # only care that the planned hcxdumptool args were passive.
    cap.capture("AA:BB:CC:00:11:22", "HomeNet", timeout=1)
    args = calls.get("args", [])
    assert "--disable_deauthentication" in args
    assert "--disable_disassociation" in args


def test_dry_run_capture_sends_deauth_when_authorized_and_not_dry(tmp_path, monkeypatch):
    """Control: without dry_run, an authorized target is allowed to transmit
    (no --disable_* flags), proving the dry-run flag is what suppresses it."""
    cfg = Config()
    cfg.dry_run = False
    cfg.capture_dir = str(tmp_path)

    calls = {}
    monkeypatch.setattr(capture_mod, "have_hcxdumptool", lambda: True)
    monkeypatch.setattr(capture_mod.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(capture_mod.subprocess, "run",
                        lambda args, **k: calls.setdefault("args", args))

    cap = capture_mod.HandshakeCapture(cfg, "mon0", is_authorized=lambda b, s: True)
    cap.capture("AA:BB:CC:00:11:22", "HomeNet", timeout=1)
    args = calls.get("args", [])
    assert "--disable_deauthentication" not in args


def test_cmd_scan_and_capture_run_in_sim(tmp_path, capsys):
    from flippergotchi import commands
    cfg = Config()
    cfg.simulate = True
    cfg.dry_run = True
    commands.cmd_scan(cfg, rounds=4)
    assert "SCAN" in capsys.readouterr().out
    commands.cmd_capture(cfg, "AA:BB:CC:00:11:22", authorized=False)
    out = capsys.readouterr().out
    assert "CAPTURE" in out and "DRY-RUN" in out
