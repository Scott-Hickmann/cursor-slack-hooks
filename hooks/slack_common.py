"""Shared utilities for Cursor Slack hooks — API helpers + thread tracking."""

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

def _load_config():
    """Load credentials from config file, falling back to env vars."""
    config_file = Path.home() / ".cursor" / "hooks" / "state" / "config.json"
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = os.environ.get("SLACK_CHANNEL_ID", "")
    try:
        cfg = json.loads(config_file.read_text())
        token = token or cfg.get("SLACK_BOT_TOKEN", "")
        channel = channel or cfg.get("SLACK_CHANNEL_ID", "")
    except Exception:
        pass
    return token, channel

SLACK_BOT_TOKEN, SLACK_CHANNEL_ID = _load_config()

LOG = "/tmp/cursor-slack-hook.log"
STATE_FILE = Path.home() / ".cursor" / "hooks" / "state" / "threads.json"


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Slack API helpers
# ---------------------------------------------------------------------------

def slack_api_json(endpoint, payload_dict):
    """POST JSON to a Slack Web API endpoint. Returns parsed response."""
    data = json.dumps(payload_dict).encode("utf-8")
    req = urllib.request.Request(
        f"https://slack.com/api/{endpoint}",
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        },
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode("utf-8"))


def slack_api_form(endpoint, params):
    """POST form-encoded data to a Slack Web API endpoint. Returns parsed response."""
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        f"https://slack.com/api/{endpoint}",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        },
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# State tracking — one Slack thread per Cursor conversation
# State format: { conversation_id: { "thread_ts": "...", "file_id": "..." } }
# ---------------------------------------------------------------------------

def _load_state():
    try:
        data = json.loads(STATE_FILE.read_text())
        # Migrate old format (conversation_id -> thread_ts string)
        migrated = {}
        for k, v in data.items():
            if isinstance(v, str):
                migrated[k] = {"thread_ts": v}
            else:
                migrated[k] = v
        return migrated
    except Exception:
        return {}


def _save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Keep only the last 100 conversations
    if len(state) > 100:
        keys = sorted(state, key=lambda k: state[k].get("thread_ts", ""))
        for k in keys[:-100]:
            del state[k]
    STATE_FILE.write_text(json.dumps(state))


def get_thread_ts(conversation_id):
    """Return the Slack thread_ts for a conversation, or None."""
    entry = _load_state().get(conversation_id, {})
    return entry.get("thread_ts")


def get_transcript_file_id(conversation_id):
    """Return the previously uploaded transcript file_id, or None."""
    entry = _load_state().get(conversation_id, {})
    return entry.get("file_id")


def save_thread_ts(conversation_id, ts):
    """Store the thread_ts for a conversation."""
    state = _load_state()
    if conversation_id not in state:
        state[conversation_id] = {}
    state[conversation_id]["thread_ts"] = ts
    _save_state(state)


def save_transcript_file_id(conversation_id, file_id):
    """Store the transcript file_id for a conversation."""
    state = _load_state()
    if conversation_id not in state:
        state[conversation_id] = {}
    state[conversation_id]["file_id"] = file_id
    _save_state(state)


# ---------------------------------------------------------------------------
# Chat title extraction
# ---------------------------------------------------------------------------

def extract_chat_title(transcript_path):
    """Extract the first user query from the transcript to use as thread title."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        start_tag = "<user_query>"
        end_tag = "</user_query>"
        start = content.find(start_tag)
        if start == -1:
            return None
        start += len(start_tag)
        end = content.find(end_tag, start)
        if end == -1:
            return None
        query = content[start:end].strip()
        first_line = query.split("\n")[0].strip()
        if len(first_line) > 150:
            first_line = first_line[:147] + "..."
        return first_line
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Thread management
# ---------------------------------------------------------------------------

def ensure_thread(conversation_id, transcript_path=None):
    """Ensure a Slack thread exists for this conversation.
    Creates one using the chat title if it doesn't exist yet.
    Returns the thread_ts.
    """
    thread_ts = get_thread_ts(conversation_id)
    if thread_ts:
        return thread_ts

    title = extract_chat_title(transcript_path) if transcript_path else None
    if not title:
        title = "Cursor Agent Session"
    message = f":thread: *{title}*"

    try:
        result = slack_api_json("chat.postMessage", {
            "channel": SLACK_CHANNEL_ID,
            "text": message,
        })
        if not result.get("ok"):
            log(f"chat.postMessage (thread start) failed: {result.get('error', result)}")
            return None
        ts = result.get("ts")
        if ts:
            save_thread_ts(conversation_id, ts)
            log(f"Created thread for {conversation_id}: {ts}")
        return ts
    except Exception as e:
        log(f"chat.postMessage (thread start) exception: {e}")
        return None


def post_message(text, conversation_id, transcript_path=None):
    """Post a message as a reply in the conversation's thread.
    Creates the thread first if it doesn't exist yet.
    Returns the thread_ts.
    """
    thread_ts = ensure_thread(conversation_id, transcript_path)

    try:
        payload = {
            "channel": SLACK_CHANNEL_ID,
            "text": text,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts

        result = slack_api_json("chat.postMessage", payload)
        if not result.get("ok"):
            log(f"chat.postMessage failed: {result.get('error', result)}")
        return thread_ts
    except Exception as e:
        log(f"chat.postMessage exception: {e}")
        return thread_ts


# ---------------------------------------------------------------------------
# Bot identity
# ---------------------------------------------------------------------------

def get_bot_user_id():
    """Get the bot's own Slack user ID via auth.test.
    Used to filter out the bot's own messages when reading thread replies.
    Returns the user_id string, or None on failure.
    """
    try:
        result = slack_api_form("auth.test", {})
        if result.get("ok"):
            return result.get("user_id")
        log(f"auth.test failed: {result.get('error', result)}")
    except Exception as e:
        log(f"auth.test exception: {e}")
    return None


# ---------------------------------------------------------------------------
# Thread replies (reading messages back from Slack)
# ---------------------------------------------------------------------------

def get_thread_replies(thread_ts, oldest=None):
    """Fetch replies to a Slack thread.
    Requires the channels:history (public) or groups:history (private) scope.

    Args:
        thread_ts: The thread's root message timestamp.
        oldest: Only return messages newer than this timestamp (inclusive).

    Returns:
        A list of message dicts, or an empty list on failure.
    """
    params = {
        "channel": SLACK_CHANNEL_ID,
        "ts": thread_ts,
        "limit": 50,
    }
    if oldest:
        params["oldest"] = oldest
    try:
        result = slack_api_form("conversations.replies", params)
        if result.get("ok"):
            return result.get("messages", [])
        log(f"conversations.replies error: {result.get('error', result)}")
    except Exception as e:
        log(f"conversations.replies exception: {e}")
    return []


def get_most_recent_thread():
    """Return (conversation_id, thread_ts) for the most recently created thread.
    Returns (None, None) if no threads exist.
    """
    state = _load_state()
    if not state:
        return None, None
    latest_cid = None
    latest_ts = "0"
    for cid, entry in state.items():
        ts = entry.get("thread_ts", "0") if isinstance(entry, dict) else entry
        if ts > latest_ts:
            latest_ts = ts
            latest_cid = cid
    if latest_cid:
        return latest_cid, latest_ts
    return None, None
