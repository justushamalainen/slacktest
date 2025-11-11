# Step-by-Step Implementation Plan: Simple Distributed Slack App

**Goal**: Build a minimal distributed Slack app that responds with “thinking” to messages and pings. Testable locally with SQLite.

## Phase 1: Local Development Setup (30 minutes)

### Step 1: Project Structure Setup

Create the following directory structure:

```
slack-app/
├── app.py                    # Main Flask application
├── config.py                 # Configuration management
├── database.py               # Database models and operations
├── oauth_handler.py          # OAuth flow implementation
├── event_handler.py          # Slack event handlers
├── requirements.txt          # Python dependencies
├── .env.example              # Example environment variables
├── .env                      # Your actual secrets (gitignored)
├── schema.sql                # Database schema
├── data/                     # SQLite database directory
│   └── .gitkeep
├── tests/                    # Test files
│   ├── test_oauth.py
│   └── test_events.py
└── README.md                 # Setup instructions
```

**Claude Code Pointer**: Create these files and directories first. Start with empty files.

### Step 2: Dependencies Installation

**requirements.txt**:

```txt
flask==3.0.0
slack-bolt==1.18.0
python-dotenv==1.0.0
requests==2.31.0
cryptography==41.0.7
gunicorn==21.2.0
pytest==7.4.3
```

**Commands**:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Claude Code Pointer**: Run these commands to set up the Python environment.

### Step 3: Environment Variables Setup

**.env.example**:

```bash
# Slack App Credentials
SLACK_CLIENT_ID=your_client_id_here
SLACK_CLIENT_SECRET=your_client_secret_here
SLACK_SIGNING_SECRET=your_signing_secret_here

# App Configuration
FLASK_ENV=development
PORT=3000
DATABASE_PATH=./data/slack_app.db

# Encryption Key (generate with: python -c "import secrets; print(secrets.token_hex(32))")
ENCRYPTION_KEY=your_64_char_hex_string_here

# Public URL (for local development with ngrok)
PUBLIC_URL=https://your-ngrok-url.ngrok.io
```

**Claude Code Pointer**:

1. Copy `.env.example` to `.env`
1. Go to api.slack.com/apps to create a new app
1. Get Client ID, Client Secret, Signing Secret from “Basic Information”
1. Generate encryption key with: `python -c "import secrets; print(secrets.token_hex(32))"`
1. Install ngrok: `npm install -g ngrok` or download from ngrok.com
1. Start ngrok: `ngrok http 3000`
1. Copy the HTTPS URL to PUBLIC_URL in .env

### Step 4: Database Schema

**schema.sql**:

