"""Independent local GiroWatch accounts and revocable login sessions."""
import base64
import hashlib
from contextlib import contextmanager
import hmac
from http.cookies import SimpleCookie
from pathlib import Path
import re
import secrets
import sqlite3
import struct
import time
from urllib.parse import quote

COOKIE = 'girowatch_session'
SESSION_SECONDS = 604800
ITERATIONS = 600000
RESET_SECONDS = 600
SETUP_SECONDS = 900
USER_FIELDS = 'id,name,email,role,totp_secret IS NOT NULL'


class AccountError(ValueError):
    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra


# Authenticator app codes (RFC 6238: SHA-1, 6 digits, 30-second steps), as Google Authenticator expects.
def totp_code(secret, step):
    mac = hmac.new(base64.b32decode(secret), struct.pack('>Q', step), 'sha1').digest()
    offset = mac[19] & 15
    return f"{(struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7fffffff) % 1000000:06d}"


def match_totp(secret, code, after=-1, now=None):
    """Accepts one step of clock drift either way; a step at or before `after` was already used."""
    if not isinstance(code, str) or not re.fullmatch(r'\d{6}', code.replace(' ', '')):
        return None
    code, step = code.replace(' ', ''), int((time.time() if now is None else now) // 30)
    for candidate in (step - 1, step, step + 1):
        if candidate > after and hmac.compare_digest(totp_code(secret, candidate), code):
            return candidate
    return None


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()


def public_user(row):
    return {'id': row[0], 'name': row[1], 'email': row[2], 'role': 'Manager' if row[3] == 'Manager' else 'Member',
            'authenticator': bool(row[4])}


class Accounts:
    def __init__(self, root):
        self.path = Path(root) / 'web_data' / 'accounts.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
                    salt TEXT NOT NULL, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (
                    email TEXT PRIMARY KEY, count INTEGER NOT NULL, until REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS resets (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
            ''')
            # Columns added after the first release; existing accounts keep working.
            columns = {row[1] for row in db.execute('PRAGMA table_info(users)')}
            for name, kind in (('role', "TEXT NOT NULL DEFAULT 'Member'"), ('totp_secret', 'TEXT'),
                               ('totp_pending', 'TEXT'), ('totp_pending_at', 'REAL'), ('totp_last_step', 'INTEGER')):
                if name not in columns:
                    db.execute(f'ALTER TABLE users ADD COLUMN {name} {kind}')
            # The earliest account is the Manager when none is set (accounts created before roles existed).
            if not db.execute("SELECT 1 FROM users WHERE role='Manager'").fetchone():
                db.execute("UPDATE users SET role='Manager' WHERE rowid=(SELECT MIN(rowid) FROM users)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def needs_setup(self):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM users LIMIT 1').fetchone() is None

    @staticmethod
    def token(cookie):
        try:
            values = SimpleCookie()
            values.load(cookie or '')
            value = values[COOKIE].value if COOKIE in values else ''
            return value if re.fullmatch('[a-f0-9]{64}', value) else ''
        except Exception:
            return ''

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def current_user(self, cookie):
        token = self.token(cookie)
        if not token:
            return None
        with self.connect() as db:
            row = db.execute(f'''SELECT {', '.join('u.' + field for field in USER_FIELDS.split(','))} FROM sessions s
                JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?''',
                (self.digest(token), time.time())).fetchone()
        return public_user(row) if row else None

    @staticmethod
    def cookie(token='', age=SESSION_SECONDS):
        return f'{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}'

    @staticmethod
    def check_attempts(db, key):
        attempt = db.execute('SELECT count,until FROM attempts WHERE email=?', (key,)).fetchone()
        if attempt and attempt[0] >= 5 and attempt[1] > time.time():
            raise AccountError('Too many attempts. Try again in 15 minutes.', 429)
        return attempt

    @staticmethod
    def record_failure(db, key, attempt):
        count = attempt[0] + 1 if attempt and attempt[1] > time.time() else 1
        db.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?)', (key, count, time.time() + 900))
        db.commit()

    def sign_in(self, db, user_id):
        token = secrets.token_hex(32)
        db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
        db.execute('INSERT INTO sessions VALUES (?,?,?)', (self.digest(token), user_id, time.time() + SESSION_SECONDS))
        return self.cookie(token)

    @staticmethod
    def new_password(body):
        password = body.get('password', '')
        if not isinstance(password, str) or not 10 <= len(password) <= 256:
            raise AccountError('Enter a password of 10–256 characters.')
        salt = secrets.token_hex(16)
        return salt, password_hash(password, salt)

    def action(self, body, cookie=''):
        action = body.get('action')
        actor = self.current_user(cookie)
        if action == 'logout':
            with self.connect() as db:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (self.digest(self.token(cookie)),))
            return {'ok': True}, self.cookie(age=0)
        if action in ('people', 'reset', 'remove'):
            return self.manage_people(body, actor, cookie), None
        if action in ('authenticator-begin', 'authenticator-confirm', 'authenticator-remove'):
            return self.authenticator(body, actor), None
        if action == 'recover':
            return self.recover(body), None
        if action == 'recover-complete':
            return self.complete_recovery(body)
        if action not in ('create', 'login'):
            raise AccountError('Unknown account action.')
        email, password = body.get('email', ''), body.get('password', '')
        if not isinstance(email, str) or not isinstance(password, str):
            raise AccountError('Enter an email address and password.')
        email = email.strip().casefold()
        if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise AccountError('Enter a valid email address.')
        if len(password) > 256:
            raise AccountError('Password must be at most 256 characters.')
        with self.connect() as db:
            # Serialize first-account setup so simultaneous requests cannot both register.
            db.execute('BEGIN IMMEDIATE')
            setup = db.execute('SELECT 1 FROM users LIMIT 1').fetchone() is None
            row = db.execute('SELECT id,name,email,salt,password_hash FROM users WHERE email=?', (email,)).fetchone()
            if action == 'create':
                if not setup and not actor:
                    raise AccountError('Sign in to add an account.', 401)
                if not setup and actor['role'] != 'Manager':
                    raise AccountError('Only the Manager can add people.', 403)
                name = body.get('name', '')
                if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80 or len(password) < 10:
                    raise AccountError('Enter your name and a password of 10–256 characters.')
                if row:
                    raise AccountError('An account with this email already exists.', 409)
                salt = secrets.token_hex(16)
                user_id, role = secrets.token_hex(16), 'Manager' if setup else 'Member'
                db.execute('INSERT INTO users (id,name,email,salt,password_hash,role) VALUES (?,?,?,?,?,?)',
                           (user_id, name.strip(), email, salt, password_hash(password, salt), role))
                user = public_user((user_id, name.strip(), email, role, None))
                if not setup:
                    return {'created': True, 'user': user}, None
            else:
                attempt = self.check_attempts(db, email)
                salt = row[3] if row else '00' * 16
                if not row or not hmac.compare_digest(password_hash(password, salt), row[4]):
                    self.record_failure(db, email, attempt)
                    raise AccountError('Email or password is incorrect.', 401)
                db.execute('DELETE FROM attempts WHERE email=?', (email,))
                user = public_user(db.execute(f'SELECT {USER_FIELDS} FROM users WHERE id=?', (row[0],)).fetchone())
            return {'user': user}, self.sign_in(db, user['id'])

    def manage_people(self, body, actor, cookie):
        if not actor:
            raise AccountError('Sign in to continue.', 401)
        if actor['role'] != 'Manager':
            raise AccountError('Only the Manager can manage people.', 403)
        with self.connect() as db:
            if body.get('action') == 'people':
                rows = db.execute(f"SELECT {USER_FIELDS} FROM users ORDER BY role='Manager' DESC, name COLLATE NOCASE").fetchall()
                return {'people': [public_user(row) for row in rows]}
            user_id = body.get('userId', '')
            row = db.execute(f'SELECT {USER_FIELDS} FROM users WHERE id=?', (user_id,)).fetchone() if isinstance(user_id, str) else None
            if not row:
                raise AccountError('That person no longer exists.', 404)
            if body.get('action') == 'remove':
                if user_id == actor['id']:
                    raise AccountError('The Manager cannot remove their own account.')
                # Removing an account signs it out everywhere.
                db.execute('DELETE FROM users WHERE id=?', (user_id,))
                db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
                db.execute('DELETE FROM attempts WHERE email=?', (row[2],))
                return {'removed': True, 'user': public_user(row)}
            salt, hashed = self.new_password(body)
            db.execute('UPDATE users SET salt=?, password_hash=? WHERE id=?', (salt, hashed, user_id))
            # Sign the person out everywhere (except the Manager's own current session) and clear any lockout.
            db.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?', (user_id, self.digest(self.token(cookie))))
            db.execute('DELETE FROM attempts WHERE email=?', (row[2],))
            return {'reset': True, 'user': public_user(row)}

    def authenticator(self, body, actor):
        if not actor:
            raise AccountError('Sign in to continue.', 401)
        with self.connect() as db:
            row = db.execute('SELECT email,salt,password_hash,totp_pending,totp_pending_at FROM users WHERE id=?', (actor['id'],)).fetchone()
            attempt = self.check_attempts(db, row[0])
            if body.get('action') == 'authenticator-confirm':
                if not row[3] or (row[4] or 0) < time.time() - SETUP_SECONDS:
                    raise AccountError('Setup expired. Start again.')
                step = match_totp(row[3], body.get('code', ''))
                if step is None:
                    self.record_failure(db, row[0], attempt)
                    raise AccountError('That code is not right. Check the GiroWatch entry in your app and try again.')
                db.execute('UPDATE users SET totp_secret=totp_pending, totp_last_step=?, totp_pending=NULL, totp_pending_at=NULL WHERE id=?',
                           (step, actor['id']))
                db.execute('DELETE FROM attempts WHERE email=?', (row[0],))
                return {'user': {**actor, 'authenticator': True}}
            # Starting or removing setup needs the current password, so a borrowed session cannot swap the authenticator.
            password = body.get('password', '')
            if not isinstance(password, str) or not hmac.compare_digest(password_hash(password, row[1]), row[2]):
                self.record_failure(db, row[0], attempt)
                raise AccountError('Password is incorrect.', 401)
            db.execute('DELETE FROM attempts WHERE email=?', (row[0],))
            if body.get('action') == 'authenticator-remove':
                db.execute('UPDATE users SET totp_secret=NULL, totp_last_step=NULL, totp_pending=NULL, totp_pending_at=NULL WHERE id=?', (actor['id'],))
                return {'user': {**actor, 'authenticator': False}}
            secret = base64.b32encode(secrets.token_bytes(20)).decode()
            db.execute('UPDATE users SET totp_pending=?, totp_pending_at=? WHERE id=?', (secret, time.time(), actor['id']))
            return {'secret': secret, 'uri': f'otpauth://totp/GiroWatch:{quote(row[0])}?secret={secret}&issuer=GiroWatch&algorithm=SHA1&digits=6&period=30'}

    def recover(self, body):
        """Step 1: email + authenticator code. A correct code gives a 10-minute, single-use permission to set a new password."""
        email = body.get('email', '')
        if not isinstance(email, str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email.strip()) or len(email) > 254:
            raise AccountError('Enter a valid email address.')
        email, key = email.strip().casefold(), 'recover:' + email.strip().casefold()
        with self.connect() as db:
            attempt = self.check_attempts(db, key)
            row = db.execute('SELECT id,totp_secret,totp_last_step FROM users WHERE email=?', (email,)).fetchone()
            # Unknown emails, accounts without an authenticator and wrong codes all get the same answer.
            step = match_totp(row[1], body.get('code', ''), row[2] if row[2] is not None else -1) if row and row[1] else None
            if step is None:
                self.record_failure(db, key, attempt)
                raise AccountError('Email or code is incorrect.', 401)
            token = secrets.token_hex(32)
            db.execute('UPDATE users SET totp_last_step=? WHERE id=?', (step, row[0]))
            db.execute('DELETE FROM attempts WHERE email=?', (key,))
            db.execute('DELETE FROM resets WHERE expires<=?', (time.time(),))
            db.execute('INSERT INTO resets VALUES (?,?,?)', (self.digest(token), row[0], time.time() + RESET_SECONDS))
            return {'resetToken': token}

    def complete_recovery(self, body):
        """Step 2: the new password, accepted once per permission."""
        token = body.get('token', '')
        salt, hashed = self.new_password(body)
        with self.connect() as db:
            key = self.digest(token) if isinstance(token, str) and re.fullmatch('[a-f0-9]{64}', token) else ''
            reset = db.execute('SELECT user_id,expires FROM resets WHERE token_hash=?', (key,)).fetchone()
            db.execute('DELETE FROM resets WHERE token_hash=?', (key,))
            row = db.execute('SELECT email FROM users WHERE id=?', (reset[0],)).fetchone() if reset else None
            if not reset or reset[1] <= time.time() or not row:
                db.commit()
                raise AccountError('This reset has expired. Start again with a new code.', 410, expired=True)
            db.execute('UPDATE users SET salt=?, password_hash=? WHERE id=?', (salt, hashed, reset[0]))
            db.execute('DELETE FROM sessions WHERE user_id=?', (reset[0],))
            db.execute('DELETE FROM attempts WHERE email=?', (row[0],))
            user = public_user(db.execute(f'SELECT {USER_FIELDS} FROM users WHERE id=?', (reset[0],)).fetchone())
            return {'user': user}, self.sign_in(db, reset[0])
