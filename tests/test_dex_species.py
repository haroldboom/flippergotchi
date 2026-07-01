"""The dex renders as a SPECIES collection, not a BSSID packet-log."""
from __future__ import annotations

from flippergotchi.game import monsters
from flippergotchi.game.bestiary import Bestiary
from flippergotchi.game.monsters import Monster


def _wifi(bssid, species, level=5, shiny=False, defeated=False):
    return Monster(
        id=bssid, kind="wifi", name=f"net-{bssid[-2:]}", species=species,
        element="Spark", level=level, hp=30, defense=40,
        shiny=shiny, defeated=defeated, captured=True,
    )


def test_species_count_is_finite_and_matches_all_species():
    names = monsters.all_species()
    # finite, de-duped, sorted
    assert names == sorted(set(names))
    assert monsters.species_count() == len(names)
    assert monsters.species_count() > 0
    # derived from real species tables, no invented ones
    assert "Gnashgear" in names          # WiFi vendor species
    assert "Crypterion" in names         # WiFi fallback
    assert "Pocketling" in names         # BLE species


def test_summary_aggregates_duplicates(tmp_path):
    dex = Bestiary(str(tmp_path / "dex.json"))
    # three distinct APs, all the same species
    dex.add(_wifi("AA:BB:CC:00:00:01", "Gnashgear", level=3))
    dex.add(_wifi("AA:BB:CC:00:00:02", "Gnashgear", level=9))
    dex.add(_wifi("AA:BB:CC:00:00:03", "Gnashgear", level=6))
    dex.add(_wifi("AA:BB:CC:00:00:04", "Crypterion", level=4))

    summary = dex.species_summary()
    by_species = {r["species"]: r for r in summary}

    # duplicates collapse to a single species row with a count
    assert by_species["Gnashgear"]["count"] == 3
    assert by_species["Gnashgear"]["best_level"] == 9  # best level seen
    assert by_species["Crypterion"]["count"] == 1
    # two distinct species caught out of the finite set
    assert len(summary) == 2


def test_xofn_species_count_is_right(tmp_path):
    dex = Bestiary(str(tmp_path / "dex.json"))
    dex.add(_wifi("AA:BB:CC:00:00:01", "Gnashgear"))
    dex.add(_wifi("AA:BB:CC:00:00:02", "Gnashgear"))  # dup -> same species
    dex.add(_wifi("AA:BB:CC:00:00:03", "Mantalink"))

    caught = len(dex.species_summary())
    assert caught == 2                      # X = distinct species, not APs
    assert caught <= monsters.species_count()  # X never exceeds N


def test_shiny_flag_surfaces(tmp_path):
    dex = Bestiary(str(tmp_path / "dex.json"))
    dex.add(_wifi("AA:BB:CC:00:00:01", "Gnashgear", shiny=False))
    dex.add(_wifi("AA:BB:CC:00:00:02", "Gnashgear", shiny=True))  # one shiny
    dex.add(_wifi("AA:BB:CC:00:00:03", "Mantalink", shiny=False))

    by_species = {r["species"]: r for r in dex.species_summary()}
    assert by_species["Gnashgear"]["shiny"] is True   # any shiny -> flagged
    assert by_species["Mantalink"]["shiny"] is False


def test_defeated_flag_surfaces(tmp_path):
    dex = Bestiary(str(tmp_path / "dex.json"))
    dex.add(_wifi("AA:BB:CC:00:00:01", "Gnashgear", defeated=False))
    dex.add(_wifi("AA:BB:CC:00:00:02", "Gnashgear", defeated=True))
    by_species = {r["species"]: r for r in dex.species_summary()}
    assert by_species["Gnashgear"]["defeated"] is True


def test_empty_dex(tmp_path):
    dex = Bestiary(str(tmp_path / "dex.json"))
    assert dex.species_summary() == []


def test_summary_sorted_by_count_desc(tmp_path):
    dex = Bestiary(str(tmp_path / "dex.json"))
    dex.add(_wifi("AA:BB:CC:00:00:01", "Mantalink"))
    dex.add(_wifi("AA:BB:CC:00:00:02", "Gnashgear"))
    dex.add(_wifi("AA:BB:CC:00:00:03", "Gnashgear"))
    counts = [r["count"] for r in dex.species_summary()]
    assert counts == sorted(counts, reverse=True)


def test_cmd_dex_renders_species_collection(tmp_path, capsys):
    class Cfg:
        bestiary_path = str(tmp_path / "dex.json")
        ledger_path = str(tmp_path / "ledger.json")

    from flippergotchi import commands
    dex = Bestiary(Cfg.bestiary_path)
    dex.add(_wifi("AA:BB:CC:00:00:01", "Gnashgear"))
    dex.add(_wifi("AA:BB:CC:00:00:02", "Gnashgear"))
    dex.save()

    commands.cmd_dex(Cfg)
    out = capsys.readouterr().out
    assert f"of {monsters.species_count()} species" in out
    assert "Gnashgear" in out
    # collapses two APs into one species row (no BSSID spam)
    assert out.count("Gnashgear") == 1


def test_cmd_dex_empty(tmp_path, capsys):
    class Cfg:
        bestiary_path = str(tmp_path / "dex.json")
        ledger_path = str(tmp_path / "ledger.json")

    from flippergotchi import commands
    commands.cmd_dex(Cfg)
    out = capsys.readouterr().out
    assert f"0 / {monsters.species_count()}" in out
