# Thinking Bot - Simple Distributed Slack App

A minimal distributed Slack app that responds with "thinking" to app mentions and direct messages. Built with Flask, SQLite, and the Slack SDK.

## Features

- Distributed OAuth installation (works with multiple workspaces)
- Encrypted token storage using AES-GCM
- Responds to app mentions with "thinking"
- Responds to direct messages with "thinking"
- SQLite database for local development
- Event signature verification
- Debug endpoints for development

## Project Structure

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
└── README.md                 # This file
```

## Prerequisites

- Python 3.8+
- ngrok (for local development)
- A Slack workspace where you can create apps

## Setup Instructions

### 1. Clone and Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Create Slack App

1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name it "Thinking Bot" and select your workspace
4. Navigate to "Basic Information" and note:
   - Client ID
   - Client Secret
   - Signing Secret

### 3. Configure Environment Variables

```bash
# Copy the example file
cp .env.example .env

# Generate encryption key
python -c "import secrets; print(secrets.token_hex(32))"

# Edit .env and fill in:
# - SLACK_CLIENT_ID
# - SLACK_CLIENT_SECRET
# - SLACK_SIGNING_SECRET
# - ENCRYPTION_KEY (from the command above)
# - PUBLIC_URL (will be set after ngrok starts)
```

### 4. Start ngrok

```bash
# In a separate terminal
ngrok http 3000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`) and update your `.env`:

```bash
PUBLIC_URL=https://abc123.ngrok.io
```

### 5. Configure Slack App Settings

#### OAuth & Permissions

Navigate to "OAuth & Permissions":

1. Add Redirect URL:
   ```
   https://your-ngrok-url.ngrok.io/slack/oauth_redirect
   ```

2. Add Bot Token Scopes:
   - `app_mentions:read` - View messages that mention your app
   - `chat:write` - Send messages as the bot
   - `channels:read` - View channels
   - `groups:read` - View private channels
   - `im:read` - View direct messages
   - `mpim:read` - View group direct messages

#### Event Subscriptions

Navigate to "Event Subscriptions":

1. Enable Events: Toggle ON
2. Set Request URL:
   ```
   https://your-ngrok-url.ngrok.io/slack/events
   ```
   (Your app must be running for this to verify!)

3. Subscribe to bot events:
   - `app_mention` - When users @mention the bot
   - `message.im` - Direct messages to bot

4. Save Changes

#### App Home

Navigate to "App Home":

1. Check "Allow users to send Slash commands and messages from the messages tab"

### 6. Start the App

```bash
python app.py
```

You should see:
```
Starting Thinking Bot on port 3000
Public URL: https://your-ngrok-url.ngrok.io
Environment: development
```

### 7. Install to Workspace

1. Open browser to `http://localhost:3000/slack/install`
2. Click "Add to Slack"
3. Select your workspace and click "Allow"
4. You should see a success page

### 8. Test the Bot

**Test App Mention:**
1. In Slack, invite the bot to a channel: `/invite @Thinking Bot`
2. Mention the bot: `@Thinking Bot hello`
3. Bot should respond: `thinking`

**Test Direct Message:**
1. Click on "Thinking Bot" in the Apps section
2. Send a message: `hello`
3. Bot should respond: `thinking`

## API Endpoints

- `GET /` - Home page with links
- `GET /slack/install` - OAuth installation page
- `GET /slack/oauth_redirect` - OAuth callback handler
- `POST /slack/events` - Slack event webhook
- `GET /health` - Health check endpoint
- `GET /debug/installations` - View installations (dev only)

## Database

The app uses SQLite for local development. The database includes:

- `installations` - Stores encrypted bot tokens per workspace
- `event_log` - Logs events for debugging

**Useful queries:**

```bash
# View all installations
sqlite3 data/slack_app.db "SELECT * FROM installations;"

# View recent events
sqlite3 data/slack_app.db "SELECT * FROM event_log ORDER BY created_at DESC LIMIT 10;"
```

## Debugging

### Bot not responding to mentions

1. Check if ngrok is running: `curl https://your-url.ngrok.io/health`
2. Check if Flask app is running (look for errors in terminal)
3. Verify bot is invited to channel: `/invite @Thinking Bot`
4. Check event log: `sqlite3 data/slack_app.db "SELECT * FROM event_log;"`

### OAuth installation fails

1. Verify Redirect URL matches in Slack app config
2. Check Client ID and Secret are correct in .env
3. Restart Flask app after changing .env
4. Verify ngrok URL hasn't changed

### Signature verification fails

1. Check `SLACK_SIGNING_SECRET` is correct
2. Restart Flask app after changing .env
3. Verify timestamp is recent (within 5 minutes)

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Viewing Logs

The app logs events to the `event_log` table for debugging:

```bash
sqlite3 data/slack_app.db "SELECT * FROM event_log ORDER BY created_at DESC LIMIT 5;"
```

## Production Deployment

For production deployment:

1. Generate a new encryption key
2. Use PostgreSQL instead of SQLite
3. Set up proper logging (not just print statements)
4. Use Redis for state storage instead of in-memory
5. Add background task processing for events
6. Enable HTTPS with proper certificates
7. Update Slack app configuration with production URLs

## Architecture

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

## Security Features

- Token encryption at rest using AES-GCM
- Request signature verification to prevent forgery
- Replay attack prevention (5-minute timestamp window)
- State parameter validation in OAuth flow
- Secure token storage with per-workspace encryption

## License

MIT
