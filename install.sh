#!/bin/bash
# =============================================================================
# Install Cursor Slack hooks into ~/.cursor/
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CURSOR_DIR="$HOME/.cursor"
SHELL_RC="$HOME/.zshrc"
[ -f "$SHELL_RC" ] || SHELL_RC="$HOME/.bashrc"

echo "=== Cursor Slack Hooks Installer ==="
echo ""

# -------------------------------------------------------------------------
# Prompt for credentials (pre-fill from env if already set)
# -------------------------------------------------------------------------

read -rp "Slack Bot Token (xoxb-...): " -i "$SLACK_BOT_TOKEN" INPUT_TOKEN
SLACK_BOT_TOKEN="${INPUT_TOKEN:-$SLACK_BOT_TOKEN}"

if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "Error: SLACK_BOT_TOKEN is required."
    echo "Create a Slack app at https://api.slack.com/apps with chat:write + files:write scopes."
    exit 1
fi

read -rp "Slack Channel ID (C...): " -i "$SLACK_CHANNEL_ID" INPUT_CHANNEL
SLACK_CHANNEL_ID="${INPUT_CHANNEL:-$SLACK_CHANNEL_ID}"

if [ -z "$SLACK_CHANNEL_ID" ]; then
    echo "Error: SLACK_CHANNEL_ID is required."
    echo "Right-click your channel in Slack > View channel details > copy the ID."
    exit 1
fi

# -------------------------------------------------------------------------
# Install hook files
# -------------------------------------------------------------------------

echo ""
echo "Installing hooks..."

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

# -------------------------------------------------------------------------
# Save credentials to shell profile
# -------------------------------------------------------------------------

echo ""

# Remove any existing SLACK_BOT_TOKEN / SLACK_CHANNEL_ID exports
if [ -f "$SHELL_RC" ]; then
    sed -i.bak '/^export SLACK_BOT_TOKEN=/d' "$SHELL_RC"
    sed -i.bak '/^export SLACK_CHANNEL_ID=/d' "$SHELL_RC"
    rm -f "${SHELL_RC}.bak"
fi

echo "export SLACK_BOT_TOKEN=\"$SLACK_BOT_TOKEN\"" >> "$SHELL_RC"
echo "export SLACK_CHANNEL_ID=\"$SLACK_CHANNEL_ID\"" >> "$SHELL_RC"
echo "  Saved credentials to $SHELL_RC"

# -------------------------------------------------------------------------
# Test connection
# -------------------------------------------------------------------------

echo ""
read -rp "Send a test message to Slack? (y/N): " TEST_CHOICE
if [[ "$TEST_CHOICE" =~ ^[Yy] ]]; then
    echo "  Sending test message..."
    RESULT=$(curl -s -X POST "https://slack.com/api/chat.postMessage" \
        -H "Content-Type: application/json; charset=utf-8" \
        -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
        -d "{\"channel\": \"$SLACK_CHANNEL_ID\", \"text\": \":white_check_mark: Cursor Slack hooks installed successfully!\"}")

    if echo "$RESULT" | python3 -c "import sys,json; sys.exit(0 if json.load(sys.stdin).get('ok') else 1)" 2>/dev/null; then
        echo "  Test message sent! Check your Slack channel."
    else
        ERROR=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','unknown'))" 2>/dev/null)
        echo "  Failed: $ERROR"
        echo "  Check your token and channel ID, and make sure the bot is invited to the channel."
    fi
fi

# -------------------------------------------------------------------------
# Done
# -------------------------------------------------------------------------

echo ""
echo "=== Installation complete ==="
echo ""
echo "Restart Cursor to activate hooks."
echo ""
echo "Debug logs:   /tmp/cursor-slack-hook.log"
echo "Thread state: ~/.cursor/hooks/state/threads.json"
