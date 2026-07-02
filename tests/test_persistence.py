from __future__ import annotations

import json
import os

from flippergotchi import persistence
from flippergotchi.persistence import CURRENT_SCHEMA, migrate
from flippergotchi.pet.state import PetState


def test_round_trip_preserves_fields(tmp_path):
    path = str(tmp_path / "state.json")
    st = PetState(name="Sharky", level=7, xp=42.0, handshakes=9,
                  duel_wins=3, stage="juvenile", element="Cyber")
    persistence.save(path, st)
    loaded = persistence.load(path)
    assert loaded.name == "Sharky"
    assert loaded.level == 7
    assert loaded.xp == 42.0
    assert loaded.handshakes == 9
    assert loaded.duel_wins == 3
    assert loaded.stage == "juvenile"
    assert loaded.element == "Cyber"
    assert loaded.schema_version == CURRENT_SCHEMA


def test_save_writes_schema_version(tmp_path):
    path = str(tmp_path / "state.json")
    persistence.save(path, PetState(name="T"))
    with open(path) as f:
        on_disk = json.load(f)
    assert on_disk["schema_version"] == CURRENT_SCHEMA


def test_legacy_save_without_version_or_newer_fields(tmp_path):
    """A pre-versioning save missing newer fields loads with defaults + stamp."""
    path = str(tmp_path / "state.json")
    legacy = {
        "name": "OldPet",
        "level": 4,
        "xp": 12.5,
        "hunger": 30.0,
        # NOTE: no schema_version, no duel_wins, no element, etc.
    }
    with open(path, "w") as f:
        json.dump(legacy, f)
    loaded = persistence.load(path)
    assert loaded.name == "OldPet"
    assert loaded.level == 4
    assert loaded.xp == 12.5
    # missing newer fields fall back to PetState defaults
    assert loaded.duel_wins == 0
    assert loaded.element == "Aether"
    assert loaded.schema_version == CURRENT_SCHEMA


def test_unknown_keys_are_dropped(tmp_path):
    path = str(tmp_path / "state.json")
    data = {
        "name": "Z",
        "level": 2,
        "schema_version": CURRENT_SCHEMA,
        "obsolete_field": 1234,        # removed key
        "another_ghost": "boo",
    }
    with open(path, "w") as f:
        json.dump(data, f)
    loaded = persistence.load(path)  # must not raise
    assert loaded.name == "Z"
    assert loaded.level == 2
    assert not hasattr(loaded, "obsolete_field")
    assert not hasattr(loaded, "another_ghost")


def test_corrupt_file_returns_fresh_state(tmp_path):
    path = str(tmp_path / "state.json")
    with open(path, "w") as f:
        f.write("{not valid json at all ::::")
    loaded = persistence.load(path)
    assert isinstance(loaded, PetState)
    assert loaded.name == "Flippy"
    assert loaded.schema_version == CURRENT_SCHEMA


def test_missing_file_returns_fresh_state(tmp_path):
    path = str(tmp_path / "does-not-exist.json")
    assert not os.path.exists(path)
    loaded = persistence.load(path)
    assert isinstance(loaded, PetState)
    assert loaded.name == "Flippy"


def test_migrate_is_idempotent():
    base = PetState(name="Idem", level=5, duel_wins=2).to_dict()
    once = migrate(base)
    twice = migrate(once)
    assert once == twice
    assert once["schema_version"] == CURRENT_SCHEMA


def test_migrate_stamps_and_fills_defaults():
    out = migrate({"name": "Bare"})
    assert out["schema_version"] == CURRENT_SCHEMA
    # every PetState field is present after migration
    for fld in PetState().to_dict():
        assert fld in out
    assert out["name"] == "Bare"


def test_migrate_does_not_mutate_input():
    src = {"name": "NoMutate"}
    migrate(src)
    assert src == {"name": "NoMutate"}


def test_migrate_upgrades_v1_and_v0_dicts_to_loadable_state(tmp_path):
    """A hand-crafted v1 dict AND a v0 dict (no schema_version) each migrate up
    to CURRENT_SCHEMA and load into a usable PetState through the real
    load() path."""
    # v1 (explicit schema_version, pre-v2 fields absent)
    v1 = {"schema_version": 1, "name": "V1Pet", "level": 3, "xp": 5.0}
    upgraded = migrate(v1)
    assert upgraded["schema_version"] == CURRENT_SCHEMA
    st = PetState.from_dict(upgraded)
    assert st.name == "V1Pet"
    assert st.level == 3
    # v2-era fields backfilled with safe defaults
    assert st.hardcore is False
    assert st.satiety == 0.0
    assert st.active_title == ""

    # v0 (NO schema_version key at all -> treated as 0) round-tripped via load()
    v0 = {"name": "V0Pet", "level": 6, "hunger": 40.0}
    p1 = str(tmp_path / "v1.json")
    p0 = str(tmp_path / "v0.json")
    with open(p1, "w") as f:
        json.dump(v1, f)
    with open(p0, "w") as f:
        json.dump(v0, f)
    loaded_v1 = persistence.load(p1)
    loaded_v0 = persistence.load(p0)
    assert loaded_v1.name == "V1Pet" and loaded_v1.schema_version == CURRENT_SCHEMA
    assert loaded_v0.name == "V0Pet" and loaded_v0.level == 6
    assert loaded_v0.schema_version == CURRENT_SCHEMA


def test_future_schema_version_loads_without_crashing(tmp_path):
    """A save stamped with a FUTURE/unknown schema_version (no migration step
    for it) must still load into a valid PetState rather than raising."""
    future = CURRENT_SCHEMA + 99
    data = {"schema_version": future, "name": "FromTheFuture", "level": 11}

    # migrate() alone: no step for this version, so it stops -- but still
    # produces a well-formed, field-complete dict.
    out = migrate(data)
    for fld in PetState().to_dict():
        assert fld in out
    assert out["name"] == "FromTheFuture"

    # and through the real load() path it yields a usable PetState.
    path = str(tmp_path / "future.json")
    with open(path, "w") as f:
        json.dump(data, f)
    loaded = persistence.load(path)
    assert isinstance(loaded, PetState)
    assert loaded.name == "FromTheFuture"
    assert loaded.level == 11
