"""Password-based owner login backed by SQLite; passwords are never stored in plaintext."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
from contextlib import contextmanager
import hmac
import os
import re
import secrets
import sqlite3

ITERATIONS = 390_000
MAX_FAILURES = 6
LOCK_MINUTES = 10


def utcnow():
    return datetime.now(timezone.utc)


class AuthStore:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name TEXT NOT NULL DEFAULT '',
                password_digest TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                created_at TEXT NOT NULL,
                last_login TEXT,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT
            )""")
            # Compatible with older SQLite files created by MailPilot Pro.
            columns={row['name'] for row in db.execute('PRAGMA table_info(users)')}
            if 'name' not in columns:
                db.execute("ALTER TABLE users ADD COLUMN name TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            db.row_factory=sqlite3.Row
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def hash_password(password, salt=None):
        if not isinstance(password,str) or len(password)<12:
            raise ValueError('Choose a password with at least 12 characters.')
        salt=salt or secrets.token_bytes(16)
        digest=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,ITERATIONS)
        return f'pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}'

    @staticmethod
    def verify_password(password, encoded):
        try:
            algorithm, rounds, salt, digest=encoded.split('$')
            if algorithm!='pbkdf2_sha256': return False
            expected=bytes.fromhex(digest)
            actual=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),int(rounds))
            return hmac.compare_digest(actual,expected)
        except (ValueError,TypeError,AttributeError):
            return False

    def has_users(self):
        with self.connect() as db:
            return bool(db.execute('SELECT 1 FROM users LIMIT 1').fetchone())

    def has_owner(self):
        with self.connect() as db:
            return bool(db.execute("SELECT 1 FROM users WHERE role='owner' LIMIT 1").fetchone())

    def register_user(self, name, email, password):
        """Create a member account, never an owner account."""
        name=(name or '').strip()
        email=(email or '').strip().lower()
        if not (2 <= len(name) <= 100):
            raise ValueError('Enter a name between 2 and 100 characters.')
        if len(email)>254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError('Enter a valid email address.')
        encoded=self.hash_password(password)
        with self.connect() as db:
            try:
                cur=db.execute("""INSERT INTO users(name,email,password_digest,role,created_at)
                               VALUES(?,?,?,'member',?)""",(name,email,encoded,utcnow().isoformat()))
            except sqlite3.IntegrityError as exc:
                raise ValueError('An account with this email may already exist. Try signing in.') from exc
            return {'id':cur.lastrowid, 'name':name, 'email':email, 'role':'member'}

    def list_users(self):
        """Safe, non-secret administrator account listing."""
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT id,name,email,role,created_at,last_login
                FROM users ORDER BY created_at DESC""")]

    def create_owner(self, email, password):
        email=email.strip().lower()
        if '@' not in email or ' ' in email or '.' not in email.split('@')[-1]:
            raise ValueError('Enter a valid email address.')
        encoded=self.hash_password(password)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM users WHERE role='owner' LIMIT 1").fetchone():
                raise ValueError('An owner already exists. Use the password reset command.')
            db.execute("INSERT INTO users(email,password_digest,role,created_at) VALUES(?,?,'owner',?)",
                       (email,encoded,utcnow().isoformat()))

    def change_password(self,email,old_password,new_password):
        if not self.authenticate(email,old_password):
            return False
        encoded=self.hash_password(new_password)
        with self.connect() as db:
            db.execute('UPDATE users SET password_digest=?,failed_attempts=0,locked_until=NULL WHERE email=?',
                       (encoded,email.strip().lower()))
        return True

    def authenticate(self, email, password):
        email=(email or '').strip().lower()
        with self.connect() as db:
            row=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if row is None:
                # Do some password work even for nonexistent accounts.
                hashlib.pbkdf2_hmac('sha256',(password or '').encode(),b'unknown-user-login',ITERATIONS)
                return None
            if row['locked_until']:
                try:
                    if datetime.fromisoformat(row['locked_until'])>utcnow():
                        return None
                except ValueError:
                    pass
            ok=self.verify_password(password or '',row['password_digest'])
            if ok:
                db.execute("""UPDATE users SET failed_attempts=0,locked_until=NULL,last_login=? WHERE id=?""",
                           (utcnow().isoformat(),row['id']))
                return {'id':row['id'],'name':row['name'],'email':row['email'],'role':row['role']}
            failed=(row['failed_attempts'] or 0)+1
            until=(utcnow()+timedelta(minutes=LOCK_MINUTES)).isoformat() if failed>=MAX_FAILURES else None
            db.execute('UPDATE users SET failed_attempts=?,locked_until=? WHERE id=?',(failed,until,row['id']))
            return None


def bootstrap_owner(auth, config):
    """Use owner credentials from deployment secrets exactly once, never write plaintext."""
    if auth.has_owner(): return False
    email=config.get('MAILPILOT_ADMIN_EMAIL','')
    password=config.get('MAILPILOT_ADMIN_PASSWORD','')
    if email and password:
        auth.create_owner(email,password)
        return True
    return False
