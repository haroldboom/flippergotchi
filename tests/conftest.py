"""Shared pytest fixtures.

The suite has several tests that (directly, or indirectly via the sim GPS wander
and the encounter capture roll) consume the process-global ``random`` module.
Without a fixed seed the pass/fail of those tests depended on collection order --
two were reproducibly flaky. Seed the global RNG before every test so results are
deterministic and order-independent; a test that needs a specific stream can still
reseed itself.
"""
import random

import pytest


@pytest.fixture(autouse=True)
def _seed_global_rng():
    random.seed(1234)
    yield
