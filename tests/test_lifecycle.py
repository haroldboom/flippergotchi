"""Hardware-readiness lifecycle plumbing (P1):

  * graceful shutdown on SIGTERM -> a single clean save (agent.run);
  * the default config search path (Config.load without -c);
  * configurable state_dir relocating default paths, and a HOME-unset-safe
    expanduser that never yields a literal '~' (systemd).

All hermetic: tmp paths only, never the real ~/.flippergotchi.
"""
from __future__ import annotations

import dataclasses
import os
import signal
import threading
import time

import pytest

from flippergotchi import config as config_mod
from flippergotchi.config import Config
from flippergotchi.agent import Agent
from flippergotchi.pet.state import PetState


def _cfg(tmp_path):
    """A sim Config with every persistence/render path redirected under tmp."""
    cfg = Config()
    cfg.simulate = True
    cfg.tui = False
    cfg.scan_bluetooth = False
    cfg.tick_interval = 0.01
    for f in dataclasses.fields(cfg):
        v = getattr(cfg, f.name)
        if isinstance(v, str) and (v.startswith("~/.flippergotchi") or v.startswith("/tmp/")):
            setattr(cfg, f.name, str(tmp_path / f.name))
    return cfg


# --------------------------------------------------------------------------- #
# 1. Graceful shutdown on SIGTERM
# --------------------------------------------------------------------------- #

def test_shutdown_handler_raises_keyboardinterrupt(tmp_path):
    agent = Agent(_cfg(tmp_path), PetState(name="T"))
    with pytest.raises(KeyboardInterrupt):
        agent._raise_shutdown(signal.SIGTERM, None)


def test_install_signal_handlers_off_main_thread_is_safe(tmp_path):
    """signal.signal() raises ValueError off the main thread; the guard must
    swallow it so tests / embedded use don't break -- nothing gets installed."""
    agent = Agent(_cfg(tmp_path), PetState(name="T"))
    out = {}

    def worker():
        out["saved"] = agent._install_signal_handlers()

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert out["saved"] == {}   # ValueError caught -> no handlers installed


def test_sigterm_triggers_single_clean_save(tmp_path):
    """A SIGTERM during the run loop exits through finally: self._save(), and
    _save() runs exactly once for the shutdown (no lost state)."""
    agent = Agent(_cfg(tmp_path), PetState(name="T"))
    calls = []
    orig_save = agent._save

    def spy():
        calls.append(1)
        orig_save()

    agent._save = spy
    # suppress the periodic (every-10s) save so we isolate the shutdown save
    agent._last_save = time.time()

    timer = threading.Timer(0.2, lambda: os.kill(os.getpid(), signal.SIGTERM))
    timer.start()
    try:
        agent.run()   # loops until SIGTERM -> KeyboardInterrupt -> finally save
    finally:
        timer.cancel()

    assert calls == [1]                       # saved exactly once
    assert (tmp_path / "state_path").exists()  # state actually flushed to disk
    # handlers restored to the default after run()
    assert signal.getsignal(signal.SIGTERM) in (signal.SIG_DFL, signal.default_int_handler)


# --------------------------------------------------------------------------- #
# 2. Default config search path
# --------------------------------------------------------------------------- #

def test_config_search_prefers_env_var(tmp_path, monkeypatch):
    f = tmp_path / "env.toml"
    f.write_text('name = "FromEnv"\n')
    monkeypatch.setenv("FLIPPERGOTCHI_CONFIG", str(f))
    monkeypatch.chdir(tmp_path)
    assert Config.load(None).name == "FromEnv"


def test_config_search_uses_cwd_file(tmp_path, monkeypatch):
    monkeypatch.delenv("FLIPPERGOTCHI_CONFIG", raising=False)
    (tmp_path / "flippergotchi.toml").write_text('name = "FromCwd"\n')
    monkeypatch.chdir(tmp_path)
    assert Config.load(None).name == "FromCwd"


def test_config_search_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("FLIPPERGOTCHI_CONFIG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))     # empty ~/.config
    monkeypatch.chdir(tmp_path)                    # empty cwd (no flippergotchi.toml)
    cfg = Config.load(None)
    assert cfg.name == "Flippy"                    # pure defaults


def test_config_load_explicit_path_unchanged(tmp_path):
    f = tmp_path / "explicit.toml"
    f.write_text('name = "Explicit"\n')
    assert Config.load(str(f)).name == "Explicit"
    # an explicit but missing path still falls back to pure defaults (unchanged)
    assert Config.load(str(tmp_path / "nope.toml")).name == "Flippy"


# --------------------------------------------------------------------------- #
# 3. Configurable state_dir + HOME-unset-safe path resolution
# --------------------------------------------------------------------------- #

def test_state_dir_relocates_default_paths(tmp_path):
    cfg = Config()
    cfg.state_dir = str(tmp_path / "state")
    cfg.apply_state_dir()
    assert cfg.state_path == str(tmp_path / "state" / "state.json")
    assert cfg.bestiary_path == str(tmp_path / "state" / "bestiary.json")
    assert cfg.wallet_path == str(tmp_path / "state" / "wallet.json")
    assert cfg.capture_dir == str(tmp_path / "state" / "captures")
    # ephemeral /tmp render outputs are NOT state -> left alone
    assert cfg.flipctl_html_out == "/tmp/flippergotchi/face.html"


def test_apply_state_dir_preserves_explicit_paths(tmp_path):
    cfg = Config()
    cfg.state_dir = str(tmp_path / "state")
    explicit = str(tmp_path / "custom" / "bestiary.json")
    cfg.bestiary_path = explicit
    cfg.apply_state_dir()
    # an explicitly-set (non-default) path is passed through untouched
    assert cfg.bestiary_path == explicit
    # while a still-default sibling is relocated under state_dir
    assert cfg.state_path == str(tmp_path / "state" / "state.json")


def test_resolve_path_expands_tilde_safely_without_home(monkeypatch):
    # Simulate systemd: expanduser cannot resolve HOME (returns "~..." verbatim).
    monkeypatch.setattr(os.path, "expanduser", lambda p: p)
    monkeypatch.delenv("STATE_DIRECTORY", raising=False)
    cfg = Config()
    cfg.apply_state_dir()
    for v in (cfg.state_dir, cfg.state_path, cfg.bestiary_path, cfg.capture_dir):
        assert not v.startswith("~")
        assert os.path.isabs(v)
    assert cfg.state_path == "/var/lib/flippergotchi/state.json"


def test_concrete_base_prefers_state_directory(monkeypatch):
    monkeypatch.setattr(os.path, "expanduser", lambda p: p)
    monkeypatch.setenv("STATE_DIRECTORY", "/srv/fg-state")
    cfg = Config()
    cfg.apply_state_dir()
    assert cfg.state_path == "/srv/fg-state/state.json"
    assert not cfg.state_path.startswith("~")


def test_safe_expanduser_never_yields_literal_tilde(monkeypatch):
    monkeypatch.setattr(os.path, "expanduser", lambda p: p)
    monkeypatch.delenv("STATE_DIRECTORY", raising=False)
    assert config_mod._safe_expanduser("~") == "/var/lib/flippergotchi"
    got = config_mod._safe_expanduser("~/.flippergotchi/state.json")
    assert not got.startswith("~") and os.path.isabs(got)
