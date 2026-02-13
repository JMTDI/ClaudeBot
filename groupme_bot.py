"""
GroupMe AI Bot - Callback Server
Listens on port 8000 for GroupMe webhook callbacks and responds using Claude AI.

Setup:
1. pip install flask anthropic requests
2. Set environment variables:
   - ANTHROPIC_API_KEY: Your Anthropic API key
   - GROUPME_BOT_ID: Your GroupMe bot ID
3. Run: python groupme_bot.py
4. Use ngrok or similar to expose port 8000 publicly
5. Set your GroupMe bot's callback URL to: http://your-public-url/callback
"""

import os
import json
import requests
from flask import Flask, request, jsonify
from anthropic import Anthropic

app = Flask(__name__)

# --- Configuration ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "your_anthropic_api_key_here")
GROUPME_BOT_ID = os.environ.get("GROUPME_BOT_ID", "your_groupme_bot_id_here")
GROUPME_POST_URL = "https://api.groupme.com/v3/bots/post"
BOT_NAME = os.environ.get("BOT_NAME", "AI Assistant")  # Should match your GroupMe bot name

# Initialize Anthropic client
client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Conversation history per group (keyed by group_id)
# Stores last N messages to maintain context
conversation_history: dict[str, list] = {}
MAX_HISTORY = 20  # Max messages to keep per group for context


def send_groupme_message(text: str, bot_id: str = GROUPME_BOT_ID):
    """Send a message to GroupMe via the Bot API."""
    payload = {
        "bot_id": bot_id,
        "text": text,
    }
    try:
        resp = requests.post(GROUPME_POST_URL, json=payload, timeout=10)
        resp.raise_for_status()
        print(f"[GroupMe] Sent message: {text[:80]}...")
    except requests.RequestException as e:
        print(f"[GroupMe] Error sending message: {e}")


def get_claude_response(group_id: str, user_name: str, user_message: str) -> str:
    """Get a response from Claude, maintaining per-group conversation history."""
    # Initialize history for this group if needed
    if group_id not in conversation_history:
        conversation_history[group_id] = []

    history = conversation_history[group_id]

    # Add the new user message to history
    history.append({
        "role": "user",
        "content": f"{user_name}: {user_message}"
    })

    # Trim history if it exceeds max length
    if len(history) > MAX_HISTORY:
        conversation_history[group_id] = history[-MAX_HISTORY:]
        history = conversation_history[group_id]

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=500,
            system=(
                f"You are {BOT_NAME}, a helpful and friendly AI assistant in a GroupMe group chat. "
                "Keep responses concise (under 300 characters when possible) since this is a chat app. "
                "Be conversational, helpful, and engaging. "
                "Messages will be prefixed with the sender's name like 'Name: message'."
            ),
            messages=history,
        )

        assistant_reply = response.content[0].text

        # Add assistant reply to history
        history.append({
            "role": "assistant",
            "content": assistant_reply
        })

        return assistant_reply

    except Exception as e:
        print(f"[Claude] Error: {e}")
        return "Sorry, I ran into an issue processing that. Try again!"


@app.route("/callback", methods=["POST"])
def callback():
    """
    GroupMe webhook callback endpoint.
    GroupMe sends a POST request here whenever a message is sent in the group.
    """
    data = request.get_json(silent=True)

    if not data:
        print("[Webhook] Received empty or non-JSON payload")
        return jsonify({"status": "ignored"}), 200

    sender_type = data.get("sender_type", "")
    sender_name = data.get("name", "Someone")
    text = data.get("text", "").strip()
    group_id = data.get("group_id", "default")

    print(f"[Webhook] Message from '{sender_name}' (type={sender_type}): {text[:100]}")

    # Ignore messages sent by bots (including ourselves) to prevent infinite loops
    if sender_type == "bot":
        print("[Webhook] Ignoring bot message to prevent loop")
        return jsonify({"status": "ignored"}), 200

    # Ignore empty messages
    if not text:
        print("[Webhook] Ignoring empty message")
        return jsonify({"status": "ignored"}), 200

    # Get Claude's response and send it back to the group
    reply = get_claude_response(group_id, sender_name, text)
    send_groupme_message(reply)

    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "running",
        "bot_name": BOT_NAME,
        "bot_id_set": GROUPME_BOT_ID != "your_groupme_bot_id_here",
        "api_key_set": ANTHROPIC_API_KEY != "your_anthropic_api_key_here",
    }), 200


@app.route("/", methods=["GET"])
def index():
    return (
        "<h2>GroupMe AI Bot is running!</h2>"
    )


if __name__ == "__main__":
    print("=" * 50)
    print(f"  GroupMe AI Bot starting on port 8000")
    print(f"  Bot Name    : {BOT_NAME}")
    print(f"  Bot ID set  : {GROUPME_BOT_ID != 'your_groupme_bot_id_here'}")
    print(f"  API Key set : {ANTHROPIC_API_KEY != 'your_anthropic_api_key_here'}")
    print(f"  Callback URL: POST http://<your-host>:8000/callback")
    print("=" * 50)
    app.run(host="0.0.0.0", port=8000, debug=False)
