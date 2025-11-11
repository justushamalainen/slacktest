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
        if key is None:
            raise ValueError("Encryption key is required")
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

# Global encryptor instance (only if key is available)
encryptor = TokenEncryption(Config.ENCRYPTION_KEY) if Config.ENCRYPTION_KEY else None

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
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        with open(schema_path, 'r') as f:
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
        if not encryptor:
            raise ValueError("Encryption not configured")

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

        if not encryptor:
            raise ValueError("Encryption not configured")

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

# Global database instance (only create if properly configured)
db = Database() if Config.ENCRYPTION_KEY else None
