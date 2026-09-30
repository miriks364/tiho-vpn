import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import subprocess
import time
from contextlib import contextmanager

DB = os.getenv('TIHO_DB', '/var/lib/tiho/tiho.db')
SECRET = os.environ.get('TIHO_SECRET', '')
MOCK = os.getenv('TIHO_MOCK_WG') == '1'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def session_token(code, key):
    if len(SECRET) < 32:
        raise RuntimeError('TIHO_SECRET must contain at least 32 characters')
    return hmac.new(SECRET.encode(), f'{code}:{key}'.encode(), hashlib.sha256).hexdigest()


@contextmanager
def db():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init():
    os.makedirs(os.path.dirname(os.path.abspath(DB)), exist_ok=True)
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_hash TEXT NOT NULL UNIQUE,
            days INTEGER NOT NULL,
            expires INTEGER,
            key TEXT UNIQUE,
            token_hash TEXT UNIQUE,
            address TEXT UNIQUE,
            revoked INTEGER NOT NULL DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS attempts (
            bucket TEXT PRIMARY KEY, window INTEGER NOT NULL, count INTEGER NOT NULL
        )''')
    os.chmod(DB, 0o600)


def valid_key(key):
    try:
        raw = base64.b64decode(key, validate=True)
        return len(raw) == 32 and raw != bytes(32) and base64.b64encode(raw).decode() == key
    except Exception:
        return False


def wg(*args):
    if not MOCK:
        return subprocess.run(['/usr/bin/wg', *args], check=True, capture_output=True, text=True, timeout=10).stdout
    return ''


def remove(key):
    if key:
        wg('set', 'wg0', 'peer', key, 'remove')


def install_peer(key, address):
    wg('set', 'wg0', 'peer', key, 'allowed-ips', address + '/32')


def issue(days):
    if not 1 <= days <= 3650:
        raise ValueError('days must be 1..3650')
    code = secrets.token_urlsafe(24)
    with db() as c:
        cur = c.execute('INSERT INTO accounts(code_hash,days) VALUES (?,?)', (digest(code), days))
        return cur.lastrowid, code


def activate(code, key):
    if not valid_key(key):
        raise ValueError('Invalid key')
    now = int(time.time())
    with db() as c:
        row = c.execute('SELECT * FROM accounts WHERE code_hash=?', (digest(code),)).fetchone()
        if not row or row['revoked'] or (row['expires'] is not None and row['expires'] <= now):
            raise PermissionError()
        if row['key'] is not None and row['key'] != key:
            raise PermissionError()
        other = c.execute('SELECT id FROM accounts WHERE key=? AND id!=?', (key, row['id'])).fetchone()
        if other:
            raise PermissionError('Device already bound; extend existing account')
        # Retries from the same device return the same session, without extending time.
        token = session_token(code, key)
        expires = row['expires'] or now + row['days'] * 86400
        if row['address']:
            address = row['address']
        else:
            used = {r[0] for r in c.execute('SELECT address FROM accounts WHERE address IS NOT NULL')}
            address = next((f'10.66.{i//256}.{i%256}' for i in range(2, 65535) if f'10.66.{i//256}.{i%256}' not in used), None)
            if address is None:
                raise RuntimeError('Address pool exhausted')
        c.execute('UPDATE accounts SET key=?, token_hash=?, expires=?, address=? WHERE id=?', (key, digest(token), expires, address, row['id']))
        return {'token': token, 'expires_at': expires}


def connect(token):
    with db() as c:
        row = c.execute('SELECT * FROM accounts WHERE token_hash=?', (digest(token),)).fetchone()
        if not row or row['revoked'] or row['expires'] <= int(time.time()):
            raise PermissionError()
        install_peer(row['key'], row['address'])
        return {
            'expires_at': row['expires'], 'address': row['address'] + '/32',
            'server_public_key': os.environ['WG_PUBLIC_KEY'],
            'endpoint': os.environ['WG_ENDPOINT'], 'dns': '1.1.1.1, 1.0.0.1'
        }


def reconcile():
    # wg0 is managed exclusively by this service. Serialize against activations/connects.
    with db() as c:
        rows = c.execute('SELECT * FROM accounts WHERE key IS NOT NULL').fetchall()
        active = {r['key']: r for r in rows if not r['revoked'] and r['expires'] > int(time.time())}
        existing = set(wg('show', 'wg0', 'peers').split())
        for key in existing - active.keys():
            remove(key)
        for row in active.values():
            install_peer(row['key'], row['address'])


def rate_limit(ip):
    now = int(time.time())
    with db() as c:
        c.execute('DELETE FROM attempts WHERE window < ?', (now - 120,))
        for bucket, maximum in [('ip:' + ip, 12), ('global', 120)]:
            row = c.execute('SELECT * FROM attempts WHERE bucket=?', (bucket,)).fetchone()
            if not row or now - row['window'] >= 60:
                c.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?)', (bucket, now, 1))
            elif row['count'] >= maximum:
                return False
            else:
                c.execute('UPDATE attempts SET count=count+1 WHERE bucket=?', (bucket,))
    return True
