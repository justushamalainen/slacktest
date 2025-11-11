"""OAuth flow implementation."""
import requests
from flask import redirect, request, jsonify
from config import Config
from database import db
import secrets

class OAuthHandler:
    """Handle OAuth flow for Slack app installation."""

    # In-memory state store (for development - use Redis in production)
    _state_store = {}

    @staticmethod
    def get_install_url():
        """Generate the OAuth installation URL."""
        state = secrets.token_urlsafe(32)

        # Store state for 10 minutes
        OAuthHandler._state_store[state] = True

        scopes = [
            'app_mentions:read',
            'chat:write',
            'channels:read',
            'groups:read',
            'im:read',
            'mpim:read'
        ]

        params = {
            'client_id': Config.SLACK_CLIENT_ID,
            'scope': ','.join(scopes),
            'redirect_uri': Config.REDIRECT_URI,
            'state': state
        }

        param_string = '&'.join(f"{k}={v}" for k, v in params.items())
        return f"https://slack.com/oauth/v2/authorize?{param_string}"

    @staticmethod
    def handle_callback(code, state):
        """Handle OAuth callback and exchange code for token."""
        # Verify state
        if state not in OAuthHandler._state_store:
            raise ValueError("Invalid state parameter")

        # Remove used state
        del OAuthHandler._state_store[state]

        # Exchange code for token
        response = requests.post('https://slack.com/api/oauth.v2.access', data={
            'client_id': Config.SLACK_CLIENT_ID,
            'client_secret': Config.SLACK_CLIENT_SECRET,
            'code': code,
            'redirect_uri': Config.REDIRECT_URI
        })

        data = response.json()

        if not data.get('ok'):
            raise ValueError(f"OAuth error: {data.get('error')}")

        # Save installation
        db.save_installation(
            team_id=data['team']['id'],
            team_name=data['team']['name'],
            bot_token=data['access_token'],
            bot_user_id=data.get('bot_user_id'),
            scope=data.get('scope', '')
        )

        return data['team']['name']

def register_oauth_routes(app):
    """Register OAuth routes with Flask app."""

    @app.route('/slack/install')
    def install():
        """Show installation page."""
        install_url = OAuthHandler.get_install_url()
        return f'''
        <html>
        <head><title>Install Slack App</title></head>
        <body style="font-family: Arial; padding: 50px; text-align: center;">
            <h1>Install Thinking Bot</h1>
            <p>Click the button below to install the app to your workspace.</p>
            <a href="{install_url}"
               style="display: inline-block; background: #4A154B; color: white;
                      padding: 15px 30px; text-decoration: none; border-radius: 5px;">
                Add to Slack
            </a>
        </body>
        </html>
        '''

    @app.route('/slack/oauth_redirect')
    def oauth_redirect():
        """Handle OAuth callback."""
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')

        if error:
            return f'<h1>Installation cancelled</h1><p>Error: {error}</p>', 400

        if not code or not state:
            return '<h1>Missing required parameters</h1>', 400

        try:
            team_name = OAuthHandler.handle_callback(code, state)
            return f'''
            <html>
            <head><title>Installation Successful</title></head>
            <body style="font-family: Arial; padding: 50px; text-align: center;">
                <h1>Successfully Installed!</h1>
                <p>Thinking Bot has been installed to <strong>{team_name}</strong></p>
                <p>Go to your Slack workspace and mention the bot to test it!</p>
            </body>
            </html>
            '''
        except Exception as e:
            return f'<h1>Installation failed</h1><p>Error: {str(e)}</p>', 500
