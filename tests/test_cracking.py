"""Crack-pipeline checks: fake hashcat via monkeypatch, assert CrackResult and
that battle() preserves its contract (refuses out-of-scope, tames BLE)."""
from __future__ import annotations

import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.game import battle, cracking, monsters
from flippergotchi.game.cracking import CrackResult, LocalCracker


def _wifi(ssid="Mine", enc="wpa2"):
    return monsters.from_ap({"ssid": ssid, "bssid": "AA:11:22:33:44:55",
                             "encryption": enc, "kind": "handshake"})


def _capture(tmp_path, name="cap.pcap"):
    p = tmp_path / name
    p.write_bytes(b"\xa1\xb2\xc3\xd4" + b"\x00" * 200)   # plausible pcap-ish blob
    return str(p)


# --------------------------------------------------------------------------- #
# CrackResult shape
# --------------------------------------------------------------------------- #
def test_crackresult_to_dict_shape():
    r = CrackResult(result="cracked", via="local hashcat", key="pw",
                    mode="handshake", detail="recovered via handshake")
    d = r.to_dict()
    assert d["result"] == "cracked"
    assert d["via"] == "local hashcat"
    assert d["key"] == "pw"
    assert d["mode"] == "handshake"
    assert d["note"] == "recovered via handshake"


# --------------------------------------------------------------------------- #
# sim fallback (no tools)
# --------------------------------------------------------------------------- #
def test_sim_when_no_hashcat(monkeypatch):
    monkeypatch.setattr(cracking.shutil, "which", lambda *_a, **_k: None)
    cfg = Config()
    c = LocalCracker(cfg)
    assert c.sim is True
    m = _wifi(enc="open")            # defense 0 => near-certain sim crack
    random.seed(1)
    res = c.crack(m, None)
    assert isinstance(res, CrackResult)
    assert res.mode == "sim"
    assert res.result in ("cracked", "failed")


def test_sim_force_via_config():
    cfg = Config(simulate=True)
    c = LocalCracker(cfg)
    assert c.sim is True


# --------------------------------------------------------------------------- #
# real path with faked hashcat
# --------------------------------------------------------------------------- #
def _patch_tools(monkeypatch, wordlist_path):
    """Pretend hashcat + hcxpcapngtool exist and a wordlist file is present."""
    monkeypatch.setattr(cracking.shutil, "which",
                        lambda name, *a, **k: f"/usr/bin/{name}")


def test_real_crack_success(monkeypatch, tmp_path):
    wl = tmp_path / "rockyou.txt"
    wl.write_text("password123\n")
    cap = _capture(tmp_path)

    monkeypatch.setattr(cracking.shutil, "which",
                        lambda name, *a, **k: f"/usr/bin/{name}")

    # validator says crackable handshake
    monkeypatch.setattr(cracking.hs, "analyze_capture",
                        lambda p: _fake_info(handshake=True))
    # converter yields a fake .hc22000
    def _to_hc(path, out=None):
        with open(out, "w") as fh:
            fh.write("WPA*02*deadbeef*aa1122334455*...\n")
        return out
    monkeypatch.setattr(cracking.hs, "to_hc22000", _to_hc)

    # hashcat "runs" and we drop a found line into the outfile
    def _fake_run(cmd, **kw):
        outfile = cmd[cmd.index("-o") + 1]
        with open(outfile, "w") as fh:
            fh.write("hash:aa:bb:Mine:password123\n")
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(cracking.subprocess, "run", _fake_run)

    cfg = Config()
    cfg.wordlist = str(wl)
    res = LocalCracker(cfg).crack(_wifi(), cap)
    assert res.result == "cracked"
    assert res.key == "password123"
    assert res.via == "local hashcat"
    assert res.mode == "handshake"


def test_real_crack_failure_exhausts(monkeypatch, tmp_path):
    wl = tmp_path / "rockyou.txt"
    wl.write_text("nope\n")
    cap = _capture(tmp_path)

    monkeypatch.setattr(cracking.shutil, "which",
                        lambda name, *a, **k: f"/usr/bin/{name}")
    monkeypatch.setattr(cracking.hs, "analyze_capture",
                        lambda p: _fake_info(pmkid=True))
    monkeypatch.setattr(cracking.hs, "to_hc22000",
                        lambda path, out=None: _touch(out))

    # hashcat runs but recovers nothing (empty outfile)
    monkeypatch.setattr(cracking.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1))

    cfg = Config()
    cfg.wordlist = str(wl)
    res = LocalCracker(cfg).crack(_wifi(), cap)
    assert res.result == "failed"
    assert res.mode == "pmkid"          # pmkid-only capture recorded as pmkid mode


def test_real_crack_invalid_capture_no_hashcat_run(monkeypatch, tmp_path):
    cap = _capture(tmp_path)
    wl = tmp_path / "wl.txt"
    wl.write_text("x\n")

    monkeypatch.setattr(cracking.shutil, "which",
                        lambda name, *a, **k: f"/usr/bin/{name}")
    # validator says nothing crackable
    monkeypatch.setattr(cracking.hs, "analyze_capture",
                        lambda p: _fake_info())

    ran = {"hashcat": False}
    def _boom(cmd, **kw):
        ran["hashcat"] = True
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(cracking.subprocess, "run", _boom)

    cfg = Config()
    cfg.wordlist = str(wl)
    res = LocalCracker(cfg).crack(_wifi(), cap)
    assert res.result == "failed"
    assert ran["hashcat"] is False      # never wasted time on a junk capture