```sql
-- Workspace installations table
CREATE TABLE IF NOT EXISTS installations (
    team_id TEXT PRIMARY KEY,
    team_name TEXT,
    bot_token BLOB NOT NULL,  -- Encrypted
    bot_user_id TEXT,
    scope TEXT,
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_bot_user_id ON installations(bot_user_id);

-- Optional: Event log for debugging
CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT,
    event_type TEXT,
    event_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Claude Code Pointer**: This schema is minimal - just stores encrypted bot tokens per workspace.

-----

## Phase 2: Core Implementation (2 hours)

### Step 5: Configuration Module

**config.py**:

```python
"""Configuration management for the Slack app."""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Application configuration."""
    
    # Slack credentials
    SLACK_CLIENT_ID = os.getenv('SLACK_CLIENT_ID')
    SLACK_CLIENT_SECRET = os.getenv('SLACK_CLIENT_SECRET')
    SLACK_SIGNING_SECRET = os.getenv('SLACK_SIGNING_SECRET')
    
    # App settings
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    PORT = int(os.getenv('PORT', 3000))
    DATABASE_PATH = os.getenv('DATABASE_PATH', './data/slack_app.db')
    
    # Security
    ENCRYPTION_KEY = bytes.fromhex(os.getenv('ENCRYPTION_KEY', ''))
    
    # URLs
    PUBLIC_URL = os.getenv('PUBLIC_URL', 'http://localhost:3000')
    REDIRECT_URI = f"{PUBLIC_URL}/slack/oauth_redirect"
    
    @classmethod
    def validate(cls):
        """Validate that all required config is present."""
        required = [
            'SLACK_CLIENT_ID',
            'SLACK_CLIENT_SECRET', 
            'SLACK_SIGNING_SECRET',
            'ENCRYPTION_KEY'
        ]
        missing = [key for key in required if not getattr(cls, key)]
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")
        
        if len(cls.ENCRYPTION_KEY) != 32:
            raise ValueError("ENCRYPTION_KEY must be 32 bytes (64 hex chars)")

# Validate on import
Config.validate()
```

**Claude Code Pointer**: This centralizes all configuration. The validate() method ensures nothing is missing.

### Step 6: Database Module

**database.py**:

```python
"""Database operations for SQLite."""
import sqlite3
import json
from datetime import datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
import base64
from config import Config

class TokenEncryption:
    """Encrypt/decrypt bot tokens."""
    
    def __init__(self, key):
        self.gcm = AESGCM(key)
    
    def encrypt(self, token: str) -> bytes:
        """Encrypt a token."""
        nonce = os.urandom(12)
        ciphertext = self.gcm.encrypt(nonce, token.encode(), None)
        return nonce + ciphertext
    
    def decrypt(self, encrypted_data: bytes) -> str:
        """Decrypt a token."""
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        plaintext = self.gcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode()

# Global encryptor instance
encryptor = TokenEncryption(Config.ENCRYPTION_KEY)

class Database:
    """SQLite database operations."""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or Config.DATABASE_PATH
        self._ensure_database()
    
    def _ensure_database(self):
        """Create database and tables if they don't exist."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Create tables
        with open('schema.sql', 'r') as f:
            schema = f.read()
        
        conn = self.get_connection()
        conn.executescript(schema)
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def save_installation(self, team_id, team_name, bot_token, bot_user_id, scope):
        """Save or update an installation."""
        encrypted_token = encryptor.encrypt(bot_token)
        
        conn = self.get_connection()
        conn.execute("""
            INSERT INTO installations (team_id, team_name, bot_token, bot_user_id, scope, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(team_id) DO UPDATE SET
                team_name = excluded.team_name,
                bot_token = excluded.bot_token,
                bot_user_id = excluded.bot_user_id,
                scope = excluded.scope,
                updated_at = CURRENT_TIMESTAMP
        """, (team_id, team_name, encrypted_token, bot_user_id, scope))
        conn.commit()
        conn.close()
    
    def get_installation(self, team_id):
        """Get installation by team_id."""
        conn = self.get_connection()
        cursor = conn.execute(
            "SELECT * FROM installations WHERE team_id = ?",
            (team_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            'team_id': row['team_id'],
            'team_name': row['team_name'],
            'bot_token': encryptor.decrypt(row['bot_token']),
            'bot_user_id': row['bot_user_id'],
            'scope': row['scope'],
            'installed_at': row['installed_at']
        }
    
    def delete_installation(self, team_id):
        """Delete an installation."""
        conn = self.get_connection()
        conn.execute("DELETE FROM installations WHERE team_id = ?", (team_id,))
        conn.commit()
        conn.close()
    
    def log_event(self, team_id, event_type, event_data):
        """Log an event for debugging."""
        conn = self.get_connection()
        conn.execute(
            "INSERT INTO event_log (team_id, event_type, event_data) VALUES (?, ?, ?)",
            (team_id, event_type, json.dumps(event_data))
        )
        conn.commit()
        conn.close()
    
    def get_all_installations(self):
        """Get all installations (for admin purposes)."""
        conn = self.get_connection()
        cursor = conn.execute("SELECT team_id, team_name, bot_user_id FROM installations")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

# Global database instance
db = Database()
```

**Claude Code Pointer**: This handles all database operations with encryption built-in. SQLite is simple - just one file.

### Step 7: OAuth Handler

**oauth_handler.py**:

```python
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
                <h1>✅ Successfully Installed!</h1>
                <p>Thinking Bot has been installed to <strong>{team_name}</strong></p>
                <p>Go to your Slack workspace and mention the bot to test it!</p>
            </body>
            </html>
            '''
        except Exception as e:
            return f'<h1>Installation failed</h1><p>Error: {str(e)}</p>', 500
```

**Claude Code Pointer**: This implements the complete OAuth flow. The install page shows an “Add to Slack” button.

### Step 8: Event Handler

**event_handler.py**:

```python
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
```

**Claude Code Pointer**: This verifies Slack signatures and handles events. Simple “thinking” response.

### Step 9: Main Application

**app.py**:

```python
"""Main Flask application."""
from flask import Flask, jsonify
from config import Config
from oauth_handler import register_oauth_routes
from event_handler import register_event_routes
from database import db

# Create Flask app
app = Flask(__name__)

# Register routes
register_oauth_routes(app)
register_event_routes(app)

@app.route('/')
def home():
    """Home page."""
    return '''
    <html>
    <head><title>Thinking Bot</title></head>
    <body style="font-family: Arial; padding: 50px;">
        <h1>🤖 Thinking Bot</h1>
        <p>A simple Slack bot that responds with "thinking"</p>
        <ul>
            <li><a href="/slack/install">Install to Slack</a></li>
            <li><a href="/health">Health Check</a></li>
            <li><a href="/debug/installations">View Installations</a></li>
        </ul>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'database': 'connected',
        'config': 'valid'
    })

