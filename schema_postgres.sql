-- PostgreSQL schema for Slack App

-- Workspace installations table
CREATE TABLE IF NOT EXISTS installations (
    team_id TEXT PRIMARY KEY,
    team_name TEXT,
    bot_token BYTEA NOT NULL,  -- Encrypted
    bot_user_id TEXT,
    scope TEXT,
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_bot_user_id ON installations(bot_user_id);

-- Optional: Event log for debugging
CREATE TABLE IF NOT EXISTS event_log (
    id SERIAL PRIMARY KEY,
    team_id TEXT,
    event_type TEXT,
    event_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
