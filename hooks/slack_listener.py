#!/usr/bin/env python3

# =============================================================================
# Slack Reply Listener — Polls Slack for human replies and injects into Cursor
# =============================================================================
# Background daemon that watches the most recent Cursor conversation thread
# in Slack for human replies, then uses macOS AppleScript to paste them into
# the Cursor chat input.
#
# Usage:
#   slack_listener.py start   [--interval N] [--shortcut KEY]
#   slack_listener.py stop
#   slack_listener.py status
#
# Requires:
#   - macOS (uses osascript for keyboard automation)
#   - Slack bot token with channels:history scope
#   - Accessibility permissions for the terminal app running the listener
# =============================================================================

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, Path(__file__).resolve().parent.as_posix())
from slack_common import (
    get_bot_user_id,
    get_most_recent_thread,
    get_thread_replies,
    log,
)

STATE_DIR = Path.home() / ".cursor" / "hooks" / "state"
LISTENER_STATE_FILE = STATE_DIR / "listener.json"
PID_FILE = STATE_DIR / "listener.pid"

DEFAULT_INTERVAL = 5  # seconds between polls
DEFAULT_SHORTCUT = "l"  # Cmd+<key> to open/focus chat input


# ---------------------------------------------------------------------------
# Listener state — tracks last-seen message ts per thread
# ---------------------------------------------------------------------------

def _load_listener_state():
    try:
        return json.loads(LISTENER_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_listener_state(state):
    LISTENER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LISTENER_STATE_FILE.write_text(json.dumps(state))


# ---------------------------------------------------------------------------
# AppleScript injection
# ---------------------------------------------------------------------------

def inject_message(message, shortcut_key):
    """Use AppleScript to paste *message* into the Cursor chat input.

    Steps:
      1. Set the macOS clipboard to the message text.
      2. Activate the Cursor application window.
      3. Press Cmd+<shortcut_key> to open/focus the chat input.
      4. Press Cmd+V to paste.
      5. Press Enter to send.
    """
    # Escape backslashes and double-quotes for AppleScript string literal
    escaped = message.replace("\\", "\\\\").replace('"', '\\"')

    script = (
        f'set the clipboard to "{escaped}"\n'
        f'tell application "Cursor" to activate\n'
        f"delay 0.5\n"
        f'tell application "System Events"\n'
        f'    keystroke "{shortcut_key}" using command down\n'
        f"    delay 0.3\n"
        f'    keystroke "v" using command down\n'
        f"    delay 0.1\n"
        f"    key code 36\n"  # Enter
        f"end tell\n"
    )

    try:
        subprocess.run(
            ["osascript", "-e", script],
            timeout=10,
            check=True,
            capture_output=True,
        )
        log(f"Injected Slack reply via AppleScript ({len(message)} chars)")
    except subprocess.TimeoutExpired:
        log("AppleScript injection timed out")
    except subprocess.CalledProcessError as e:
        log(f"AppleScript injection failed: {e.stderr.decode(errors='replace')}")
    except Exception as e:
        log(f"AppleScript injection error: {e}")


# ---------------------------------------------------------------------------
# Polling loop
# ---------------------------------------------------------------------------

def run_listener(interval, shortcut_key):
    """Main polling loop. Runs until SIGTERM/SIGINT."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))

    # Resolve the bot's own user ID so we can filter its messages
    bot_user_id = get_bot_user_id()
    log(f"Slack listener started (pid={os.getpid()}, interval={interval}s, "
        f"shortcut=Cmd+{shortcut_key}, bot_user_id={bot_user_id})")

    listener_state = _load_listener_state()

    # Graceful shutdown
    running = True

    def _handle_signal(signum, _frame):
        nonlocal running
        running = False
        log(f"Slack listener received signal {signum}, shutting down")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        while running:
            _conversation_id, thread_ts = get_most_recent_thread()
            if not thread_ts:
                time.sleep(interval)
                continue

            # Use last-seen ts for this thread, defaulting to thread_ts itself
            # (so we skip the root message on first poll)
            last_seen = listener_state.get(thread_ts, thread_ts)

            replies = get_thread_replies(thread_ts, oldest=last_seen)

            for msg in replies:
                msg_ts = msg.get("ts", "")

                # Skip already-processed messages (oldest is inclusive)
                if msg_ts <= last_seen:
                    continue

                # Skip the thread root message
                if msg_ts == thread_ts:
                    continue

                # Skip bot messages
                if msg.get("bot_id"):
                    listener_state[thread_ts] = msg_ts
                    continue
                if bot_user_id and msg.get("user") == bot_user_id:
                    listener_state[thread_ts] = msg_ts
                    continue

                text = msg.get("text", "").strip()
                if not text:
                    listener_state[thread_ts] = msg_ts
                    continue

                log(f"New human reply in thread {thread_ts}: "
                    f"{text[:80]}{'...' if len(text) > 80 else ''}")
                inject_message(text, shortcut_key)

                listener_state[thread_ts] = msg_ts

            _save_listener_state(listener_state)
            time.sleep(interval)
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        log("Slack listener stopped")


# ---------------------------------------------------------------------------
# Daemon helpers (start / stop / status)
# ---------------------------------------------------------------------------

def _read_pid():
    """Return the PID from the pidfile, or None."""
    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process is still alive
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def cmd_start(args):
    existing = _read_pid()
    if existing:
        print(f"Listener is already running (pid {existing}).")
        return

    # Fork into background (double-fork to detach from terminal)
    pid = os.fork()
    if pid > 0:
        # Parent — wait briefly for child to write pidfile
        time.sleep(0.5)
        child_pid = _read_pid()
        if child_pid:
            print(f"Slack listener started (pid {child_pid}).")
        else:
            print("Slack listener started in background.")
        return

    # First child — become session leader
    os.setsid()

    pid2 = os.fork()
    if pid2 > 0:
        # Exit first child so the daemon is fully detached
        os._exit(0)

    # Daemon process — redirect stdio to /dev/null
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)

    run_listener(args.interval, args.shortcut)
    os._exit(0)


def cmd_stop(_args):
    pid = _read_pid()
    if not pid:
        print("Listener is not running.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to listener (pid {pid}).")
        # Wait for it to exit
        for _ in range(20):
            time.sleep(0.25)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                print("Listener stopped.")
                return
        print("Listener did not exit in time; you may need to kill it manually.")
    except ProcessLookupError:
        print("Listener was not running.")
        PID_FILE.unlink(missing_ok=True)


def cmd_status(_args):
    pid = _read_pid()
    if pid:
        print(f"Listener is running (pid {pid}).")
    else:
        print("Listener is not running.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Slack reply listener for Cursor chat injection (macOS)")
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="Start the listener daemon")
    p_start.add_argument(
        "--interval", type=int, default=DEFAULT_INTERVAL,
        help=f"Polling interval in seconds (default: {DEFAULT_INTERVAL})")
    p_start.add_argument(
        "--shortcut", type=str, default=DEFAULT_SHORTCUT,
        help=f"Key for Cmd+<key> to focus chat input (default: {DEFAULT_SHORTCUT})")

    sub.add_parser("stop", help="Stop the listener daemon")
    sub.add_parser("status", help="Check if the listener is running")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