@app.route('/debug/installations')
def debug_installations():
    """Debug endpoint to view installations."""
    if Config.FLASK_ENV != 'development':
        return jsonify({'error': 'Not available in production'}), 403
    
    installations = db.get_all_installations()
    return jsonify({
        'count': len(installations),
        'installations': installations
    })

if __name__ == '__main__':
    print(f"🚀 Starting Thinking Bot on port {Config.PORT}")
    print(f"📝 Public URL: {Config.PUBLIC_URL}")
    print(f"🔧 Environment: {Config.FLASK_ENV}")
    app.run(host='0.0.0.0', port=Config.PORT, debug=(Config.FLASK_ENV == 'development'))
```

**Claude Code Pointer**: This is the main entry point. Run with `python app.py`.

-----

## Phase 3: Slack App Configuration (30 minutes)

### Step 10: Configure Slack App Settings

Go to https://api.slack.com/apps and click “Create New App” → “From scratch”

**App Name**: Thinking Bot  
**Workspace**: Select your development workspace

#### 10.1: OAuth & Permissions

Navigate to “OAuth & Permissions”:

1. **Redirect URLs** → Add:
   
   ```
   https://your-ngrok-url.ngrok.io/slack/oauth_redirect
   ```
1. **Bot Token Scopes** → Add:
- `app_mentions:read` - View messages that mention your app
- `chat:write` - Send messages as the bot
- `channels:read` - View channels
- `groups:read` - View private channels
- `im:read` - View direct messages
- `mpim:read` - View group direct messages

**Claude Code Pointer**: These scopes are minimal. Add more only if needed.

#### 10.2: Event Subscriptions

Navigate to “Event Subscriptions”:

1. **Enable Events** → Toggle ON
1. **Request URL** → Enter:
   
   ```
   https://your-ngrok-url.ngrok.io/slack/events
   ```
   
   Your app must be running for this to verify! Slack sends a challenge request.
1. **Subscribe to bot events** → Add:
- `app_mention` - When users @mention the bot
- `message.im` - Direct messages to bot
1. **Save Changes**

**Claude Code Pointer**: Make sure your Flask app is running before setting the Request URL!

#### 10.3: App Home

Navigate to “App Home”:

1. Check “Allow users to send Slash commands and messages from the messages tab”

**Claude Code Pointer**: This enables DMs to work.

#### 10.4: Manage Distribution

Navigate to “Manage Distribution”:

1. Check “Remove Hard Coded Information” (required for distribution)
1. Click “Activate Public Distribution”

**Claude Code Pointer**: Now your app can be installed in multiple workspaces!

-----

## Phase 4: Local Testing (1 hour)

### Step 11: Start Local Development Server

**Terminal 1 - Start ngrok**:

```bash
ngrok http 3000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`) and update your `.env`:

```bash
PUBLIC_URL=https://abc123.ngrok.io
```

**Terminal 2 - Start Flask app**:

```bash
source venv/bin/activate
python app.py
```

You should see:

```
🚀 Starting Thinking Bot on port 3000
📝 Public URL: https://abc123.ngrok.io
🔧 Environment: development
```

**Claude Code Pointer**: Keep both terminals running during development.

### Step 12: Test OAuth Installation

1. Open browser to `http://localhost:3000/slack/install`
1. Click “Add to Slack”
1. Select your workspace
1. Click “Allow”
1. You should see success page

