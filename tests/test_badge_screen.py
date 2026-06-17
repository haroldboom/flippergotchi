"""The grayscale badge-wall render reflects the book + stats, masks hidden badges."""
from __future__ import annotations

from flippergotchi.game import achievements as ach_mod
from flippergotchi.view import badge_screen


class _State:
    name = "Sharkey"
    active_title = ""
    titles: list = []


def _book(tmp_path, unlocked=()):
    book = ach_mod.AchievementBook(str(tmp_path / "ach.json"))
    for bid in unlocked:
        book._unlocked.add(bid)
    return book


def test_render_writes_badge_names_and_tier_marks(tmp_path):
    book = _book(tmp_path, unlocked=["first_catch"])
    stats = {"catches": 1, "cracks": 0, "duel_wins": 0, "distance_m": 0,
             "level": 1, "stage": "egg", "equipped_slots": 0, "shinies": 0,
             "quests_done": 0, "streak": 0}
    out = badge_screen.render(str(tmp_path / "badges.html"), book, stats, _State())
    html = open(out).read()
    # real badge names from the catalogue
    assert "First Blood" in html
    assert "Safecracker" in html
    assert "Trailblazer" in html
    # tier marks B/S/G appear
    assert ">B<" in html and ">S<" in html and ">G<" in html
    # grayscale screen + native size
    assert "filter:grayscale(1)" in html and "144px" in html
    # progress count of the whole catalogue
    got, total = book.progress()
    assert f"{got}/{total}" in html


def test_unlocked_star_and_locked_progress(tmp_path):
    book = _book(tmp_path, unlocked=["first_catch"])
    stats = {"catches": 4, "cracks": 0, "duel_wins": 0, "distance_m": 0,
             "level": 1, "stage": "egg", "equipped_slots": 0, "shinies": 0,
             "quests_done": 0, "streak": 0}
    out = badge_screen.render(str(tmp_path / "badges.html"), book, stats, _State())
    html = open(out).read()
    # unlocked badge carries a star glyph
    assert "&#9733;" in html
    # locked Beastmaster I shows a progress hint (4 of 10)
    assert "4/10" in html


def test_render_masks_a_hidden_badge(tmp_path, monkeypatch):
    # the render delegates masking to achievements.display_name, so a hidden,
    # not-yet-earned badge shows as the secret placeholder (shiny_find is now
    # un-hidden/reachable, so use a synthetic hidden badge for this).
    book = _book(tmp_path)
    secret = ach_mod.Badge("secret_x", "TopSecret", "hidden", "catches", 1,
                           hidden=True)
    monkeypatch.setattr(book, "all", lambda: [secret])
    out = badge_screen.render(str(tmp_path / "b.html"), book, {"catches": 0}, _State())
    html = open(out).read()
    assert "TopSecret" not in html
    assert "??? (secret)" in html
