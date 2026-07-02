"""Shared pytest fixtures.

The suite has several tests that (directly, or indirectly via the sim GPS wander
and the encounter capture roll) consume the process-global ``random`` module.
Without a fixed seed the pass/fail of those tests depended on collection order --
two were reproducibly flaky. Seed the global RNG before every test so results are
deterministic and order-independent; a test that needs a specific stream can still
reseed itself.
"""
import dataclasses
import itertools
import random

import pytest

from flippergotchi.config import Config


@pytest.fixture(autouse=True)
def _seed_global_rng():
    random.seed(1234)
    yield


@pytest.fixture
def make_cfg(tmp_path):
    """Factory for the canonical hermetic test Config.

    Builds a ``Config`` with ``simulate=True``, ``tui=False``,
    ``scan_bluetooth=False`` and EVERY persistent/render path (anything under
    ``~/.flippergotchi`` -- including ``audit_log`` -- or ``/tmp/``) redirected
    under this test's ``tmp_path`` as ``tmp_path / <field_name>``.  Keyword
    overrides are applied last, so drifted variants can do e.g.
    ``make_cfg(ai_backend="canned")``.
    """
    def _factory(**overrides):
        cfg = Config()
        cfg.simulate = True
        cfg.tui = False
        cfg.scan_bluetooth = False
        for f in dataclasses.fields(cfg):
            v = getattr(cfg, f.name)
            if isinstance(v, str) and (v.startswith("~/.flippergotchi")
                                       or v.startswith("/tmp/")):
                setattr(cfg, f.name, str(tmp_path / f.name))
        for k, v in overrides.items():
            setattr(cfg, k, v)
        return cfg
    return _factory


@pytest.fixture
def cfg(make_cfg):
    """The canonical hermetic test Config (see ``make_cfg``)."""
    return make_cfg()


@pytest.fixture
def tmp_file(tmp_path):
    """Factory: path to ``name`` inside a FRESH subdirectory of tmp_path.

    Drop-in replacement for the old ``os.path.join(tempfile.mkdtemp(), name)``
    pattern -- every call still gets its own directory (so two "fresh" stores
    with the same filename never collide), but nothing leaks outside the
    test's tmp_path.
    """
    counter = itertools.count()

    def _make(name):
        d = tmp_path / "d{}".format(next(counter))
        d.mkdir()
        return str(d / name)
    return _make
