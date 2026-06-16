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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all good")
