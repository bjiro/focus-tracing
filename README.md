# focus-tracing

Screenshots your screen every few minutes, analyzes with Claude, generates daily recaps.

## Setup

```bash
cp .env.example .env  # add your ANTHROPIC_API_KEY
sudo apt install scrot xprintidle
uv sync
```

## Usage

```bash
uv run capture.py                     # capture every 5 min
uv run capture.py --interval 10       # custom interval
uv run recap.py                       # recap for today
uv run recap.py --date 2026-03-24     # specific day
```

Logs: `~/.traces/logs/YYYY-MM-DD.jsonl`
Screenshots: `~/.traces/screenshots/YYYY-MM-DD/`

Open `dashboard.html` in a browser to visualize a recap or log file.

## Run as a daemon

```bash
./install-daemon.sh
```

```bash
systemctl --user status focus-tracing
journalctl --user -u focus-tracing -f
```

## Cost

~100 captures/day. Haiku (~$0.10–0.20/day) is recommended for capture; Opus for recap.
