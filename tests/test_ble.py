"""BLE expansion: enriched taxonomy, GATT 'tame' rewards, tracker detection."""
from __future__ import annotations

from flippergotchi.config import Config
from flippergotchi.core.bluetooth import BluetoothScanner
from flippergotchi.game import monsters
from flippergotchi.game.ble import TrackerLog, tame_reward


# -- taxonomy ---------------------------------------------------------------
def test_from_ble_species_by_class_and_vendor():
    m = monsters.from_ble({"addr": "AA:BB:CC:00:11:22", "name": "AirTag",
                           "device_class": "tracker", "company": "Apple",
                           "services": ["find_my"], "rssi": -55})
    assert m.species == "Trackling" and m.rarity == "rare"
    assert m.element == "Aether" and m.vendor == "Apple"

    buds = monsters.from_ble({"addr": "AA:BB:CC:00:11:33", "name": "Galaxy Buds",
                              "device_class": "audio", "company": "Samsung",
                              "services": ["audio_sink"], "rssi": -50})
    assert buds.species == "Echobub" and buds.element == "Tide"


def test_from_ble_level_scales_with_services():
    few = monsters.from_ble({"addr": "AA:BB:CC:00:11:44", "device_class": "phone",
                             "services": [], "rssi": -70})
    many = monsters.from_ble({"addr": "AA:BB:CC:00:11:55", "device_class": "phone",
                              "services": ["a", "b", "c", "d"], "rssi": -70})
    assert many.level > few.level


# -- tame reward ------------------------------------------------------------
def test_tame_reward_scales_and_rewards_rare():
    common = monsters.from_ble({"addr": "AA:BB:CC:00:11:66", "device_class": "phone"})
    rare = monsters.from_ble({"addr": "AA:BB:CC:00:11:77", "device_class": "tracker",
                              "company": "Apple"})
    thin = tame_reward(common, {"services": ["generic_access"], "characteristics": 3})
    rich = tame_reward(rare, {"services": ["device_information", "battery_service",
                                           "heart_rate", "find_my"],
                              "characteristics": 12})
    assert rich["xp"] > thin["xp"] and rich["scrap"] > thin["scrap"]
    assert "services" in rich["key"]


# -- enumerate (sim) --------------------------------------------------------
def test_sim_enumerate_is_deterministic():
    s = BluetoothScanner(Config())   # simulate defaults False? -> set it
    s.mode = "sim"
    a = s.enumerate("AA:BB:CC:00:11:22")
    b = s.enumerate("AA:BB:CC:00:11:22")
    assert a == b and a["services"] and a["characteristics"] > 0


def test_classify_buckets():
    c = BluetoothScanner._classify
    assert c("MX Keys", "Logitech", ["human_interface_device"], True) == "input"
    assert c("Hue", "Signify", ["smarthome"], True) == "smarthome"
    assert c("Contour", "Ascensia", ["glucose"], True) == "medical"
    assert c("AirTag", "Apple", ["find_my"], False) == "tracker"
    assert c("Random Thing", "", [], True) == "unknown"


# -- tracker detection ------------------------------------------------------
def test_tracker_log_flags_a_follower(tmp_path):
    cfg = Config()
    cfg.tracker_alert_sightings = 3
    cfg.tracker_alert_window_s = 100.0
    log = TrackerLog(str(tmp_path / "trk.json"))
    # one sighting -> not a stalker
    log.record("C0:FF:EE:00:00:01", "AirTag", now=0.0)
    assert not log.is_stalker("C0:FF:EE:00:00:01", cfg)
    # seen repeatedly across a 100s+ window -> stalker
    log.record("C0:FF:EE:00:00:01", "AirTag", now=60.0)
    log.record("C0:FF:EE:00:00:01", "AirTag", now=150.0)
    assert log.is_stalker("C0:FF:EE:00:00:01", cfg)
    # should_alert fires exactly once
    assert log.should_alert("C0:FF:EE:00:00:01", cfg) is True
    assert log.should_alert("C0:FF:EE:00:00:01", cfg) is False
    # survives a save/reload
    log.save()
    assert TrackerLog(str(tmp_path / "trk.json")).is_stalker(
        "C0:FF:EE:00:00:01", cfg)


def test_every_ble_species_modelled():
    from flippergotchi.view import monster_art
    for species in set(monsters._BLE_SPECIES.values()):
        assert monster_art.sprite_path(species), f"no sprite for {species}"
