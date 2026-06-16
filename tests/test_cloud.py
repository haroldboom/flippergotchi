"""Cloud cracking: real wpa-sec/onlinehashcrack upload + result retrieval.

All hermetic -- urllib is mocked, so no network is touched. Covers the multipart
encoder, dry-run/sim suppression, wpa-sec upload success/failure, result-potfile
parsing, and the `cloud results` command applying recovered keys to the dex.
"""
from __future__ import annotations

import dataclasses
import types

import pytest

from flippergotchi.config import Config
from flippergotchi import commands
from flippergotchi.game import cracking as cracking_mod
from flippergotchi.game.cracking import (
    CloudCracker, _encode_multipart, _fmt_mac, _parse_wpa_sec_potfile,
)
from flippergotchi.game.bestiary import Bestiary
from flippergotchi.game import monsters
from flippergotchi.game.ledger import Ledger


class _Resp:
    def __init__(self, data: bytes):
        self._d = data

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _mock_urlopen(monkeypatch, data: bytes, sink: dict | None = None):
    def _fake(req, timeout=None):
        if sink is not None:
            sink["req"] = req
        return _Resp(data)
    monkeypatch.setattr(cracking_mod.urllib.request, "urlopen", _fake)


def _monster(path=""):
    return types.SimpleNamespace(name="HomeNet", id="AA:BB:CC:00:11:22",
                                 capture_path=path)


# -- helpers ----------------------------------------------------------------
def test_fmt_mac_normalises():
    assert _fmt_mac("aabbcc001122") == "AA:BB:CC:00:11:22"
    assert _fmt_mac("AA:BB:CC:00:11:22") == "AA:BB:CC:00:11:22"
    assert _fmt_mac("nothex") == ""
    assert _fmt_mac("aabbcc") == ""  # too short


def test_parse_potfile():
    text = ("aabbcc001122:1122334455aa:HomeNet:hunter2\n"
            "\n"
            "ffeeddccbbaa:0011223344ff:Cafe:s3cret:with:colons\n"
            "garbage line\n")
    out = _parse_wpa_sec_potfile(text)
    assert out["AA:BB:CC:00:11:22"] == "hunter2"
    # PSK is the LAST field even if it contains colons
    assert out["FF:EE:DD:CC:BB:AA"] == "colons"


def test_multipart_encoder_shape():
    ctype, body = _encode_multipart("file", "/tmp/cap.pcapng", b"\x01\x02",
                                    extra_fields={"api_key": "k"})
    assert ctype.startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="cap.pcapng"' in body
    assert b'name="api_key"' in body
    assert body.rstrip().endswith(b"--")


# -- submit: suppression ----------------------------------------------------
def test_dry_run_submit_does_not_touch_network(monkeypatch, tmp_path):
    cap = tmp_path / "c.pcapng"
    cap.write_bytes(b"x")
    cfg = Config(); cfg.dry_run = True; cfg.wpa_sec_key = "k"
    monkeypatch.setattr(cracking_mod.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("dry-run must not upload"))
    res = CloudCracker(cfg).submit(_monster(), str(cap))
    assert res.result == "dry-run"
    assert "would upload" in res.detail


def test_sim_submit_is_simulated(monkeypatch):
    cfg = Config(); cfg.simulate = True
    monkeypatch.setattr(cracking_mod.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("sim must not upload"))
    res = CloudCracker(cfg).submit(_monster(), None)
    assert res.result == "submitted"
    assert "simulated" in res.detail


# -- submit: real wpa-sec ---------------------------------------------------
def test_wpa_sec_submit_success(monkeypatch, tmp_path):
    cap = tmp_path / "c.pcapng"
    cap.write_bytes(b"PCAPDATA")
    cfg = Config(); cfg.wpa_sec_key = "secret"
    sink: dict = {}
    _mock_urlopen(monkeypatch, b"OK\n", sink)
    res = CloudCracker(cfg).submit(_monster(), str(cap))
    assert res.result == "submitted" and res.via == "wpa-sec"
    req = sink["req"]
    assert req.method == "POST"
    assert "upload" in req.full_url
    assert req.headers.get("Cookie") == "key=secret"
    assert b"PCAPDATA" in req.data


