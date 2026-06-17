"""Daily-quests: progress, completion, rewards, persistence, and daily reroll."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flippergotchi.game.quests import QuestLog, _TEMPLATES


def _log():
    return QuestLog(os.path.join(tempfile.mkdtemp(), "q.json"))


def test_record_increments_progress():
    q = _log()
    q.roll("2026-06-16", n=len(_TEMPLATES))  # all templates -> every metric active
    target = next(x for x in q.active() if x.metric == "snacks")
    q.record("snacks", 1)
    assert target.progress == 1 and target.done is False
    # an unmatched metric touches nothing
    assert q.record("nope", 99) == []


def test_reaching_target_marks_done_and_returns_newly_completed():
    q = _log()
    q.roll("2026-06-16", n=len(_TEMPLATES))
    target = next(x for x in q.active() if x.metric == "snacks")
    newly = q.record("snacks", target.target)
    assert target.done is True
    assert target in newly
    # already-done quests aren't returned again
    assert q.record("snacks", 5) == []


def test_templates_have_rewards():
    for tid, desc, metric, tgt, reward in _TEMPLATES:
        assert isinstance(reward, dict) and reward


def test_persistence_roundtrip():
    p = os.path.join(tempfile.mkdtemp(), "q.json")
    q = QuestLog(p)
    q.roll("2026-06-16", n=3)
    metric = q.active()[0].metric
    q.record(metric, 1)
    q.save()
    reloaded = QuestLog(p)
    assert reloaded.day == "2026-06-16"
    assert reloaded.active()[0].progress == 1


def test_roll_on_new_day_replaces_quests():
    q = _log()
    q.roll("2026-06-16", n=3)
    before = [x.id for x in q.active()]
    q.record(q.active()[0].metric, 1)
    # same day -> no reroll, progress preserved
    q.roll("2026-06-16", n=3)
    assert [x.id for x in q.active()] == before
    assert any(x.progress for x in q.active())
    # new day -> rerolled, progress reset
    q.roll("2026-06-17", n=3)
    assert all(x.progress == 0 and x.done is False for x in q.active())
    assert q.day == "2026-06-17"


def test_grant_quest_reward_applies():
    from flippergotchi.config import Config
    from flippergotchi.game import equipment as eq
    from flippergotchi.game.quests import Quest, grant_quest_reward
    from flippergotchi.pet.state import PetState

    cfg = Config()
    st = PetState(handshakes=5, xp=0)
    inv = eq.Inventory(os.path.join(tempfile.mkdtemp(), "inv.json"))

    grant_quest_reward(Quest("a", "x", "catches", 1, reward={"handshakes": 3}), st, inv, cfg)
    assert st.handshakes == 8
    grant_quest_reward(Quest("b", "y", "snacks", 1, reward={"xp": 50}), st, inv, cfg)
    assert st.xp == 50
    grant_quest_reward(Quest("c", "z", "cracks", 1, reward={"gear": True}), st, inv, cfg)
    assert len(inv.all()) == 1


def test_grant_quest_reward_scrap_and_food():
    # the foundation fix: quests now pay scrap (into a passed wallet) + food
    from flippergotchi.config import Config
    from flippergotchi.game.quests import Quest, grant_quest_reward
    from flippergotchi.game.shop import Wallet
    from flippergotchi.pet.state import PetState

    cfg = Config()
    st = PetState(hunger=40.0)
    w = Wallet(os.path.join(tempfile.mkdtemp(), "w.json"))
    grant_quest_reward(Quest("a", "x", "catches", 1, reward={"scrap": 40}),
                       st, None, cfg, w)
    assert w.scrap == 40
    h0 = st.hunger
    grant_quest_reward(Quest("b", "y", "snacks", 1, reward={"food": 2}),
                       st, None, cfg, w)
    assert st.hunger < h0            # food fed the pet


def test_grant_quest_reward_scrap_without_wallet_persists():
    # wallet=None -> scrap is credited to a freshly loaded+saved wallet at cfg path
    from flippergotchi.config import Config
    from flippergotchi.game.quests import Quest, grant_quest_reward
    from flippergotchi.game.shop import Wallet
    from flippergotchi.pet.state import PetState

    cfg = Config()
    cfg.wallet_path = os.path.join(tempfile.mkdtemp(), "w.json")
    grant_quest_reward(Quest("a", "x", "catches", 1, reward={"scrap": 30}),
                       PetState(), None, cfg)
    assert Wallet(cfg.wallet_path).scrap == 30


def test_all_templates_have_scrap():
    # every daily quest should pay into the scrap economy now
    for tid, desc, metric, target, reward in _TEMPLATES:
        assert reward.get("scrap", 0) > 0, f"{tid} pays no scrap"


def test_every_metric_has_a_template():
    # no METRIC may be undeliverable: each one needs at least one quest template
    from flippergotchi.game.quests import METRICS, _TEMPLATES, _WEEKLY_TEMPLATES
    have = {t[2] for t in _TEMPLATES} | {t[2] for t in _WEEKLY_TEMPLATES}
    assert set(METRICS) <= have, f"metrics with no template: {set(METRICS) - have}"


def test_roll_distinct_metrics():
    import random
    q = _log()
    q.roll("2026-06-16", n=3, rng=random.Random(5))
    metrics = [x.metric for x in q.active()]
    assert len(metrics) == len(set(metrics))      # never two quests on one metric


def test_weekly_rolls_and_rerolls():
    import random
    q = _log()
    q.roll_weekly("2026-W10", n=2, rng=random.Random(1))
    first = [x.id for x in q.active_weeklies()]
    assert len(first) == 2
    q.roll_weekly("2026-W10", n=2)                # same week -> no reroll
    assert [x.id for x in q.active_weeklies()] == first
    q.roll_weekly("2026-W11", n=2, rng=random.Random(2))   # new week -> fresh
    assert all(x.progress == 0 for x in q.active_weeklies())


def test_record_bumps_daily_and_weekly():
    from flippergotchi.game.quests import Quest
    q = _log()
    q.quests = [Quest("d", "daily catch", "catches", 1)]
    q.weeklies = [Quest("w", "weekly catch", "catches", 1)]
    done = q.record("catches", 1)
    assert {x.id for x in done} == {"d", "w"}     # one event finishes both = 2 rewards


def test_all_dailies_bonus_once_per_day():
    from flippergotchi.game.quests import Quest, DAILY_CLEAR_BONUS
    q = _log()
    q.day = "2026-06-16"
    q.quests = [Quest("a", "x", "catches", 1, progress=1, done=True)]
    assert q.all_dailies_done()
    assert q.claim_daily_bonus("2026-06-16") == DAILY_CLEAR_BONUS
    assert q.claim_daily_bonus("2026-06-16") == 0          # only once per day
    q.quests.append(Quest("b", "y", "cracks", 1))          # not all done now
    q.bonus_day = ""
    assert q.claim_daily_bonus("2026-06-16") == 0


def test_migrate_v1_to_v2():
    import json
    from flippergotchi.game.quests import QuestLog, CURRENT_SCHEMA
    p = os.path.join(tempfile.mkdtemp(), "q.json")
    with open(p, "w") as f:                                # legacy v1: daily-only
        json.dump({"day": "2026-06-16", "quests": [
            {"id": "walk_2k", "description": "Walk 2 km", "metric": "distance_m",
             "target": 2000, "progress": 500, "done": False, "reward": {"scrap": 30}}]}, f)
    q = QuestLog(p)
    assert q.schema_version == CURRENT_SCHEMA
    assert q.active()[0].progress == 500                  # daily preserved
    assert q.weeklies == [] and q.week == "" and q.bonus_day == ""
    q.save()
    with open(p) as f:
        raw = json.load(f)
    assert raw["schema_version"] == CURRENT_SCHEMA and "weeklies" in raw


def test_lifetime_done_increments():
    from flippergotchi.game.quests import Quest
    q = _log()
    q.quests = [Quest("a", "x", "catches", 1)]
    assert q.lifetime_done == 0
    q.record("catches", 1)
    assert q.lifetime_done == 1                # feeds the quests_done capstone


def test_streak_increments_then_resets_on_missed_day():
    q = _log()
    q.roll("2026-06-16", n=2)
    for x in q.quests:
        x.done = True
    assert q.claim_daily_bonus("2026-06-16") > 0
    assert q.streak == 1
    q.roll("2026-06-17", n=2)                  # 06-16 was cleared -> streak survives
    for x in q.quests:
        x.done = True
    q.claim_daily_bonus("2026-06-17")
    assert q.streak == 2
    q.roll("2026-06-18", n=2)                  # fresh dailies, left incomplete
    q.roll("2026-06-19", n=2)                  # rolling past an unfinished day -> reset
    assert q.streak == 0


def test_chain_advances_step_by_step_and_completes():
    from flippergotchi.game.quests import _CHAINS
    cid, giver, title, steps = _CHAINS[0]      # first_steps: walk1k -> catch3 -> crack1
    q = _log()
    done = q.record("distance_m", 1000)         # step 1
    assert any(x.id == f"{cid}:0" for x in done)
    assert q.chains[cid]["step"] == 1
    assert any(x.id == f"{cid}:1" for x in q.record("catches", 3))   # step 2
    assert any(x.id == f"{cid}:2" for x in q.record("cracks", 1))    # step 3
    assert q.chains[cid]["done"] is True
    # a finished chain never advances again
    assert q.record("distance_m", 5000) == [] or \
        all(not x.id.startswith(cid) for x in q.record("cracks", 1))


def test_chain_step_carries_reward():
    from flippergotchi.game.quests import _CHAINS
    cid = _CHAINS[0][0]
    q = _log()
    done = q.record("distance_m", 1000)
    step_q = next(x for x in done if x.id == f"{cid}:0")
    assert step_q.reward.get("scrap", 0) > 0    # caller grants it like any quest


def test_chain_progress_persists():
    from flippergotchi.game.quests import QuestLog
    q = _log()
    q.record("distance_m", 500)                 # partial first step
    q.save()
    assert QuestLog(q.path).chains["first_steps"]["progress"] == 500


def test_active_chains_lists_current_step():
    q = _log()
    chains = q.active_chains()
    assert chains                               # all chains start active
    giver, title, desc, prog, target, idx, total = chains[0]
    assert idx == 1 and total >= 1 and giver


def test_migrate_v2_to_v3():
    from flippergotchi.game.quests import migrate, CURRENT_SCHEMA
    raw = migrate({"schema_version": 2, "day": "x", "quests": [],
                   "week": "", "weeklies": [], "bonus_day": ""})
    assert raw["schema_version"] == CURRENT_SCHEMA == 3
    assert raw["lifetime_done"] == 0 and raw["streak"] == 0
    assert raw["last_clear_day"] == ""


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
