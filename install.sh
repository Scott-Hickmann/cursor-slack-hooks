#!/bin/bash
# =============================================================================
# Install Cursor Slack hooks into ~/.cursor/
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CURSOR_DIR="$HOME/.cursor"

echo "Installing Cursor Slack hooks..."

# Copy hooks.json (back up existing)
if [ -f "$CURSOR_DIR/hooks.json" ]; then
    echo "  Backing up existing hooks.json -> hooks.json.bak"
    cp "$CURSOR_DIR/hooks.json" "$CURSOR_DIR/hooks.json.bak"
fi
cp "$SCRIPT_DIR/hooks.json" "$CURSOR_DIR/hooks.json"
echo "  Installed hooks.json"

# Copy hook scripts
mkdir -p "$CURSOR_DIR/hooks"
cp "$SCRIPT_DIR/hooks/slack_common.py" "$CURSOR_DIR/hooks/slack_common.py"
cp "$SCRIPT_DIR/hooks/notify-slack.sh" "$CURSOR_DIR/hooks/notify-slack.sh"
cp "$SCRIPT_DIR/hooks/notify-slack-response.sh" "$CURSOR_DIR/hooks/notify-slack-response.sh"
chmod +x "$CURSOR_DIR/hooks/notify-slack.sh" "$CURSOR_DIR/hooks/notify-slack-response.sh"
echo "  Installed hook scripts"

# Create state directory
mkdir -p "$CURSOR_DIR/hooks/state"

# Check for required env vars
echo ""
if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "WARNING: SLACK_BOT_TOKEN is not set."
    echo "  Add to ~/.zshrc:  export SLACK_BOT_TOKEN=\"xoxb-...\""
fi
if [ -z "$SLACK_CHANNEL_ID" ]; then
    echo "WARNING: SLACK_CHANNEL_ID is not set."
    echo "  Add to ~/.zshrc:  export SLACK_CHANNEL_ID=\"C...\""
fi

echo ""
echo "Done! Restart Cursor to activate hooks."
echo ""
echo "Debug logs: /tmp/cursor-slack-hook.log"
echo "Thread state: ~/.cursor/hooks/state/threads.json"
