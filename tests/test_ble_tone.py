"""BLE tone reconciliation.

The BLE system used to be framed as owning real people's devices (Fitbit /
glucose monitor / hearing aid / AirTag) and exfiltrating their health records,
location history and audio. That clashed with the game's consent-first,
catch-not-harm, "monsters you befriend" ethic. It has been re-skinned into
whimsical roaming "signal-sprites" you befriend/attune/soothe.

These tests assert the invasive framing is gone from every player-surfaced
string, the friendly signal-sprite flavor is present, and -- crucially -- that
the reskin changed only WORDS: the odds, rewards and consent/authz gates are
byte-for-byte the same behaviour as before.
"""
from __future__ import annotations

from flippergotchi.config import Config
from flippergotchi.game import monsters, blebattle, ble
from flippergotchi.view import blebattle_screen


# terms that must never appear in anything the player can read
_FORBIDDEN = (
    "glucose", "hearing aid", "health record", "audio intercept",
    "location history", "fitness data", "keystroke", "device profile",
    "beacon uuid", "raw gatt dump", "control token",
    "took control", "ltk recovered", "owned", "brute", "sniff",
    "re-pair", "gatt write", "downgrade", "knob", "exfil", "victim",
)

# whimsical flavor that should be present in the new surfaced strings
_EXPECTED = ("sprite", "befriend", "wandering spark", "listen", "hum", "friend")


def _ble(cls, addr="AA:BB:CC:00:11:22", connectable=True):
    return monsters.from_ble({"addr": addr, "name": cls, "device_class": cls,
                              "connectable": connectable, "rssi": -55})


def _roll(monkeypatch, value):
    monkeypatch.setattr(blebattle.random, "random", lambda: value)


def _surfaced_strings(monkeypatch):
    """Gather every text string a player could see across BLE code paths.

    Deliberately excludes the base64-encoded sprite bytes in the rendered HTML
    (random image data can contain any substring); the human-readable render
    template is included instead so real UI copy is still checked.
    """
    out: list[str] = []
    out += list(blebattle._LOOT.values())
    out += [lbl for (lbl, _uuid, _val) in blebattle._CONTROL.values()]
    out.append(blebattle._DEFAULT_CONTROL[0])
    out += list(blebattle_screen._PAIRING_LABEL.values())
    out += [txt for txt, _col in blebattle_screen._OUTCOME.values()]
    out.append(blebattle_screen._DOC)          # the render template copy
    # every outcome of every pairing type -> the full step log + result notes
    for cls, conn, roll in [("tracker", True, 0.0), ("tracker", True, 1.0),
                            ("wearable", True, 0.0), ("phone", False, 0.0),
                            ("phone", True, 0.5), ("phone", False, 0.9)]:
        _roll(monkeypatch, roll)
        m = _ble(cls, addr=f"AA:BB:CC:00:{cls[:2]}:00", connectable=conn)
        res = blebattle.battle_ble(m, Config(simulate=True))
        for label, detail in res["steps"]:
            out.append(label)
            out.append(detail)
        out.append(res.get("note", ""))
    return [s for s in out if s]


# -- invasive framing is gone -----------------------------------------------
def test_no_invasive_terms_in_surfaced_strings(monkeypatch):
    blob = "\n".join(_surfaced_strings(monkeypatch)).lower()
    for bad in _FORBIDDEN:
        assert bad not in blob, f"invasive term still surfaced: {bad!r}"


def test_no_invasive_loot_values():
    for loot in blebattle._LOOT.values():
        low = loot.lower()
        assert not any(b in low for b in _FORBIDDEN)


def test_friendly_flavor_present(monkeypatch):
    blob = "\n".join(_surfaced_strings(monkeypatch)).lower()
    for good in _EXPECTED:
        assert good in blob, f"expected friendly flavor missing: {good!r}"


