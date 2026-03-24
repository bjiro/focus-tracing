#!/usr/bin/env python3
"""
Observer — capture daemon
Takes a screenshot every N minutes, sends to Claude for analysis,
appends structured entry to daily JSONL log.
"""

import os, sys, json, time, base64, datetime, subprocess, io, signal, argparse
from pathlib import Path
from PIL import ImageGrab, Image
import anthropic

# Load .env from project root
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip().lstrip("export ")
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# ── Config ────────────────────────────────────────────────────────────────────
INTERVAL_MINUTES = 5
IDLE_THRESHOLD_MINUTES = 5  # skip capture if no input for this long
LOG_DIR = Path.home() / ".traces" / "logs"
SCREENSHOT_DIR = Path.home() / ".traces" / "screenshots"
MODEL = "claude-haiku-4-5"
MAX_SCREENSHOT_DIM = 1280  # resize before sending to reduce tokens

ANALYZE_PROMPT = """\
You are observing someone's screen as part of a personal productivity tracker.
Analyze this screenshot and return a JSON object (no markdown, no backticks).

Required fields:
{
  "timestamp": "<ISO timestamp passed in>",
  "active_app": "<app name or browser>",
  "window_title": "<window/tab title if visible>",
  "category": "<one of: coding, research, writing, communication, media, terminal, design, admin, idle, other>",
  "task_summary": "<1-2 sentences: what the person is doing right now>",
  "content_type": "<creating | consuming | debugging | communicating | configuring | idle>",
  "learning_signal": "<null or 1 sentence if they appear to be learning something new>",
  "error_signal": "<null or 1 sentence if an error/bug/mistake is visible>",
  "tools_visible": ["<list of tools, languages, services visible>"],
  "confidence": <0.0-1.0 how confident you are in this analysis>
}

Be concise and factual. If the screen is blurry or unclear, reflect that in confidence.
"""

# ── Screenshot ────────────────────────────────────────────────────────────────
def take_screenshot() -> bytes:
    """Take a screenshot using PIL or fallback to scrot."""
    try:
        # Try PIL first (works on some X11 setups)
        img = ImageGrab.grab()
    except Exception:
        # Fallback: scrot
        tmp = Path("/tmp/observer_snap.png")
        result = subprocess.run(["scrot", str(tmp)], capture_output=True)
        if result.returncode != 0:
            # Try gnome-screenshot
            result = subprocess.run(
                ["gnome-screenshot", "-f", str(tmp)], capture_output=True
            )
        if result.returncode != 0:
            raise RuntimeError("No screenshot tool found. Install scrot: apt install scrot")
        img = Image.open(tmp)

    # Resize to reduce token cost
    w, h = img.size
    if max(w, h) > MAX_SCREENSHOT_DIM:
        scale = MAX_SCREENSHOT_DIM / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def save_screenshot(png_bytes: bytes, ts: str) -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    date = ts[:10]
    day_dir = SCREENSHOT_DIR / date
    day_dir.mkdir(exist_ok=True)
    fname = ts.replace(":", "-").replace("T", "_") + ".png"
    path = day_dir / fname
    path.write_bytes(png_bytes)
    return path


# ── Window metadata ────────────────────────────────────────────────────────────
def get_window_info() -> dict:
    info = {}
    # Try xdotool
    try:
        wid = subprocess.check_output(["xdotool", "getactivewindow"], stderr=subprocess.DEVNULL).decode().strip()
        title = subprocess.check_output(["xdotool", "getwindowname", wid], stderr=subprocess.DEVNULL).decode().strip()
        info["window_title_meta"] = title
    except Exception:
        pass
    # Try wmctrl
    try:
        out = subprocess.check_output(["wmctrl", "-lp"], stderr=subprocess.DEVNULL).decode()
        # get focused window from xprop
        focused = subprocess.check_output(["xprop", "-root", "_NET_ACTIVE_WINDOW"], stderr=subprocess.DEVNULL).decode()
        info["wmctrl_available"] = True
    except Exception:
        pass
    return info


# ── Idle detection ────────────────────────────────────────────────────────────
def get_idle_seconds() -> float | None:
    """Return seconds since last input using xprintidle, or None if unavailable."""
    try:
        ms = subprocess.check_output(["xprintidle"], stderr=subprocess.DEVNULL)
        return int(ms.strip()) / 1000
    except Exception:
        return None


# ── Claude analysis ────────────────────────────────────────────────────────────
def analyze_screenshot(client: anthropic.Anthropic, png_bytes: bytes, ts: str) -> dict:
    b64 = base64.standard_b64encode(png_bytes).decode()

    prompt = ANALYZE_PROMPT.replace("<ISO timestamp passed in>", ts)

    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()
    # Strip any accidental markdown fences
    raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
    try:
        entry = json.loads(raw)
    except json.JSONDecodeError:
        entry = {
            "timestamp": ts,
            "parse_error": True,
            "raw": raw,
            "task_summary": "Parse error",
            "category": "other",
            "confidence": 0.0,
        }

    entry["_meta"] = get_window_info()
    return entry


# ── Logging ───────────────────────────────────────────────────────────────────
def append_log(entry: dict):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    date = entry.get("timestamp", datetime.datetime.now().isoformat())[:10]
    log_path = LOG_DIR / f"{date}.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return log_path


# ── Main loop ─────────────────────────────────────────────────────────────────
def run_capture(interval_minutes: int, save_screenshots: bool):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    print(f"[Observer] Started. Capturing every {interval_minutes} min. Ctrl+C to stop.")

    def capture_once():
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        idle_secs = get_idle_seconds()
        if idle_secs is not None and idle_secs >= IDLE_THRESHOLD_MINUTES * 60:
            print(f"[{ts}] Idle ({idle_secs/60:.0f} min) — skipping.")
            append_log({"timestamp": ts, "category": "idle", "task_summary": "idle", "confidence": 1.0})
            return
        print(f"[{ts}] Capturing...", end=" ", flush=True)
        try:
            png = take_screenshot()
            if save_screenshots:
                save_screenshot(png, ts)
            entry = analyze_screenshot(client, png, ts)
            append_log(entry)
            print(f"✓ {entry.get('category','?')} — {entry.get('task_summary','')[:60]}")
        except Exception as e:
            print(f"✗ Error: {e}")
            append_log({"timestamp": ts, "error": str(e)})

    # Capture immediately, then on interval
    capture_once()

    try:
        while True:
            time.sleep(interval_minutes * 60)
            capture_once()
    except KeyboardInterrupt:
        print("\n[Observer] Stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Observer capture daemon")
    parser.add_argument("--interval", type=int, default=INTERVAL_MINUTES, help="Minutes between captures")
    parser.add_argument("--no-save-screenshots", action="store_true", help="Don't save screenshots to disk")
    args = parser.parse_args()
    run_capture(args.interval, not args.no_save_screenshots)