def test_wpa_sec_submit_needs_key(tmp_path):
    cap = tmp_path / "c.pcapng"; cap.write_bytes(b"x")
    cfg = Config()  # no wpa_sec_key
    res = CloudCracker(cfg).submit(_monster(), str(cap))
    assert res.result == "failed" and "wpa_sec_key" in res.detail


def test_submit_no_file_fails():
    cfg = Config(); cfg.wpa_sec_key = "k"
    res = CloudCracker(cfg).submit(_monster(), "/nonexistent.pcapng")
    assert res.result == "failed" and "no capture" in res.detail


def test_submit_network_error_degrades(monkeypatch, tmp_path):
    cap = tmp_path / "c.pcapng"; cap.write_bytes(b"x")
    cfg = Config(); cfg.wpa_sec_key = "k"

    def _boom(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(cracking_mod.urllib.request, "urlopen", _boom)
    res = CloudCracker(cfg).submit(_monster(), str(cap))
    assert res.result == "failed" and "error" in res.detail.lower()


# -- fetch results ----------------------------------------------------------
def test_fetch_results_parses(monkeypatch):
    cfg = Config(); cfg.wpa_sec_key = "k"
    _mock_urlopen(monkeypatch, b"aabbcc001122:1122334455aa:HomeNet:letmein\n")
    out = CloudCracker(cfg).fetch_results()
    assert out == {"AA:BB:CC:00:11:22": "letmein"}


def test_fetch_results_empty_without_key():
    assert CloudCracker(Config()).fetch_results() == {}


# -- cmd_cloud results applies keys to the dex ------------------------------
def _tmp_cfg(tmp_path):
    cfg = Config()
    for f in dataclasses.fields(cfg):
        v = getattr(cfg, f.name)
        if isinstance(v, str) and v.startswith("~/.flippergotchi"):
            setattr(cfg, f.name, str(tmp_path / f.name))
    return cfg


def test_cmd_cloud_results_marks_monster_cracked(tmp_path, monkeypatch, capsys):
    cfg = _tmp_cfg(tmp_path)
    cfg.wpa_sec_key = "k"
    dex = Bestiary(cfg.bestiary_path)
    m = monsters.from_ap({"type": "ap", "bssid": "AA:BB:CC:00:11:22",
                          "ssid": "HomeNet", "encryption": "wpa2",
                          "band": "2.4GHz", "clients": 1, "signal": -50})
    m.captured = True
    dex.add(m)
    dex.save()
    monkeypatch.setattr(CloudCracker, "fetch_results",
                        lambda self: {"AA:BB:CC:00:11:22": "hunter2"})
    commands.cmd_cloud(cfg, "results", None)
    out = capsys.readouterr().out
    assert "cracked via cloud" in out and "hunter2" in out
    # persisted: the monster is now defeated with the key, logged as a win
    reloaded = Bestiary(cfg.bestiary_path).get("AA:BB:CC:00:11:22")
    assert reloaded.defeated and reloaded.key == "hunter2"
    assert Ledger(cfg.ledger_path).counts()["win"] == 1


def test_cmd_cloud_submit_refuses_out_of_scope(tmp_path, capsys):
    cfg = _tmp_cfg(tmp_path)
    cfg.cloud_enabled = True
    cfg.wpa_sec_key = "k"
    cap = tmp_path / "c.pcapng"; cap.write_bytes(b"x")
    dex = Bestiary(cfg.bestiary_path)
    m = monsters.from_ap({"type": "ap", "bssid": "AA:BB:CC:00:11:22",
                          "ssid": "StrangerNet", "encryption": "wpa2",
                          "band": "2.4GHz", "clients": 1, "signal": -50})
    m.captured = True
    m.capture_path = str(cap)
    dex.add(m)
    dex.save()
    commands.cmd_cloud(cfg, "submit", "StrangerNet", authorized=False)
    assert "refused" in capsys.readouterr().out
