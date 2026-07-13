CREATE TABLE IF NOT EXISTS user_profiles (
  user_id INTEGER PRIMARY KEY,
  agent TEXT,
  region TEXT,
  acquisition_channel TEXT,
  vip_level INTEGER,
  total_deposit REAL,
  total_deposit_count INTEGER,
  total_withdraw REAL,
  wallet_balance REAL,
  net_lifetime REAL,
  last_active_time TEXT,
  registered TEXT,
  recent_deposit_count_7d INTEGER,
  recent_activity_json TEXT,
  synced_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_agent ON user_profiles(agent);
