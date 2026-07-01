# Deploying Flippergotchi as a service

This covers running Flippergotchi unattended (e.g. on a Flipper One or any Linux
box) via systemd, where it should survive reboots, save state cleanly on stop,
and find its config without a `-c` flag.

## 1. Install

```sh
pip install .           # provides the `flippergotchi` console script
# or, for the CPU AI backend:
pip install '.[ai-cpu]'
```

## 2. Config search path

`flippergotchi` runs with no `-c` by looking for a config file in this order and
using the **first that exists** (otherwise it runs on built-in defaults):

1. an explicit `-c/--config PATH`
2. `$FLIPPERGOTCHI_CONFIG`
3. `./flippergotchi.toml` (current working directory)
4. `~/.config/flippergotchi/config.toml`
5. `/etc/flippergotchi/config.toml`

For a service install, drop your config at `/etc/flippergotchi/config.toml`
(the shipped unit also sets `FLIPPERGOTCHI_CONFIG` to that path):

```sh
sudo install -Dm644 config.example.toml /etc/flippergotchi/config.toml
sudo $EDITOR /etc/flippergotchi/config.toml
```

## 3. State directory

All persistent JSON stores (state, bestiary, inventory, wallet, quests, ledger,
captures, audit log, ...) default under **`state_dir`** (`~/.flippergotchi`).
Override `state_dir` in the config to relocate **all** of them together:

```toml
state_dir = "/var/lib/flippergotchi"
```

Any per-store `*_path` still at its default is relocated under `state_dir`
automatically; explicitly-set `*_path` values are left where you put them.

> **systemd + HOME:** without `HOME` set, `expanduser("~")` returns a literal
> `~`, which would create `./~/.flippergotchi` in the service's working
> directory. Flippergotchi guards against this (falling back to
> `$STATE_DIRECTORY` or `/var/lib/flippergotchi`), but the unit still sets
> `HOME` explicitly so the default `~/.flippergotchi` resolves cleanly.

## 4. systemd unit

A ready-to-edit unit ships at [`packaging/flippergotchi.service`](../packaging/flippergotchi.service).

```sh
# create the service account (owns the radio + state)
sudo useradd --system --home-dir /var/lib/flippergotchi --shell /usr/sbin/nologin flippergotchi

sudo install -Dm644 packaging/flippergotchi.service /etc/systemd/system/flippergotchi.service
sudo $EDITOR /etc/systemd/system/flippergotchi.service   # set User=/HOME=/ExecStart path
sudo systemctl daemon-reload
sudo systemctl enable --now flippergotchi.service
journalctl -u flippergotchi -f
```

Key directives:

- `Restart=on-failure` — auto-recover from a crash.
- `AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW` — monitor mode + raw frame
  capture/injection without running as full root.
- `StateDirectory=flippergotchi` — systemd creates `/var/lib/flippergotchi`
  (0700, owned by `User=`) and exports `$STATE_DIRECTORY`.
- `Environment=HOME=/var/lib/flippergotchi` and an explicit `User=` — required
  so `~` and state resolution are deterministic (see above).
- `ExecStart=/usr/bin/flippergotchi` — the console script; adjust the path to
  match your install (`which flippergotchi`).

## 5. Clean shutdown

`systemctl stop` / shutdown sends `SIGTERM`. Flippergotchi installs a `SIGTERM`
(and `SIGINT`) handler that raises out of the tick loop and flushes all state via
the loop's `finally` block, so up to ~10 s of progress is no longer lost on every
stop. `TimeoutStopSec=20` leaves room for the final save.
