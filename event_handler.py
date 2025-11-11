"""Handle Slack events."""
from flask import request, jsonify
import hmac
import hashlib
import time
from config import Config
from database import db
from slack_sdk import WebClient

def verify_slack_signature(request_data, timestamp, signature):
    """Verify that the request came from Slack."""
    # Prevent replay attacks (reject requests older than 5 minutes)
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False

    # Create signature
    sig_basestring = f"v0:{timestamp}:{request_data}".encode()
    my_signature = 'v0=' + hmac.new(
        Config.SLACK_SIGNING_SECRET.encode(),
        sig_basestring,
        hashlib.sha256
    ).hexdigest()

    # Timing-safe comparison
    return hmac.compare_digest(my_signature, signature)

class EventHandler:
    """Handle Slack events."""

    @staticmethod
    def handle_event(event_data):
        """Route events to appropriate handlers."""
        event = event_data.get('event', {})
        event_type = event.get('type')
        team_id = event_data.get('team_id')

        # Log event
        db.log_event(team_id, event_type, event)

        # Get bot token for this workspace
        installation = db.get_installation(team_id)
        if not installation:
            print(f"No installation found for team {team_id}")
            return

        client = WebClient(token=installation['bot_token'])

        # Handle different event types
        if event_type == 'app_mention':
            EventHandler._handle_mention(client, event)
        elif event_type == 'message':
            EventHandler._handle_message(client, event, installation['bot_user_id'])

    @staticmethod
    def _handle_mention(client, event):
        """Handle app mention events."""
        channel = event.get('channel')
        user = event.get('user')

        # Respond with "thinking"
        client.chat_postMessage(
            channel=channel,
            text=f"thinking",
            thread_ts=event.get('thread_ts')  # Reply in thread if mentioned in thread
        )

    @staticmethod
    def _handle_message(client, event, bot_user_id):
        """Handle direct messages to the bot."""
        # Ignore bot's own messages
        if event.get('bot_id') or event.get('user') == bot_user_id:
            return

        # Only respond to direct messages (DMs)
        channel_type = event.get('channel_type')
        if channel_type == 'im':
            channel = event.get('channel')
            client.chat_postMessage(
                channel=channel,
                text="thinking"
            )

def register_event_routes(app):
    """Register event handling routes with Flask app."""

    @app.route('/slack/events', methods=['POST'])
    def slack_events():
        """Handle Slack events."""
        # Get raw request data for signature verification
        request_data = request.get_data().decode('utf-8')
        timestamp = request.headers.get('X-Slack-Request-Timestamp')
        signature = request.headers.get('X-Slack-Signature')

        # Verify signature
        if not verify_slack_signature(request_data, timestamp, signature):
            return jsonify({'error': 'Invalid signature'}), 403

        data = request.json

        # Handle URL verification challenge
        if data.get('type') == 'url_verification':
            return jsonify({'challenge': data.get('challenge')})

        # Handle event callback
        if data.get('type') == 'event_callback':
            # Process event asynchronously in production
            # For now, process directly (works for low volume)
            EventHandler.handle_event(data)

        # Always respond quickly (within 3 seconds)
        return jsonify({'status': 'ok'}), 200
