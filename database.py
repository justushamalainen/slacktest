"""Database operations for SQLite and PostgreSQL."""
import sqlite3
import json
from datetime import datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
import base64
from config import Config

# Import PostgreSQL driver if available
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

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
    """Database operations supporting both SQLite and PostgreSQL."""

    def __init__(self, db_type=None, db_path=None, db_url=None):
        self.db_type = db_type or Config.DATABASE_TYPE
        self.db_path = db_path or Config.DATABASE_PATH
        self.db_url = db_url or Config.DATABASE_URL

        # Validate database type
        if self.db_type not in ['sqlite', 'postgres']:
            raise ValueError(f"Unsupported database type: {self.db_type}")

        # Check if PostgreSQL is requested but not available
        if self.db_type == 'postgres' and not POSTGRES_AVAILABLE:
            raise ValueError("PostgreSQL support requires psycopg2-binary package")

        # Check if PostgreSQL URL is provided
        if self.db_type == 'postgres' and not self.db_url:
            raise ValueError("DATABASE_URL is required for PostgreSQL")

        self._ensure_database()

    def _ensure_database(self):
        """Create database and tables if they don't exist."""
        if self.db_type == 'sqlite':
            # Ensure directory exists for SQLite
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

            # Load SQLite schema
            schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
            with open(schema_path, 'r') as f:
                schema = f.read()

            conn = self.get_connection()
            conn.executescript(schema)
            conn.commit()
            conn.close()
        else:
            # Load PostgreSQL schema
            schema_path = os.path.join(os.path.dirname(__file__), 'schema_postgres.sql')
            with open(schema_path, 'r') as f:
                schema = f.read()

            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(schema)
            conn.commit()
            cursor.close()
            conn.close()

    def get_connection(self):
        """Get a database connection."""
        if self.db_type == 'sqlite':
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        else:
            conn = psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)
            return conn

    def _get_placeholder(self, index=1):
        """Get the appropriate parameter placeholder for the database type."""
        if self.db_type == 'sqlite':
            return '?'
        else:
            return f'${index}'

    def save_installation(self, team_id, team_name, bot_token, bot_user_id, scope):
        """Save or update an installation."""
        if not encryptor:
            raise ValueError("Encryption not configured")

        encrypted_token = encryptor.encrypt(bot_token)

        conn = self.get_connection()

        if self.db_type == 'sqlite':
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
        else:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO installations (team_id, team_name, bot_token, bot_user_id, scope, updated_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT(team_id) DO UPDATE SET
                    team_name = EXCLUDED.team_name,
                    bot_token = EXCLUDED.bot_token,
                    bot_user_id = EXCLUDED.bot_user_id,
                    scope = EXCLUDED.scope,
                    updated_at = CURRENT_TIMESTAMP
            """, (team_id, team_name, psycopg2.Binary(encrypted_token), bot_user_id, scope))
            conn.commit()
            cursor.close()

        conn.close()

    def get_installation(self, team_id):
        """Get installation by team_id."""
        conn = self.get_connection()

        if self.db_type == 'sqlite':
            cursor = conn.execute(
                "SELECT * FROM installations WHERE team_id = ?",
                (team_id,)
            )
            row = cursor.fetchone()
        else:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM installations WHERE team_id = %s",
                (team_id,)
            )
            row = cursor.fetchone()
            cursor.close()

        conn.close()

        if not row:
            return None

        if not encryptor:
            raise ValueError("Encryption not configured")

        # Convert row to dict
        if self.db_type == 'sqlite':
            row_dict = dict(row)
        else:
            row_dict = dict(row)

        # Handle bytea type for PostgreSQL
        bot_token_bytes = row_dict['bot_token']
        if self.db_type == 'postgres' and isinstance(bot_token_bytes, memoryview):
            bot_token_bytes = bytes(bot_token_bytes)

        return {
            'team_id': row_dict['team_id'],
            'team_name': row_dict['team_name'],
            'bot_token': encryptor.decrypt(bot_token_bytes),
            'bot_user_id': row_dict['bot_user_id'],
            'scope': row_dict['scope'],
            'installed_at': row_dict['installed_at']
        }

    def delete_installation(self, team_id):
        """Delete an installation."""
        conn = self.get_connection()

        if self.db_type == 'sqlite':
            conn.execute("DELETE FROM installations WHERE team_id = ?", (team_id,))
            conn.commit()
        else:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM installations WHERE team_id = %s", (team_id,))
            conn.commit()
            cursor.close()

        conn.close()

    def log_event(self, team_id, event_type, event_data):
        """Log an event for debugging."""
        conn = self.get_connection()

        if self.db_type == 'sqlite':
            conn.execute(
                "INSERT INTO event_log (team_id, event_type, event_data) VALUES (?, ?, ?)",
                (team_id, event_type, json.dumps(event_data))
            )
            conn.commit()
        else:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO event_log (team_id, event_type, event_data) VALUES (%s, %s, %s)",
                (team_id, event_type, json.dumps(event_data))
            )
            conn.commit()
            cursor.close()

        conn.close()

    def get_all_installations(self):
        """Get all installations (for admin purposes)."""
        conn = self.get_connection()

        if self.db_type == 'sqlite':
            cursor = conn.execute("SELECT team_id, team_name, bot_user_id FROM installations")
            rows = cursor.fetchall()
        else:
            cursor = conn.cursor()
            cursor.execute("SELECT team_id, team_name, bot_user_id FROM installations")
            rows = cursor.fetchall()
            cursor.close()

        conn.close()
        return [dict(row) for row in rows]

# Global database instance (only create if properly configured)
db = Database() if Config.ENCRYPTION_KEY else None
