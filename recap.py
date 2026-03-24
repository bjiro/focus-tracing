#!/usr/bin/env python3
"""
Observer — end-of-day recap generator
Reads today's (or any date's) JSONL log and generates a structured recap.
"""

import os, sys, json, datetime, argparse
from pathlib import Path
from collections import defaultdict
import anthropic

# Load .env from project root
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip().lstrip("export ")
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

LOG_DIR = Path.home() / ".traces" / "logs"

RECAP_PROMPT = """\
You are analyzing a day's worth of activity log entries from a personal productivity tracker.
Each entry is a JSON object describing what was observed on the person's screen every few minutes.

Here are all the entries for today:

{entries}

Generate a structured end-of-day recap. Be direct, specific, and insightful. Avoid filler.

Format your response as JSON (no markdown, no backticks):
{
  "date": "<date>",
  "total_captures": <int>,
  "active_hours": "<estimated active time e.g. 4h 20min>",
  
  "time_breakdown": {
    "<category>": "<percentage and estimated time e.g. 45% — ~2h>"
  },
  
  "work_sessions": [
    {
      "time_range": "<e.g. 09:00–11:30>",
      "main_focus": "<what they were doing>",
      "tools": ["<tools used>"],
      "outcome": "<what seems to have been accomplished>"
    }
  ],
  
  "what_i_did": [
    "<bullet: specific task or activity completed>"
  ],
  
  "what_i_learned": [
    "<bullet: specific learning signal observed — null if none>"
  ],
  
  "mistakes_and_struggles": [
    "<bullet: specific error, bug, or struggle observed — null if none>"
  ],
  
  "patterns": [
    "<bullet: behavioral or work pattern worth noting — e.g. long idle at 14:00, frequent context switching>"
  ],
  
  "focus_score": <1-10, how focused and on-task the day appears>,
  "focus_comment": "<1 sentence explaining the score>",
  
  "tomorrow_suggestion": "<1 specific actionable suggestion based on today's patterns>"
}
"""


def load_log(date_str: str) -> list[dict]:
    log_path = LOG_DIR / f"{date_str}.jsonl"
    if not log_path.exists():
        return []
    entries = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def print_recap_pretty(recap: dict):
    """Print the recap in a readable terminal format."""
    print("\n" + "═" * 60)
    print(f"  OBSERVER RECAP — {recap.get('date', '?')}")
    print("═" * 60)

    print(f"\n📊 {recap.get('total_captures', '?')} captures | Active: {recap.get('active_hours', '?')} | Focus: {recap.get('focus_score', '?')}/10")
    print(f"   {recap.get('focus_comment', '')}")

    print("\n⏱  TIME BREAKDOWN")
    for cat, val in recap.get("time_breakdown", {}).items():
        print(f"   {cat:<18} {val}")

    print("\n✅ WHAT I DID")
    for item in recap.get("what_i_did", []):
        if item:
            print(f"   • {item}")

    learned = [x for x in recap.get("what_i_learned", []) if x]
    if learned:
        print("\n💡 WHAT I LEARNED")
        for item in learned:
            print(f"   • {item}")

    mistakes = [x for x in recap.get("mistakes_and_struggles", []) if x]
    if mistakes:
        print("\n⚠️  MISTAKES & STRUGGLES")
        for item in mistakes:
            print(f"   • {item}")

    patterns = [x for x in recap.get("patterns", []) if x]
    if patterns:
        print("\n🔍 PATTERNS")
        for item in patterns:
            print(f"   • {item}")

    sessions = recap.get("work_sessions", [])
    if sessions:
        print("\n🗓  WORK SESSIONS")
        for s in sessions:
            print(f"   [{s.get('time_range', '?')}] {s.get('main_focus', '')}")
            if s.get("tools"):
                print(f"   Tools: {', '.join(s['tools'])}")
            if s.get("outcome"):
                print(f"   → {s['outcome']}")
            print()

    suggestion = recap.get("tomorrow_suggestion")
    if suggestion:
        print(f"\n🚀 TOMORROW: {suggestion}")

    print("\n" + "═" * 60 + "\n")


def generate_recap(date_str: str, save: bool = True):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    entries = load_log(date_str)
    if not entries:
        print(f"No log entries found for {date_str}. Has the capture daemon run today?")
        sys.exit(0)

    print(f"Generating recap for {date_str} ({len(entries)} entries)...")

    entries_text = "\n".join(json.dumps(e) for e in entries)
    prompt = RECAP_PROMPT.replace("{entries}", entries_text)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()

    try:
        recap = json.loads(raw)
    except json.JSONDecodeError:
        print("Failed to parse recap JSON. Raw response:")
        print(raw)
        sys.exit(1)

    print_recap_pretty(recap)

    if save:
        recap_path = LOG_DIR / f"{date_str}_recap.json"
        with open(recap_path, "w") as f:
            json.dump(recap, f, indent=2)
        print(f"Recap saved to {recap_path}")

    return recap


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Observer end-of-day recap")
    parser.add_argument("--date", default=datetime.date.today().isoformat(), help="Date to recap (YYYY-MM-DD)")
    parser.add_argument("--no-save", action="store_true", help="Don't save recap to disk")
    args = parser.parse_args()
    generate_recap(args.date, not args.no_save)