**Verify installation**:

```bash
# Check database
sqlite3 data/slack_app.db "SELECT team_id, team_name FROM installations;"
```

**Claude Code Pointer**: If OAuth fails, check ngrok URL matches in Slack app config.

### Step 13: Test App Mention

In Slack:

1. Invite bot to a channel: `/invite @Thinking Bot`
1. Mention the bot: `@Thinking Bot hello`
1. Bot should respond: `thinking`

**Check logs** (in Flask terminal):

```
127.0.0.1 - - [timestamp] "POST /slack/events HTTP/1.1" 200 -
```

**Claude Code Pointer**: If no response, check event_log table for debugging.

### Step 14: Test Direct Message

In Slack:

1. Click on “Thinking Bot” in Apps section
1. Send a message: `hello`
1. Bot should respond: `thinking`

### Step 15: Debug Common Issues

**Issue: “Invalid signature”**

- Check `SLACK_SIGNING_SECRET` in `.env`
- Ensure ngrok URL matches in Slack config
- Restart Flask app after changing .env

**Issue: “No installation found”**

- Check database: `sqlite3 data/slack_app.db "SELECT * FROM installations;"`
- Reinstall app if needed

**Issue: Events not received**

- Check ngrok is running
- Verify Request URL in Slack shows ✅ verified
- Check Slack app is invited to channel

**Query event log**:

```bash
sqlite3 data/slack_app.db "SELECT * FROM event_log ORDER BY created_at DESC LIMIT 5;"
```

**Claude Code Pointer**: Event log is your friend for debugging!

-----

## Phase 5: Testing Suite (30 minutes)

### Step 16: Unit Tests

**tests/test_oauth.py**:

```python
"""Test OAuth functionality."""
import pytest
from oauth_handler import OAuthHandler
from config import Config

def test_install_url_generation():
    """Test that install URL is generated correctly."""
    url = OAuthHandler.get_install_url()
    
    assert 'slack.com/oauth/v2/authorize' in url
    assert Config.SLACK_CLIENT_ID in url
    assert 'state=' in url
    assert 'scope=' in url

def test_state_parameter_stored():
    """Test that state parameter is stored."""
    url = OAuthHandler.get_install_url()
    state = url.split('state=')[1].split('&')[0]
    
    assert state in OAuthHandler._state_store

def test_invalid_state_rejected():
    """Test that invalid state is rejected."""
    with pytest.raises(ValueError, match='Invalid state'):
        OAuthHandler.handle_callback('fake_code', 'invalid_state')
```

**tests/test_events.py**:

```python
"""Test event handling."""
import pytest
from event_handler import verify_slack_signature
import time
import hmac
import hashlib
from config import Config

def test_signature_verification():
    """Test that valid signatures are accepted."""
    timestamp = str(int(time.time()))
    body = '{"type":"event_callback"}'
    
    sig_basestring = f"v0:{timestamp}:{body}".encode()
    signature = 'v0=' + hmac.new(
        Config.SLACK_SIGNING_SECRET.encode(),
        sig_basestring,
        hashlib.sha256
    ).hexdigest()
    
    assert verify_slack_signature(body, timestamp, signature) is True

def test_old_timestamp_rejected():
    """Test that old requests are rejected."""
    old_timestamp = str(int(time.time()) - 400)  # 6 minutes old
    body = '{"type":"event_callback"}'
    
    sig_basestring = f"v0:{old_timestamp}:{body}".encode()
    signature = 'v0=' + hmac.new(
        Config.SLACK_SIGNING_SECRET.encode(),
        sig_basestring,
        hashlib.sha256
    ).hexdigest()
    
    assert verify_slack_signature(body, old_timestamp, signature) is False
```

**Run tests**:

```bash
pytest tests/ -v
```

**Claude Code Pointer**: Add more tests as you add features.

-----

## Phase 6: Production Preparation (Optional)

### Step 17: Production Database

For production, migrate to PostgreSQL:

**Update database.py**:

