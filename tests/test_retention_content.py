"""Endgame / retention content (gameplay-review "no endgame" fix).

Covers the month-scale badge ladders, the finite species-dex capstone, the
shiny collection ladder, escalating claim-once streak rewards, the rotating
weekly challenge, the new long chains, and the new persisted state fields.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.config import Config
from flippergotchi.game import achievements as ach
from flippergotchi.game import monsters
from flippergotchi.game.quests import (
    DAILY_CLEAR_BONUS, STREAK_REWARDS, QuestLog, grant_quest_reward, migrate,
)
from flippergotchi.game.shop import Wallet
from flippergotchi.pet.state import PetState


def _tmp(name):
    return os.path.join(tempfile.mkdtemp(), name)


def _book():
    return ach.AchievementBook(_tmp("a.json"))


class _Mon:
    def __init__(self, species, captured=True, shiny=False):
        self.species, self.captured, self.shiny = species, captured, shiny


class _Dex:
    def __init__(self, mons):
        self._mons = list(mons)

    def all(self):
        return list(self._mons)


# --- extended badge ladders ---------------------------------------------------
def test_new_ladder_tiers_unlock_at_thresholds():
    cases = [
        ("catch_250", {"catches": 250}), ("catch_500", {"catches": 500}),
        ("catch_1000", {"catches": 1000}), ("crack_100", {"cracks": 100}),
        ("crack_250", {"cracks": 250}), ("legend_10", {"legendary_kills": 10}),
        ("duel_win_100", {"duel_wins": 100}), ("walk_100k_m", {"distance_m": 100000}),
        ("walk_250k_m", {"distance_m": 250000}), ("tame_100", {"tames": 100}),
        ("tame_200", {"tames": 200}), ("quest_500", {"quests_done": 500}),
        ("quest_1000", {"quests_done": 1000}), ("streak_14", {"streak": 14}),
        ("streak_30", {"streak": 30}), ("streak_100", {"streak": 100}),
        ("level_25", {"level": 25}), ("level_40", {"level": 40}),
    ]
    for bid, stats in cases:
        badge = ach.get(bid)
        assert badge is not None, f"missing badge {bid}"
        book = _book()
        # one below threshold: stays locked
        metric = badge.metric
        below = {metric: stats[metric] - 1}
        assert all(b.id != bid for b in book.check(below)), f"{bid} unlocked early"
        # at threshold: unlocks
        assert any(b.id == bid for b in book.check(stats)), f"{bid} did not unlock"


def test_new_capstones_carry_titles():
    for bid, title in [("catch_500", "the Beastlord"),
                       ("crack_100", "the Nullcipher"),
                       ("tame_200", "the Signalbinder"),
                       ("walk_250k_m", "the Worldwalker"),
                       ("quest_1000", "the Unstoppable"),
                       ("streak_30", "the Unbroken"),
                       ("streak_100", "the Centurion")]:
        assert ach.get(bid).reward.get("title") == title


def test_ladder_rewards_stay_modest_scrap():
    # endgame ladders are prestige, not a scrap firehose: every new tier pays
    # at most 2500 scrap (the hidden grandmaster capstone is the ceiling)
    for b in ach.CATALOG:
        assert b.reward.get("scrap", 0) <= 2500, f"{b.id} pays too much scrap"


# --- shiny ladder --------------------------------------------------------------
def test_shiny_ladder_unlocks():
    for bid, n in [("shiny_5", 5), ("shiny_15", 15), ("shiny_50", 50)]:
        book = _book()
        assert all(b.id != bid for b in book.check({"shinies": n - 1}))
        assert any(b.id == bid for b in book.check({"shinies": n}))


def test_shiny_ladder_from_dex_via_build_stats():
    dex = _Dex([_Mon("Gnashgear", shiny=True) for _ in range(5)]
               + [_Mon("Kragnet", shiny=False)])
    stats = ach.build_stats(PetState(), dex=dex)
    assert stats["shinies"] == 5
    assert any(b.id == "shiny_5" for b in _book().check(stats))


# --- species-completion capstone ------------------------------------------------
def test_build_stats_counts_distinct_species():
    dex = _Dex([_Mon("Gnashgear"), _Mon("Gnashgear"), _Mon("Kragnet"),
                _Mon("Telewyrm", captured=False)])
    stats = ach.build_stats(PetState(), dex=dex)
    assert stats["species_caught"] == 2                       # dupes/uncaught don't count
    assert stats["species_total"] == monsters.species_count()  # the finite N


def test_dex_master_unlocks_only_on_full_dex():
    everything = [_Mon(s) for s in monsters.all_species()]
    partial = ach.build_stats(PetState(), dex=_Dex(everything[:-1]))
    assert all(b.id != "dex_master" for b in _book().check(partial))
    full = ach.build_stats(PetState(), dex=_Dex(everything))
    book = _book()
    assert any(b.id == "dex_master" for b in book.check(full))


def test_dex_master_grants_gold_title():
    badge = ach.get("dex_master")
    assert badge.tier == "gold"
    st = PetState()
    stats = ach.build_stats(st, dex=_Dex([_Mon(s) for s in monsters.all_species()]))
    ach.grant_reward(_book(), stats, st, Config(), Wallet(_tmp("w.json")))
    assert "the Reefmaster" in st.titles


def test_grandmaster_needs_legend_and_full_dex():
    full = _Dex([_Mon(s) for s in monsters.all_species()])
    legend_only = ach.build_stats(PetState(stage="legend"), dex=_Dex([]))
    assert all(b.id != "grandmaster" for b in _book().check(legend_only))
    dex_only = ach.build_stats(PetState(stage="adult"), dex=full)
    assert all(b.id != "grandmaster" for b in _book().check(dex_only))
    both = ach.build_stats(PetState(stage="legend"), dex=full)
    assert any(b.id == "grandmaster" for b in _book().check(both))
    assert ach.get("grandmaster").hidden                      # aspirational secret


def test_paragon_badge_reads_state_field():
    stats = ach.build_stats(PetState(paragon=1))
    assert stats["paragon"] == 1
    assert any(b.id == "paragon_1" for b in _book().check(stats))
    assert all(b.id != "paragon_1" for b in _book().check(
        ach.build_stats(PetState())))                        # default 0 stays locked


# --- escalating, claim-once streak rewards --------------------------------------
def _clear_day(q, day):
    q.roll(day, n=2)
    for x in q.quests:
        x.done = True
    return q.claim_daily_bonus(day)


def test_streak_rewards_escalate_at_milestones():
    q = QuestLog(_tmp("q.json"))
    for i in range(1, 7):
        assert _clear_day(q, f"2026-06-{i:02d}") == DAILY_CLEAR_BONUS
    # day 7: the first milestone pays on top of the ordinary bonus
    assert _clear_day(q, "2026-06-07") == DAILY_CLEAR_BONUS + STREAK_REWARDS[7]
    assert _clear_day(q, "2026-06-08") == DAILY_CLEAR_BONUS   # day 8: back to normal
    for i in range(9, 14):
        _clear_day(q, f"2026-06-{i:02d}")
    assert _clear_day(q, "2026-06-14") == DAILY_CLEAR_BONUS + STREAK_REWARDS[14]


def test_streak_rewards_claim_once_ever():
    q = QuestLog(_tmp("q.json"))
    q.streak = 6
    q.last_clear_day = "2026-06-06"
    assert _clear_day(q, "2026-06-07") == DAILY_CLEAR_BONUS + STREAK_REWARDS[7]
    # streak breaks, then is rebuilt past 7: the tier does NOT pay again
    q.streak = 6
    q.last_clear_day = "2026-07-06"
    assert _clear_day(q, "2026-07-07") == DAILY_CLEAR_BONUS
    assert q.streak_claimed == [7]


def test_streak_reward_tiers_are_7_14_30_100_and_escalate():
    tiers = sorted(STREAK_REWARDS)
    assert tiers == [7, 14, 30, 100]
    values = [STREAK_REWARDS[t] for t in tiers]
    assert values == sorted(values) and values[0] < values[-1]   # escalating


def test_streak_claimed_persists():
    p = _tmp("q.json")
    q = QuestLog(p)
    q.streak = 6
    _clear_day(q, "2026-06-07")
    q.save()
    assert QuestLog(p).streak_claimed == [7]


def test_streak_jump_still_collects_missed_tiers():
    # defensive >=: a save whose streak leapt past a tier collects it next clear
    q = QuestLog(_tmp("q.json"))
    q.streak = 20
    q.last_clear_day = "2026-06-20"
    bonus = _clear_day(q, "2026-06-21")
    assert bonus == DAILY_CLEAR_BONUS + STREAK_REWARDS[7] + STREAK_REWARDS[14]


# --- rotating weekly challenge ---------------------------------------------------
def test_weekly_challenge_rolls_and_rotates():
    q = QuestLog(_tmp("q.json"))
    assert q.active_challenge() is None                       # nothing before a roll
    q.roll_weekly("2026-W26")
    first = q.active_challenge()
    assert first is not None and first.id.startswith("chal_")
    q.roll_weekly("2026-W26")                                 # same week: unchanged
    assert q.active_challenge() is first
    q.roll_weekly("2026-W27")                                 # next week: rotated
    assert q.active_challenge().id != first.id


def test_weekly_challenge_is_deterministic_per_week():
    a, b = QuestLog(_tmp("q.json")), QuestLog(_tmp("q.json"))
    a.roll_weekly("2026-W30")
    b.roll_weekly("2026-W30")
    assert a.active_challenge().id == b.active_challenge().id


def test_weekly_challenge_records_progress_and_completes():
    q = QuestLog(_tmp("q.json"))
    q.roll_weekly("2026-W26")
    ch = q.active_challenge()
    done = q.record(ch.metric, ch.target)
    assert ch.done and ch in done                             # flows through record()
    assert q.record(ch.metric, 1) == [] or ch not in q.record(ch.metric, 1)


def test_weekly_challenge_pays_title_not_big_scrap():
    from flippergotchi.game.quests import _CHALLENGE_TEMPLATES
    for tid, desc, metric, target, reward in _CHALLENGE_TEMPLATES:
        assert reward.get("title"), f"{tid} has no title prize"
        assert reward.get("scrap", 0) <= 200, f"{tid} scrap too high"


def test_weekly_challenge_persists():
    p = _tmp("q.json")
    q = QuestLog(p)
    q.roll_weekly("2026-W26")
    q.record(q.active_challenge().metric, 1)
    q.save()
    r = QuestLog(p)
    assert r.challenge_week == "2026-W26"
    assert r.active_challenge().id == q.active_challenge().id
    assert r.active_challenge().progress == 1


def test_quest_reward_title_applied_once():
    st = PetState()
    cfg = Config()
    q = QuestLog(_tmp("q.json"))
    q.roll_weekly("2026-W26")
    ch = q.active_challenge()
    done = q.record(ch.metric, ch.target)
    chal_done = next(x for x in done if x.id == ch.id)        # chains fire too
    w = Wallet(_tmp("w.json"))
    msg = grant_quest_reward(chal_done, st, None, cfg, w)
    title = ch.reward["title"]
    assert title in st.titles and "title:" in msg
    # re-granting the same title (next season's re-earn) never duplicates it
    grant_quest_reward(chal_done, st, None, cfg, w)
    assert st.titles.count(title) == 1


# --- long chains ------------------------------------------------------------------
def test_month_scale_chains_exist_and_advance():
    from flippergotchi.game.quests import _CHAIN_BY_ID
    assert "the_long_haul" in _CHAIN_BY_ID and "deep_signal" in _CHAIN_BY_ID
    giver, title, steps = _CHAIN_BY_ID["the_long_haul"]
    assert len(steps) >= 4                                    # genuinely long
    assert any(s.reward.get("title") for s in steps)          # finale pays prestige
    q = QuestLog(_tmp("q.json"))
    done = q.record("distance_m", 25000)                      # step 1 of the long haul
    assert any(x.id == "the_long_haul:0" for x in done)
    assert q.chains["the_long_haul"]["step"] == 1


def test_chain_finale_title_flows_through_reward_path():
    from flippergotchi.game.quests import _CHAIN_BY_ID
    _, _, steps = _CHAIN_BY_ID["deep_signal"]
    q = QuestLog(_tmp("q.json"))
    st = PetState()
    q.record("tames", 25)
    q.record("duel_wins", 10)
    q.record("legendary_kills", 3)
    done = q.record("tames", 60)
    final = next(x for x in done if x.id == "deep_signal:3")
    grant_quest_reward(final, st, None, Config(), Wallet(_tmp("w.json")))
    assert "the Deep Signal" in st.titles
    assert q.chains["deep_signal"]["done"] is True


# --- persistence / migration -------------------------------------------------------
def test_migrate_v3_to_v4_adds_challenge_and_streak_blocks():
    raw = migrate({"schema_version": 3, "day": "x", "quests": [], "week": "",
                   "weeklies": [], "bonus_day": "", "lifetime_done": 0,
                   "streak": 0, "last_clear_day": ""})
    assert raw["schema_version"] == 4
    assert raw["challenge"] is None
    assert raw["challenge_week"] == ""
    assert raw["streak_claimed"] == []


def test_old_v3_questlog_file_still_loads():
    p = _tmp("q.json")
    with open(p, "w") as f:
        json.dump({"schema_version": 3, "day": "2026-06-16",
                   "quests": [{"id": "walk_2k", "description": "Walk 2 km",
                               "metric": "distance_m", "target": 2000,
                               "progress": 500, "done": False,
                               "reward": {"scrap": 30}}],
                   "week": "2026-W25", "weeklies": [], "bonus_day": "",
                   "lifetime_done": 12, "streak": 3,
                   "last_clear_day": "2026-06-15"}, f)
    q = QuestLog(p)
    assert q.active()[0].progress == 500 and q.streak == 3    # old data intact
    assert q.challenge is None and q.streak_claimed == []     # new blocks default


def test_state_paragon_field_persists_and_defaults():
    st = PetState(paragon=2)
    d = st.to_dict()
    assert d["paragon"] == 2
    assert PetState.from_dict(d).paragon == 2
    # old saves without the field load with the safe default
    legacy = {k: v for k, v in PetState().to_dict().items() if k != "paragon"}
    assert PetState.from_dict(legacy).paragon == 0


def test_book_progress_reflects_bigger_catalog():
    # sanity: the catalogue really grew into a long tail (was 21 badges)
    book = _book()
    unlocked, total = book.progress()
    assert unlocked == 0 and total >= 35


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
