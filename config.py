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
    ENCRYPTION_KEY = bytes.fromhex(os.getenv('ENCRYPTION_KEY', '')) if os.getenv('ENCRYPTION_KEY') else None

    # URLs
    PUBLIC_URL = os.getenv('PUBLIC_URL', 'http://localhost:3000')
    REDIRECT_URI = f"{PUBLIC_URL}/slack/oauth_redirect" if PUBLIC_URL else None

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

        if cls.ENCRYPTION_KEY and len(cls.ENCRYPTION_KEY) != 32:
            raise ValueError("ENCRYPTION_KEY must be 32 bytes (64 hex chars)")

# Only validate if not in a test environment
if os.getenv('FLASK_ENV') != 'test':
    try:
        Config.validate()
    except ValueError as e:
        print(f"⚠️  Configuration warning: {e}")
        print("Please copy .env.example to .env and fill in the required values.")