def test_multiple_wordlists_passed(monkeypatch, tmp_path):
    wl1 = tmp_path / "a.txt"; wl1.write_text("a\n")
    wl2 = tmp_path / "b.txt"; wl2.write_text("b\n")
    cap = _capture(tmp_path)

    monkeypatch.setattr(cracking.shutil, "which",
                        lambda name, *a, **k: f"/usr/bin/{name}")
    monkeypatch.setattr(cracking.hs, "analyze_capture",
                        lambda p: _fake_info(handshake=True))
    monkeypatch.setattr(cracking.hs, "to_hc22000",
                        lambda path, out=None: _touch(out))

    seen = {}
    def _capture_cmd(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(cracking.subprocess, "run", _capture_cmd)

    cfg = Config()
    cfg.wordlists = [str(wl1), str(wl2)]
    LocalCracker(cfg).crack(_wifi(), cap)
    assert str(wl1) in seen["cmd"] and str(wl2) in seen["cmd"]


def test_rules_file_appended(monkeypatch, tmp_path):
    wl = tmp_path / "a.txt"; wl.write_text("a\n")
    rules = tmp_path / "best64.rule"; rules.write_text(":\n")
    cap = _capture(tmp_path)

    monkeypatch.setattr(cracking.shutil, "which",
                        lambda name, *a, **k: f"/usr/bin/{name}")
    monkeypatch.setattr(cracking.hs, "analyze_capture",
                        lambda p: _fake_info(handshake=True))
    monkeypatch.setattr(cracking.hs, "to_hc22000",
                        lambda path, out=None: _touch(out))

    seen = {}
    monkeypatch.setattr(cracking.subprocess, "run",
                        lambda cmd, **kw: seen.update(cmd=cmd) or
                        subprocess.CompletedProcess(cmd, 0))

    cfg = Config()
    cfg.wordlist = str(wl)
    cfg.hashcat_rules = str(rules)
    LocalCracker(cfg).crack(_wifi(), cap)
    assert "-r" in seen["cmd"] and str(rules) in seen["cmd"]


def test_timeout_returns_failed(monkeypatch, tmp_path):
    wl = tmp_path / "a.txt"; wl.write_text("a\n")
    cap = _capture(tmp_path)

    monkeypatch.setattr(cracking.shutil, "which",
                        lambda name, *a, **k: f"/usr/bin/{name}")
    monkeypatch.setattr(cracking.hs, "analyze_capture",
                        lambda p: _fake_info(handshake=True))
    monkeypatch.setattr(cracking.hs, "to_hc22000",
                        lambda path, out=None: _touch(out))

    def _timeout(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))
    monkeypatch.setattr(cracking.subprocess, "run", _timeout)

    cfg = Config()
    cfg.wordlist = str(wl)
    res = LocalCracker(cfg).crack(_wifi(), cap)
    assert res.result == "failed"
    assert "timed out" in res.detail


# --------------------------------------------------------------------------- #
# battle() contract preserved
# --------------------------------------------------------------------------- #
def test_battle_does_not_refuse_on_scope():
    # consent-based authorization: battle() never returns "refused"
    cfg = Config(simulate=True)
    m = _wifi(ssid="Stranger")
    r = battle.battle(m, cfg)
    assert r["result"] != "refused"
    assert "key" in r and "via" in r


def test_battle_ble_routes_to_ble_engine(monkeypatch):
    import flippergotchi.game.blebattle as bb
    monkeypatch.setattr(bb.random, "random", lambda: 0.0)   # sim crack lands
    cfg = Config(simulate=True)
    m = monsters.from_ble({"addr": "AA:BB:CC:DD:EE:01", "name": "Buds",
                           "device_class": "audio", "rssi": -60})
    r = battle.battle(m, cfg)
    assert r["result"] == "cracked" and m.defeated


def test_battle_cracks_when_authorized_sim():
    cfg = Config(simulate=True)
    cfg.home_networks = ["Mine"]
    m = _wifi(ssid="Mine", enc="open")
    random.seed(1)
    r = battle.battle(m, cfg, force_authorized=True)
    assert r["result"] == "cracked" and m.defeated and m.key


def test_battle_result_has_legacy_keys():
    cfg = Config(simulate=True)
    cfg.home_networks = ["Mine"]
    m = _wifi(ssid="Mine", enc="open")
    random.seed(2)
    r = battle.battle(m, cfg, force_authorized=True)
    assert set(["result", "via", "key"]) <= set(r.keys())


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _fake_info(pmkid=False, handshake=False):
    info = cracking.hs.CaptureInfo(path="x", exists=True, size=100)
    info.contains_pmkid = pmkid
    if handshake:
        info.eapol_messages = {1, 2}
    return info


def _touch(out):
    with open(out, "w") as fh:
        fh.write("WPA*02*x\n")
    return out


if __name__ == "__main__":
    print("run via pytest")
