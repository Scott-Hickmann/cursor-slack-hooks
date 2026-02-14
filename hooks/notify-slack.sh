#!/usr/bin/env python3

# =============================================================================
# Slack "stop" Hook — Status notification + transcript file (threaded)
# =============================================================================
# Posts the stop notification into the conversation's Slack thread.
# Uploads/replaces the transcript file attached to the root message.
#
# SETUP:
#   SLACK_BOT_TOKEN   — Bot User OAuth Token (xoxb-...) with chat:write + files:write scopes
#   SLACK_CHANNEL_ID  — Channel ID (e.g. C0123456789)
# =============================================================================

import json
import os
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parent.as_posix())
from slack_common import (
    SLACK_CHANNEL_ID,
    ensure_thread,
    get_thread_ts,
    get_transcript_file_id,
    log,
    post_message,
    save_transcript_file_id,
    slack_api_form,
    slack_api_json,
)


def delete_old_transcript(conversation_id):
    """Delete the previously uploaded transcript file, if any."""
    old_file_id = get_transcript_file_id(conversation_id)
    if not old_file_id:
        return
    try:
        result = slack_api_form("files.delete", {"file": old_file_id})
        if result.get("ok"):
            log(f"Deleted old transcript file: {old_file_id}")
        else:
            log(f"files.delete failed for {old_file_id}: {result.get('error', result)}")
    except Exception as e:
        log(f"files.delete exception: {e}")


def upload_transcript(transcript_path, status, timestamp, thread_ts, conversation_id):
    """Upload transcript to the thread root. Deletes any previous transcript first."""
    if not transcript_path or not os.path.isfile(transcript_path):
        log(f"No transcript file: {transcript_path}")
        return

    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        log(f"Failed to read transcript: {e}")
        return

    if not content.strip():
        log("Transcript file is empty")
        return

    # Delete old transcript before uploading new one
    delete_old_transcript(conversation_id)

    # Replace non-ASCII characters with ASCII so Slack doesn't classify as binary
    content = content.encode("ascii", errors="replace").decode("ascii")
    content_bytes = content.encode("utf-8")
    filename = f"transcript-{timestamp.replace(' ', '_').replace(':', '-')}.txt"

    # Step 1: Get an upload URL from Slack
    try:
        result = slack_api_form("files.getUploadURLExternal", {
            "filename": filename,
            "length": len(content_bytes),
        })
        if not result.get("ok"):
            log(f"files.getUploadURLExternal failed: {result.get('error', result)}")
            return
        upload_url = result["upload_url"]
        file_id = result["file_id"]
        log(f"Got upload URL for file_id: {file_id}")
    except Exception as e:
        log(f"files.getUploadURLExternal exception: {e}")
        return

    # Step 2: Upload the raw file content to the presigned URL
    try:
        req = urllib.request.Request(
            upload_url,
            data=content_bytes,
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=30)
        log(f"File content uploaded to presigned URL (HTTP {resp.status})")
    except Exception as e:
        log(f"File upload to presigned URL exception: {e}")
        return

    # Step 3: Complete the upload, sharing to the thread root
    try:
        params = {
            "files": json.dumps([{"id": file_id, "title": f"Cursor transcript ({status}) - {timestamp}"}]),
            "channel_id": SLACK_CHANNEL_ID,
        }
        if thread_ts:
            params["thread_ts"] = thread_ts
        result = slack_api_form("files.completeUploadExternal", params)
        if not result.get("ok"):
            log(f"files.completeUploadExternal failed: {result.get('error', result)}")
        else:
            # Save the new file_id so we can replace it next time
            save_transcript_file_id(conversation_id, file_id)
            log("Transcript uploaded to thread successfully")
    except Exception as e:
        log(f"files.completeUploadExternal exception: {e}")


def main():
    raw = sys.stdin.read()
    log(f"Hook invoked. Raw input length: {len(raw)}")

    try:
        hook_input = json.loads(raw)
    except json.JSONDecodeError:
        hook_input = {}

    status = hook_input.get("status", "unknown")
    transcript_path = hook_input.get("transcript_path")
    conversation_id = hook_input.get("conversation_id", "")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log(f"Status: {status}, transcript_path: {transcript_path}, conversation_id: {conversation_id}")

    emoji_map = {
        "completed": ":white_check_mark:",
        "error": ":x:",
        "aborted": ":octagonal_sign:",
    }
    text_map = {
        "completed": "Agent finished successfully. Your input is needed to continue.",
        "error": "Agent encountered an error. Please check and provide guidance.",
        "aborted": "Agent was aborted.",
    }
    emoji = emoji_map.get(status, ":bell:")
    text = text_map.get(
        status, f"Agent stopped (status: {status}). Your input may be needed."
    )

    comment = f"{emoji} {text}\n_Status: `{status}` | {timestamp}_"

    # Ensure thread exists, post stop notification as reply
    post_message(comment, conversation_id, transcript_path=transcript_path)
    thread_ts = get_thread_ts(conversation_id)

    # Upload/replace transcript on the thread root
    upload_transcript(transcript_path, status, timestamp, thread_ts, conversation_id)

    print("{}")


if __name__ == "__main__":
    main()
