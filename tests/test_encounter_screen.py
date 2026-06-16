"""The visual encounter card renders for WiFi villains and BLE mini-monsters."""
from __future__ import annotations

from flippergotchi.view import encounter_screen


def test_wifi_encounter_card(tmp_path):
    out = encounter_screen.render(str(tmp_path / "enc.html"), {
        "species": "Crypterion", "name": "OPTUS_A1B2", "level": 11,
        "encryption": "wpa2", "defense": 72, "kind": "wifi"})
    html = open(out).read()
    assert "Crypterion" in html and "WPA2" in html
    assert "CAPTURE" in html and "RUN" in html
    assert "A wild Crypterion appeared!" in html
    # the species sprite (not the fallback) is embedded
    from flippergotchi.view import monster_art
    assert monster_art.sprite_b64("Crypterion") in html


def test_ble_encounter_card_and_custom_line(tmp_path):
    out = encounter_screen.render(str(tmp_path / "enc.html"), {
        "species": "Pocketling", "name": "Pixel 9", "level": 4,
        "encryption": "", "defense": 5, "kind": "ble"}, line="blip!")
    html = open(out).read()
    assert "Pocketling" in html and ">BLE<" in html
    assert "blip!" in html


def test_unknown_species_uses_fallback(tmp_path):
    out = encounter_screen.render(str(tmp_path / "enc.html"), {
        "species": "Nope", "name": "x", "level": 1, "encryption": "open",
        "defense": 0, "kind": "wifi"})
    # no sprite for "Nope" -> fallback sprite embedded, still renders
    assert "Nope" in open(out).read()