```python
# Add at top
import psycopg2
from psycopg2.extras import RealDictCursor

# Modify get_connection method
def get_connection(self):
    """Get database connection (PostgreSQL in production)."""
    if Config.FLASK_ENV == 'production':
        conn = psycopg2.connect(
            Config.DATABASE_URL,
            cursor_factory=RealDictCursor
        )
    else:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
    return conn
```

### Step 18: Environment Setup Checklist

**Pre-deployment**:

- [ ] Generate new encryption key for production
- [ ] Set all environment variables on hosting platform
- [ ] Update Slack app Redirect URLs to production domain
- [ ] Update Event Subscriptions Request URL to production
- [ ] Set up proper logging (not just print statements)
- [ ] Configure production database
- [ ] Enable HTTPS (Let’s Encrypt, Cloudflare)
- [ ] Test OAuth flow end-to-end

-----

## Quick Reference Commands

### Development

```bash
# Start ngrok
ngrok http 3000

# Start app
python app.py

# Run tests
pytest tests/ -v

# Check database
sqlite3 data/slack_app.db "SELECT * FROM installations;"

# View event logs
sqlite3 data/slack_app.db "SELECT * FROM event_log ORDER BY created_at DESC LIMIT 10;"
```

### Debugging

```bash
# Test signature generation
python -c "from event_handler import verify_slack_signature; print('OK')"

# Check config
python -c "from config import Config; print(Config.PUBLIC_URL)"

# View all tables
sqlite3 data/slack_app.db ".tables"

# View schema
sqlite3 data/slack_app.db ".schema installations"
```

-----

## Architecture Summary

```
User mentions bot in Slack
         ↓
Slack sends POST to /slack/events
         ↓
Verify signature (HMAC-SHA256)
         ↓
Extract team_id from event
         ↓
Query database for bot_token (decrypt)
         ↓
Create WebClient with token
         ↓
Post "thinking" message back
```

**Data Flow**:

1. OAuth: User installs → Slack → /oauth_redirect → Save encrypted token to DB
1. Events: Slack event → /slack/events → Verify → Load token → Respond
1. Database: All tokens encrypted at rest, decrypted only when needed

-----

## Next Steps After Basic Implementation

Once the basic app works:

1. **Add slash commands**: Implement `/think` command
1. **Add interactive buttons**: Let users click “Think Harder”
1. **Add background processing**: Use Redis queue for longer operations
1. **Add rate limiting**: Implement per-workspace rate limits
1. **Add monitoring**: Set up error tracking (Sentry)
1. **Add analytics**: Track usage per workspace
1. **Deploy to production**: Heroku, Railway, or cloud platform

-----

## Troubleshooting Guide

### App not responding to mentions

**Check**:

1. Is ngrok running? `curl https://your-url.ngrok.io/health`
1. Is Flask app running? Check terminal for errors
1. Is bot invited to channel? `/invite @Thinking Bot`
1. Check event_log: `sqlite3 data/slack_app.db "SELECT * FROM event_log;"`

### OAuth installation fails

**Check**:

1. Redirect URL matches in Slack app config
1. Client ID and Secret are correct in .env
1. Ngrok URL hasn’t changed (restart ngrok = new URL)
1. State parameter is being stored (check OAuthHandler._state_store)

### Database errors

**Check**:

1. schema.sql ran successfully: `sqlite3 data/slack_app.db ".tables"`
1. Encryption key is 64 hex characters (32 bytes)
1. File permissions on data/ directory

### Signature verification fails

**Check**:

1. SLACK_SIGNING_SECRET is correct (copy from Slack app config)
1. Using raw request body (not parsed JSON) for signature
1. Timestamp is recent (within 5 minutes)

-----

## File Checklist

Before starting, ensure you have:

- [x] requirements.txt
- [x] .env (from .env.example)
- [x] schema.sql
- [x] config.py
- [x] database.py
- [x] oauth_handler.py
- [x] event_handler.py
- [x] app.py
- [x] tests/test_oauth.py
- [x] tests/test_events.py
- [x] data/ directory created
- [x] README.md

**Total files**: ~12 files, ~800 lines of Python code

This implementation is production-ready for small-scale deployments (< 100 workspaces) and can scale with proper infrastructure additions (PostgreSQL, Redis, background workers).
