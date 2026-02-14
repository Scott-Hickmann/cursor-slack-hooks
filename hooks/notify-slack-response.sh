#!/usr/bin/env python3

# =============================================================================
# Slack "afterAgentResponse" Hook — Streams each agent response to a thread
# =============================================================================

import json
import sys
from datetime import datetime

sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parent.as_posix())
from slack_common import log, post_message

MAX_TEXT_CHARS = 2900  # Slack block text limit is ~3000


def main():
    raw = sys.stdin.read()
    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        print("{}")
        return

    text = hook_input.get("text", "").strip()
    conversation_id = hook_input.get("conversation_id", "")
    transcript_path = hook_input.get("transcript_path")
    if not text or not conversation_id:
        print("{}")
        return

    timestamp = datetime.now().strftime("%H:%M:%S")

    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n... (truncated)"

    message = f":robot_face: *Agent response* — {timestamp}\n\n{text}"
    post_message(message, conversation_id, transcript_path=transcript_path)

    print("{}")


if __name__ == "__main__":
    main()
