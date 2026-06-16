"""The WiFi-species enemy monsters are modelled (each has a sprite on disk)."""
from __future__ import annotations

from flippergotchi.view import monster_art
from flippergotchi.game import monsters


def test_every_wifi_species_has_a_sprite():
    # the species game/monsters can assign to a WiFi AP must all be modelled
    for species in set(monsters._WIFI_SPECIES.values()):
        assert monster_art.sprite_path(species), f"no sprite for {species}"


def test_every_ble_species_has_a_sprite():
    # BLE mini-monsters are modelled too (a friendlier gadget tier)
    for species in set(monsters._BLE_SPECIES.values()):
        assert monster_art.sprite_path(species), f"no sprite for {species}"


def test_sprite_b64_round_trips():
    b = monster_art.sprite_b64("Crypterion")
    assert isinstance(b, str) and len(b) > 100


def test_unknown_species_is_none():
    assert monster_art.sprite_path("Nope") is None
    assert monster_art.sprite_b64("") is None


def test_modelled_species_lists_all_four():
    assert set(monster_art.modelled_species()) == set(monster_art.SPECIES_SPRITES)
