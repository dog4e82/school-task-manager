"""Server-owned sessions and per-account data. Google credentials are encrypted."""

import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, directory, key, database_url=""):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "web.sqlite3"
        self.database_url = database_url
        self.cipher = Fernet(key.encode() if isinstance(key, str) else key)
        with self.db(initialize=True) as db:
            db.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, email TEXT NOT NULL, name TEXT NOT NULL, credentials BLOB NOT NULL);
              CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf TEXT NOT NULL, expires INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS oauth_states (
                id TEXT PRIMARY KEY, binding TEXT NOT NULL, payload BLOB NOT NULL, expires INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS snapshots (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, data TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS personal (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, item_id TEXT NOT NULL,
                data TEXT NOT NULL, PRIMARY KEY(user_id,item_id));
              CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
                reserved INTEGER NOT NULL, day TEXT NOT NULL, result TEXT, created BIGINT NOT NULL);
              CREATE UNIQUE INDEX IF NOT EXISTS one_active_job_per_user ON jobs(user_id)
                WHERE status IN ('queued','running');
              CREATE TABLE IF NOT EXISTS login_diagnostics (
                stage TEXT NOT NULL, result TEXT NOT NULL, attempts INTEGER NOT NULL,
                last_seen BIGINT NOT NULL, PRIMARY KEY(stage,result));
              CREATE TABLE IF NOT EXISTS oauth_runtime_config (
                component TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, updated BIGINT NOT NULL);
            """)

    @contextmanager
    def db(self, initialize=False):
        if self.database_url:
            from postgres_storage import Connection
            connection = Connection(self.database_url, initialize=initialize)
        else:
            connection = sqlite3.connect(self.path, timeout=15)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def encrypt(self, value):
        return self.cipher.encrypt(json.dumps(value).encode())

    def record_oauth_config(self, fingerprints):
        if (set(fingerprints) != {'client_id', 'client_secret', 'encryption_key'}
                or any(len(value) != 64 or any(c not in '0123456789abcdef' for c in value) for value in fingerprints.values())):
            raise ValueError('invalid_config_marker')
        with self.db() as db:
            for component, fingerprint in fingerprints.items():
                db.execute('INSERT INTO oauth_runtime_config VALUES (?,?,?) '
                           'ON CONFLICT(component) DO UPDATE SET fingerprint=excluded.fingerprint,updated=excluded.updated',
                           (component, fingerprint, time.time_ns() // 1000))

    def record_login(self, stage, result):
        """Bounded aggregate operational counters, with no account identifiers."""
        if stage not in {'start', 'callback', 'token', 'identity', 'permissions', 'storage', 'session'}:
            raise ValueError('invalid_login_stage')
        if result not in {'started', 'received', 'success', 'state_expired', 'denied', 'missing_scopes',
                          'invalid_client', 'invalid_grant', 'scope_changed', 'network', 'failed'}:
            raise ValueError('invalid_login_result')
        with self.db() as db:
            db.execute('INSERT INTO login_diagnostics VALUES (?,?,1,?) '
                       'ON CONFLICT(stage,result) DO UPDATE SET attempts=login_diagnostics.attempts+1,last_seen=excluded.last_seen',
                       (stage, result, time.time_ns() // 1000))

    def decrypt(self, value):
        return json.loads(self.cipher.decrypt(value))

    def begin_oauth(self, payload):
        state, binding = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("DELETE FROM oauth_states WHERE expires<?", (int(time.time()),))
            db.execute("INSERT INTO oauth_states VALUES (?,?,?,?)", (digest(state), digest(binding), self.encrypt(payload), int(time.time()) + 600))
        return state, binding

    def consume_oauth(self, state, binding):
        with self.db() as db:
            row = db.execute("DELETE FROM oauth_states WHERE id=? AND binding=? AND expires>? RETURNING payload",
                             (digest(state), digest(binding), int(time.time()))).fetchone()
            if row is None:
                return None
        return self.decrypt(row["payload"])

    def save_user(self, subject, email, name, credentials):
        user_id = digest("google:" + subject)
        with self.db() as db:
            db.execute("INSERT INTO users VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                       "email=excluded.email,name=excluded.name,credentials=excluded.credentials",
                       (user_id, email, name, self.encrypt(credentials)))
        return user_id

    def update_credentials(self, user_id, credentials):
        with self.db() as db:
            db.execute("UPDATE users SET credentials=? WHERE id=?", (self.encrypt(credentials), user_id))

    def get_user(self, user_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return {**dict(row), "credentials": self.decrypt(row["credentials"])} if row else None

    def create_session(self, user_id):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (int(time.time()),))
            db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (digest(token), user_id, csrf, int(time.time()) + 604800))
        return token

    def session(self, token):
        with self.db() as db:
            row = db.execute("SELECT user_id,csrf FROM sessions WHERE id=? AND expires>?", (digest(token), int(time.time()))).fetchone()
        return dict(row) if row else None

    def delete_session(self, token):
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE id=?", (digest(token),))

    def snapshot(self, user_id):
        with self.db() as db:
            row = db.execute("SELECT data FROM snapshots WHERE user_id=?", (user_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_snapshot(self, user_id, snapshot):
        with self.db() as db:
            db.execute("INSERT INTO snapshots VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
                       (user_id, json.dumps(snapshot, ensure_ascii=False)))

    def personal(self, user_id):
        with self.db() as db:
            rows = db.execute("SELECT item_id,data FROM personal WHERE user_id=?", (user_id,)).fetchall()
        return {row[0]: json.loads(row[1]) for row in rows}

    def save_personal(self, user_id, item_id, patch):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM personal WHERE user_id=? AND item_id=?", (user_id, item_id)).fetchone()
            value = {**(json.loads(row[0]) if row else {}), **patch}
            db.execute("INSERT INTO personal VALUES (?,?,?) ON CONFLICT(user_id,item_id) DO UPDATE SET data=excluded.data",
                       (user_id, item_id, json.dumps(value, ensure_ascii=False)))

    def new_job(self, user_id, kind, day, limit=0, daily_limit=3, global_limit=30):
        job_id = secrets.token_urlsafe(18)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= 20:
                raise ValueError("server_busy")
            if limit:
                used = db.execute("SELECT COALESCE(SUM(reserved),0) FROM jobs WHERE user_id=? AND day=? AND kind='analyze'", (user_id, day)).fetchone()[0]
                if used + limit > daily_limit:
                    raise ValueError("daily_limit")
                total = db.execute("SELECT COALESCE(SUM(reserved),0) FROM jobs WHERE day=? AND kind='analyze'", (day,)).fetchone()[0]
                if total + limit > global_limit:
                    raise ValueError("global_limit")
            db.execute("INSERT INTO jobs VALUES (?,?,?,'queued','대기 중',?,?,NULL,?)", (job_id, user_id, kind, limit, day, time.time_ns() // 1000))
        return job_id

    def finish_job(self, user_id, job_id, status, stage, result=None):
        with self.db() as db:
            db.execute("UPDATE jobs SET status=?,stage=?,result=? WHERE id=? AND user_id=?",
                       (status, stage, json.dumps(result, ensure_ascii=False), job_id, user_id))

    def job(self, user_id, job_id):
        with self.db() as db:
            row = db.execute("SELECT id,kind,status,stage,result FROM jobs WHERE user_id=? AND id=?", (user_id, job_id)).fetchone()
        if row is None:
            return None
        return {**dict(row), "result": json.loads(row["result"]) if row["result"] else None}

    def latest_job(self, user_id):
        with self.db() as db:
            row = db.execute("SELECT id FROM jobs WHERE user_id=? ORDER BY created DESC,id DESC LIMIT 1", (user_id,)).fetchone()
        return self.job(user_id, row[0]) if row else None

    def recover_jobs(self):
        with self.db() as db:
            db.execute("UPDATE jobs SET status='interrupted',stage='서버가 재시작되었습니다. 저장된 결과를 확인하세요.' WHERE status IN ('queued','running')")

    def delete_user(self, user_id):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM jobs WHERE user_id=? AND status IN ('queued','running')", (user_id,)).fetchone():
                raise ValueError("job_running")
            db.execute("DELETE FROM users WHERE id=?", (user_id,))