def test_render_banner_is_befriend(monkeypatch):
    _roll(monkeypatch, 0.0)
    m = _ble("tracker")
    res = blebattle.battle_ble(m, Config(simulate=True))
    html = blebattle_screen.sequence_html(
        {"species": "Trackling", "name": "Neat Widget",
         "pairing": "just_works"}, res)
    last = html[-1]
    assert "FRIEND!" in last and "SIGNAL SPRITE" in last
    # "!" and the space are not base64 chars, so these can't false-match sprites
    assert "OWNED!" not in last and "BLE BATTLE" not in last


# -- mechanics / odds are unchanged (only the words changed) ----------------
def test_odds_boundaries_unchanged(monkeypatch):
    """Boundary rolls encode the exact pre-reskin odds table."""
    cfg = Config(simulate=True)

    # just_works p=0.95
    _roll(monkeypatch, 0.94)
    assert blebattle.battle_ble(_ble("tracker"), cfg)["result"] == "cracked"
    _roll(monkeypatch, 0.96)
    assert blebattle.battle_ble(_ble("tracker"), cfg)["result"] == "failed"

    # pin p=0.65
    _roll(monkeypatch, 0.64)
    assert blebattle.battle_ble(_ble("wearable"), cfg)["result"] == "cracked"
    _roll(monkeypatch, 0.66)
    assert blebattle.battle_ble(_ble("wearable"), cfg)["result"] == "failed"

    # secure: ease-guard chance 0.35, then befriend p=0.9
    _roll(monkeypatch, 0.34)          # eases guard -> befriended (knob path)
    r = blebattle.battle_ble(_ble("phone", connectable=False), cfg)
    assert r["result"] == "cracked" and "knob" in r["via"]
    _roll(monkeypatch, 0.36)          # can't ease + not connectable -> bashful
    assert blebattle.battle_ble(
        _ble("phone", connectable=False), cfg)["result"] == "immune"

    # secure + connectable: boop chance 0.7
    _roll(monkeypatch, 0.69)
    assert blebattle.battle_ble(
        _ble("phone", connectable=True), cfg)["result"] == "cracked"
    _roll(monkeypatch, 0.70)
    assert blebattle.battle_ble(
        _ble("phone", connectable=True), cfg)["result"] == "failed"


def test_rewards_unchanged():
    """tame/befriend rewards use the same formula (xp=6+n*2+juicy*3,
    scrap=10+n*4+20-if-rare)."""
    rare = monsters.from_ble({"addr": "AA:BB:CC:00:11:77",
                              "device_class": "tracker", "company": "Apple"})
    r = ble.tame_reward(rare, {"services": ["device_information", "find_my"],
                               "characteristics": 12})
    assert r["xp"] == 6 + 2 * 2 + 2 * 3      # both services are "juicy"
    assert r["scrap"] == 10 + 2 * 4 + 20     # rare bonus


def test_defense_and_pairing_mechanics_unchanged():
    assert _ble("tracker").pairing == "just_works"
    assert _ble("wearable").pairing == "pin"
    assert _ble("phone").pairing == "secure"
    assert _ble("phone").defense > _ble("tracker").defense


def test_species_count_stable():
    # the reskin renamed NO species; the dex denominator is unchanged.
    assert monsters.species_count() == len(monsters.all_species())
    for name in ("Trackling", "Echobub", "Vitalix", "Pocketling", "Tickbit"):
        assert name in monsters.all_species()


# -- the tracker safety feature stays (protective, not exploitative) ---------
def test_tracker_safety_alert_preserved(tmp_path):
    cfg = Config()
    cfg.tracker_alert_sightings = 3
    cfg.tracker_alert_window_s = 100.0
    log = ble.TrackerLog(str(tmp_path / "trk.json"))
    log.record("C0:FF:EE:00:00:01", now=0.0)
    log.record("C0:FF:EE:00:00:01", now=60.0)
    log.record("C0:FF:EE:00:00:01", now=150.0)
    assert log.is_stalker("C0:FF:EE:00:00:01", cfg)
    assert log.should_alert("C0:FF:EE:00:00:01", cfg) is True
