import sqlite3
from datetime import date


def fmt(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:.2f}".rstrip('0')


class Database:
    def __init__(self, db_path="bot.db"):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id        INTEGER PRIMARY KEY,
                    username       TEXT DEFAULT '',
                    full_name      TEXT DEFAULT '',
                    balance        REAL DEFAULT 0,
                    referral_count INTEGER DEFAULT 0,
                    referrer_id    INTEGER DEFAULT NULL,
                    last_daily     TEXT DEFAULT NULL,
                    ref_rewarded   INTEGER DEFAULT 0,
                    created_at     TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    amount     REAL NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                );
            """)
            # Миграция: добавляем колонку если её нет (для существующих БД)
            try:
                conn.execute("ALTER TABLE users ADD COLUMN ref_rewarded INTEGER DEFAULT 0")
            except Exception:
                pass
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('daily_reward', '1')")
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('ref_reward', '3')")

    def register_user(self, user_id, username, full_name, referrer_id=None):
        with self._conn() as conn:
            existing = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if existing:
                conn.execute("UPDATE users SET username = ?, full_name = ? WHERE user_id = ?", (username, full_name, user_id))
                return False
            conn.execute("INSERT INTO users (user_id, username, full_name, referrer_id) VALUES (?, ?, ?, ?)", (user_id, username, full_name, referrer_id))
            if referrer_id and referrer_id != user_id:
                conn.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?", (referrer_id,))
            return True

    def get_user(self, user_id):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def add_balance(self, user_id, amount: float):
        with self._conn() as conn:
            conn.execute("UPDATE users SET balance = MAX(0, ROUND(balance + ?, 2)) WHERE user_id = ?", (amount, user_id))

    def set_balance(self, user_id, amount: float):
        with self._conn() as conn:
            conn.execute("UPDATE users SET balance = ROUND(?, 2) WHERE user_id = ?", (max(0.0, amount), user_id))

    def get_all_users(self):
        with self._conn() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY balance DESC").fetchall()]

    def get_user_count(self):
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def claim_daily(self, user_id):
        today = str(date.today())
        with self._conn() as conn:
            row = conn.execute("SELECT last_daily, referrer_id, ref_rewarded FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row and row["last_daily"] == today:
                return "already_claimed"
            reward = self.get_setting("daily_reward", 1.0)
            conn.execute("UPDATE users SET balance = ROUND(balance + ?, 2), last_daily = ? WHERE user_id = ?", (reward, today, user_id))

            # Начисляем реферальный бонус рефереру только 1 раз — при первом получении daily
            referrer_id = row["referrer_id"] if row else None
            ref_rewarded = row["ref_rewarded"] if row else 0
            ref_bonus_given = False
            if referrer_id and not ref_rewarded:
                ref_reward = self.get_setting("ref_reward", 3.0)
                conn.execute("UPDATE users SET balance = ROUND(balance + ?, 2), referral_count = referral_count + 1 WHERE user_id = ?", (ref_reward, referrer_id))
                conn.execute("UPDATE users SET ref_rewarded = 1 WHERE user_id = ?", (user_id,))
                ref_bonus_given = True

            return "claimed", referrer_id if ref_bonus_given else None

    def get_setting(self, key, default=None):
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if row:
                try:
                    val = float(row["value"])
                    return int(val) if val == int(val) else val
                except ValueError:
                    return row["value"]
            return default

    def set_setting(self, key, value):
        with self._conn() as conn:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))

    def get_top_balance(self, limit=10):
        with self._conn() as conn:
            return [dict(r) for r in conn.execute("SELECT full_name, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,)).fetchall()]

    def get_top_refs(self, limit=10):
        with self._conn() as conn:
            return [dict(r) for r in conn.execute("SELECT full_name, referral_count FROM users ORDER BY referral_count DESC LIMIT ?", (limit,)).fetchall()]

    def log_withdrawal(self, user_id, amount: float):
        with self._conn() as conn:
            conn.execute("INSERT INTO withdrawals (user_id, amount) VALUES (?, ?)", (user_id, amount))
