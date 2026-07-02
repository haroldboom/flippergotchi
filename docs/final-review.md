# Whole-codebase QA pass — findings & dispositions

*A five-lens read-only review (correctness/bugs, cohesion/dead-code, safety
regression, test-suite quality, config/docs consistency) of the full tree, then a
fix pass. This records what was found, what was fixed, and what was deliberately
deferred. Suite: 577 passing.*

## Fixed this pass

### Safety (all three regressions closed)
- **Terminal-injection**: attacker-controlled names/SSIDs printed raw in many
  CLI/log paths (scan, catch, dex, duel, battle, recon). Now sanitized at
  ingestion — `monsters.from_ap/from_ble` clean the SSID/BLE name, `_note_peer`
  cleans the peer name, and `cmd_scan` cleans the raw SSID it prints. (HTML views
  already `html.escape`.)
- **`--dry-run` transmit**: `blebattle.battle_ble` had no dry-run guard, so
  `battle <ble> --dry-run` could connect + `write_gatt_char` on real hardware.
  It now returns a dry-run result without the crackle/GATT hops.
- **BLE scope gate**: autonomous GATT enumerate (`_tame_ble`) was gated only by
  the global consent flag; now per-target (consent AND (manual | in_scope)) with
  the deny audited — matching deauth/crack and the config's own claim.

### Correctness
- **Persist soft-stakes/death state**: `_sick`/`_neglect_h`/`_faint_ticks` are now
  `PetState` fields (round-trip via to_dict/from_dict; old saves backfill). Fixes
  dodging neglect-sickness by restarting and a dying hardcore pet regaining its
  death runway on reload.
- **Hardcore self-rescue**: a starving/fainting hardcore pet could forage + eat
  its way out of the death runway indefinitely while walking. `can_forage()` now
  blocks foraging in that state (hand-feed still works). This also made the
  previously order-dependent hardcore-death test deterministic.
- **Infinite-loop guard**: `xp_to_next` floored at 1.0 so a bad `base_xp`/`level_exp`
  config can't spin the level-up loop forever.
- **Durability**: `Larder._load` tolerates a bad row instead of wiping the whole
  larder; `AchievementBook.save` now uses a pid-unique tmp + fsync like the other
  stores.

### Tests
- Added `tests/conftest.py` autouse RNG-seed fixture (kills order-dependent
  flakiness from tests that consume the global `random`).
- Fixed the two flaky tests (shiny: force a deterministic catch; hardcore: fixed
  by the can_forage change) and a test that wrote the **real** `~/.flippergotchi/audit.log`
  (now redirected to tmp).
- New test guarding the auto-duel fair-match gate (previously untested — the only
  prior test disabled the gate).

### Cohesion / config / docs
- Removed dead code (`gearsets.describe_set`, `elements.advantage` alias, the
  unused `blebattle_html_out` config field) and unused imports.
- Made phantom "tunable via cfg" knobs real `Config` fields (`auto_duel_cooldown/
  chance/min_odds/max_odds`, `sleep_energy_low`, `wake_energy_high`,
  `onboard_quiet_catches`) — they were read via `getattr` but ignored from TOML.
- Fixed stale comments (prime "no sprite yet", paragon "field added by another
  agent", shop "not called from agent.py", the `_sick`/`_faint_ticks` "non-persisted"
  notes) and `config.example.toml` drift (`xp_per_snack` 2.0→0.5, `forage_food_per_m`
  0.06→0.01, the wrong `character_variant` list). Removed the dead version-mismatch
  note in `docs/packaging.md` and added a since-addressed banner to the
  implementation review.

## Deferred (with reasons)

- **Daemon-vs-CLI concurrent save clobber** — if the agent daemon and a CLI
  command run at once, last-writer-wins can lose data (agent rewrites all stores
  every 10s from memory; no file locking). Single-process use is safe. Fix needs
  file locking / reload-before-save or routing the agent through the `GameState`
  facade — a real architecture change, out of scope for a fix pass.
- **Half-wired features** (product decisions, not bugs): the shop `lure` item and
  food `salvage` field do nothing yet; the rotating weekly challenge is scored +
  rewarded but never *displayed* in `cmd_quests`; gear-**set** bonuses feed duels
  but aren't shown in `cmd_gear`. Each needs a "wire it up or cut it" call.
- **GameState-bypass in some CLI writers** (`cmd_gear/quests/title/cloud-submit`
  save stores directly) — harmless single-process, but not the one atomic save
  path; unify if daemon+CLI concurrency is ever supported.
- **Sprite-stem duplication** — the `variant/stage` sprite-stem pattern is
  copy-pasted ~5× and `screens.player_stem` diverges; worth unifying into one
  helper (low risk, cosmetic).
- **Chain-step overflow** — a single large quest event advances at most one chain
  step and drops the remainder; minor progression loss.
- **Test hygiene** — `_cfg(tmp_path)` is copy-pasted across ~13 files and ~13 use
  `tempfile.mkdtemp()` instead of the `tmp_path` fixture; consolidate into
  conftest. Also worth adding `pytest-randomly` to CI so this flakiness class
  fails loudly, plus GameState all-store round-trip and migrate-chain coverage.
- **`schema_version` numbering** is cosmetic-stale (fields added without bumping);
  harmless because `from_dict` backfills, but the number no longer tracks shape.

## Confirmed sound (checked, no action)
Persistence migration of old saves, duel numeric guards + `estimate_win_pct`
RNG-isolation, `authz` fail-closed scope checks, bettercap deauth gating, cloud
upload gating, no weak default creds, and the Bestiary re-encounter merge.
