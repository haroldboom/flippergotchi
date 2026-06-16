from __future__ import annotations

import json
import os

from .pet.state import PetState

# The schema version this build writes. Bump it whenever PetState's on-disk
# shape changes in a way a migration step needs to repair (see migrate()).
CURRENT_SCHEMA = 1


def _v0_to_v1(data: dict) -> dict:
    """Legacy saves predating `schema_version` (treated as v0).

    Nothing structural changed at v1 - from_dict already tolerates missing
    fields - so this is just the identity step. It exists so the dispatch
    table below has an entry for every version and the upgrade path is
    explicit/auditable.
    """
    return data


# Sequential upgrade steps, keyed by the version they upgrade FROM.
# To add the next version:
#   1. bump CURRENT_SCHEMA to 2 (and the default in PetState.schema_version),
#   2. write `def _v1_to_v2(data): ... return data` that repairs a v1 dict,
#   3. register it here: 1: _v1_to_v2.
# migrate() then chains the steps until the data reaches CURRENT_SCHEMA.
_MIGRATIONS = {
    0: _v0_to_v1,
}


def migrate(data: dict) -> dict:
    """Upgrade a raw save dict to CURRENT_SCHEMA. Pure + idempotent.

    Runs the sequential upgrade steps, fills any fields still missing from
    PetState's defaults, drops keys PetState no longer knows about, and stamps
    the current schema_version. Re-running on an already-current dict is a
    no-op. Never raises on a well-formed dict.
    """
    data = dict(data)
    version = int(data.get("schema_version", 0) or 0)

    while version < CURRENT_SCHEMA:
        step = _MIGRATIONS.get(version)
        if step is None:  # gap in the table - stop rather than loop forever
            break
        data = step(data)
        version += 1

    defaults = PetState().to_dict()
    known = set(defaults)
    # drop unknown/removed keys, then backfill any missing fields with defaults
    merged = {k: v for k, v in data.items() if k in known}
    for k, default in defaults.items():
        merged.setdefault(k, default)
    merged["schema_version"] = CURRENT_SCHEMA
    return merged


def load(path: str) -> PetState:
    path = os.path.expanduser(path)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return PetState.from_dict(migrate(json.load(f)))
        except Exception:
            pass
    return PetState()


def save(path: str, state: PetState) -> None:
    path = os.path.expanduser(path)
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state.to_dict(), f, indent=2)
    os.replace(tmp, path)
