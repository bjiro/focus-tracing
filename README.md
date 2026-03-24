# Traces

Personal AI activity tracker. Screenshots your screen every N minutes and gather pertinent data, analyzes with Claude, generates daily recaps.

## Setup

```bash
uv venv
uv init .
puv add anthropic pillow
sudo apt install scrot  
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### Start capturing
```bash
uv run capture.py                    # default: every 5 min
uv run capture.py --interval 10      # every 10 min
uv run capture.py --no-save-screenshots  # analyze only, no disk storage
```

Logs go to: `~/.observer/logs/YYYY-MM-DD.jsonl`
Screenshots: `~/.observer/screenshots/YYYY-MM-DD/`

### End-of-day recap
```bash
uv run recap.py                      # today
uv run recap.py --date 2025-03-22    # specific day
```

Recap saved to: `~/.observer/logs/YYYY-MM-DD_recap.json`

### Dashboard
Open `dashboard.html` in a browser, then load a `_recap.json` or `.jsonl` file.

## Run as background service (systemd)

```ini
# ~/.config/systemd/user/observer.service
[Unit]
Description=Observer capture daemon

[Service]
ExecStart=/usr/bin/python3 /path/to/observer/capture.py --interval 5
Environment=ANTHROPIC_API_KEY=sk-ant-...
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable observer
systemctl --user start observer
```

## Cost estimate
- ~100 captures/day at 5-min intervals
- ~800 tokens/capture (image + response)
- ≈ $1–2/day with claude-opus, $0.10–0.20 with claude-haiku
- Switch model in capture.py: MODEL = "claude-haiku-4-5" for cheaper runs