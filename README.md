# Cursor Slack Hooks

Get Slack notifications whenever the Cursor AI agent needs your input. Each Cursor conversation maps to a Slack thread, with agent responses streamed in real-time and a full transcript uploaded when the agent stops.

## Features

- **Agent responses** posted to Slack as they happen (`afterAgentResponse` hook)
- **Stop notifications** when the agent finishes, errors, or is aborted (`stop` hook)
- **Threaded** — one Slack thread per Cursor conversation, titled with the first user message
- **Transcript file** uploaded on each stop, replacing the previous one

## Prerequisites

- Python 3 (comes with macOS)
- A Slack app with a Bot Token — no pip packages needed

## Slack App Setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app (or use an existing one)
2. Under **OAuth & Permissions**, add these Bot Token Scopes:
   - `chat:write`
   - `files:write`
   - `files:read` (optional, for debugging)
3. Install the app to your workspace
4. Copy the **Bot User OAuth Token** (`xoxb-...`)
5. Invite the bot to your target channel: `/invite @YourBotName`
6. Get the **Channel ID**: right-click the channel > "View channel details" > copy the ID at the bottom

## Installation

```bash
git clone <this-repo>
cd cursor-slack-hooks

# Set your Slack credentials (add to ~/.zshrc to persist)
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_CHANNEL_ID="C0123456789"

# Install hooks into ~/.cursor/
chmod +x install.sh
./install.sh
```

Restart Cursor to activate the hooks.

## How It Works

```
Cursor Agent Loop
    │
    ├── afterAgentResponse ──▶ notify-slack-response.sh
    │                              │
    │                              └── Posts agent response text
    │                                  to the conversation's Slack thread
    │
    └── stop ──▶ notify-slack.sh
                     │
                     ├── Posts stop notification (completed/error/aborted)
                     └── Uploads full transcript as .txt file
                         (replaces previous transcript)
```

### Thread Structure

```
#channel
  └── 🧵 Add cursor hooks for Slack notifications    ← thread root (first user query)
        ├── 🤖 Agent response — 14:30:01              ← afterAgentResponse
        │     Hello! This message shows up in Slack...
        ├── ✅ Agent finished. Your input is needed.   ← stop
        └── 📄 transcript-2026-02-13_14-30-05.txt     ← full transcript
```

## Files

| File | Description |
|------|-------------|
| `hooks.json` | Cursor hooks configuration |
| `hooks/slack_common.py` | Shared Slack API helpers + thread state management |
| `hooks/notify-slack-response.sh` | Posts each agent response to the thread |
| `hooks/notify-slack.sh` | Posts stop notification + uploads transcript |
| `install.sh` | Copies everything into `~/.cursor/` |

## Debugging

```bash
# View real-time hook logs
tail -f /tmp/cursor-slack-hook.log

# Check thread state
cat ~/.cursor/hooks/state/threads.json

# Test the stop hook manually
echo '{"status": "completed", "conversation_id": "test123"}' | ~/.cursor/hooks/notify-slack.sh
```

## Configuration

All configuration is via environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | Yes | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_CHANNEL_ID` | Yes | Channel ID to post notifications to |
