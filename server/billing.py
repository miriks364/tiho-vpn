"""Transactional Stars billing. No network calls; only Telegram bot worker may call settle()."""
import base64
import hashlib
import hmac
import json
import secrets
import time
import core

PLANS = {'m1': (30, 100), 'm3': (90, 270), 'y1': (365, 900)}


def init():
    core.init()
    with core.db() as c:
        statements = [
            '''CREATE TABLE IF NOT EXISTS customers (
                tg_id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL UNIQUE,
                nonce TEXT NOT NULL, last_reset INTEGER NOT NULL DEFAULT 0)''',
            '''CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, tg_id INTEGER NOT NULL, days INTEGER NOT NULL,
                stars INTEGER NOT NULL, created INTEGER NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0, paid INTEGER NOT NULL DEFAULT 0,
                terms_version TEXT NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS payments (
                charge TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE,
                tg_id INTEGER NOT NULL, account_id INTEGER NOT NULL, days INTEGER NOT NULL,
                stars INTEGER NOT NULL, paid_at INTEGER NOT NULL,
                refunded INTEGER NOT NULL DEFAULT 0)''',
            '''CREATE TABLE IF NOT EXISTS refund_events (
                charge TEXT PRIMARY KEY, tg_id INTEGER NOT NULL, payload TEXT NOT NULL,
                amount INTEGER NOT NULL, currency TEXT NOT NULL, created INTEGER NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY, dedupe TEXT NOT NULL UNIQUE, tg_id INTEGER NOT NULL,
                kind TEXT NOT NULL, payload TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 0,
                next_try INTEGER NOT NULL DEFAULT 0, sent INTEGER NOT NULL DEFAULT 0)''',
            '''CREATE TABLE IF NOT EXISTS inbox (
                update_id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0, tries INTEGER NOT NULL DEFAULT 0,
                next_try INTEGER NOT NULL DEFAULT 0)''',
            '''CREATE TABLE IF NOT EXISTS refund_jobs (charge TEXT PRIMARY KEY, done INTEGER NOT NULL DEFAULT 0, tries INTEGER NOT NULL DEFAULT 0, next_try INTEGER NOT NULL DEFAULT 0)''',
            'CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
        ]
        for sql in statements:
            c.execute(sql)


def code_for(tg_id, nonce):
    if len(core.SECRET) < 32:
        raise RuntimeError('Missing TIHO_SECRET')
    raw = hmac.new(core.SECRET.encode(), f'tiho-activation-v1:{tg_id}:{nonce}'.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def enqueue(c, dedupe, uid, kind, payload=None):
    c.execute('INSERT OR IGNORE INTO outbox(dedupe,tg_id,kind,payload) VALUES (?,?,?,?)',
              (dedupe, uid, kind, json.dumps(payload or {}, ensure_ascii=False)))


def order(uid, plan, terms='2026-09-v1', event=None):
    if plan not in PLANS:
        raise ValueError('Unknown plan')
    now = int(time.time())
    with core.db() as c:
        if event is not None:
            prior = c.execute('SELECT value FROM bot_state WHERE key=?', ('cb:'+event,)).fetchone()
            if prior:
                return prior['value']
        account = c.execute('SELECT a.revoked FROM customers u JOIN accounts a ON a.id=u.account_id WHERE u.tg_id=?', (uid,)).fetchone()
        if account and account['revoked']:
            raise PermissionError('Доступ отозван. Свяжись с поддержкой до покупки.')
        # Rate limit invoice spam; at most one invoice per user per 3 seconds.
        recent = c.execute('SELECT 1 FROM orders WHERE tg_id=? AND created>?', (uid, now-3)).fetchone()
        if recent:
            raise ValueError('Подожди несколько секунд перед новым счётом.')
        oid = secrets.token_urlsafe(24)
        days, stars = PLANS[plan]
        c.execute('INSERT INTO orders(id,tg_id,days,stars,created,terms_version) VALUES (?,?,?,?,?,?)', (oid, uid, days, stars, now, terms))
        if event is not None:
            c.execute('INSERT INTO bot_state VALUES (?,?)', ('cb:'+event, oid))
        enqueue(c, 'invoice:'+oid, uid, 'invoice', {'id': oid, 'days': days, 'stars': stars})
        return oid


def checkout(uid, payload, currency, amount):
    with core.db() as c:
        r = c.execute('SELECT * FROM orders WHERE id=?', (payload,)).fetchone()
        if not r or r['tg_id'] != uid or currency != 'XTR' or amount != r['stars'] or r['paid'] or r['created'] < int(time.time())-1800:
            return False
        a = c.execute('SELECT a.revoked FROM customers u JOIN accounts a ON a.id=u.account_id WHERE u.tg_id=?', (uid,)).fetchone()
        if a and a['revoked']:
            return False
        c.execute('UPDATE orders SET approved=1 WHERE id=?', (payload,))
        return True


def settle(uid, payment):
    """Only call on successful_payment from authenticated getUpdates, never client input."""
    charge = payment.get('telegram_payment_charge_id', '')
    if not isinstance(charge, str) or not 1 <= len(charge) <= 512:
        raise ValueError('Invalid charge')
    payload = payment.get('invoice_payload')
    now = int(time.time())
    with core.db() as c:
        r = c.execute('SELECT * FROM orders WHERE id=?', (payload,)).fetchone()
        if not r or r['tg_id'] != uid or payment.get('currency') != 'XTR' or payment.get('total_amount') != r['stars'] or not r['approved']:
            raise ValueError('Payment does not match an approved order')
        existing = c.execute('SELECT * FROM payments WHERE charge=?', (charge,)).fetchone()
        if existing:
            if existing['order_id'] != payload or existing['tg_id'] != uid:
                raise ValueError('Charge collision')
            return False
        if r['paid']:
            raise ValueError('Order already paid with another charge; manual refund required')
        user = c.execute('SELECT * FROM customers WHERE tg_id=?', (uid,)).fetchone()
        if not user:
            nonce = secrets.token_urlsafe(24)
            code = code_for(uid, nonce)
            cur = c.execute('INSERT INTO accounts(code_hash,days) VALUES (?,?)', (core.digest(code), r['days']))
            aid = cur.lastrowid
            c.execute('INSERT INTO customers(tg_id,account_id,nonce) VALUES (?,?,?)', (uid, aid, nonce))
        else:
            aid = user['account_id']
            a = c.execute('SELECT * FROM accounts WHERE id=?', (aid,)).fetchone()
            # Preserve administrative revocation if it happened after checkout.
            if a['revoked']:
                raise ValueError('Account revoked after checkout; support/refund required')
            if a['expires'] is None:
                c.execute('UPDATE accounts SET days=days+? WHERE id=?', (r['days'], aid))
            else:
                c.execute('UPDATE accounts SET expires=? WHERE id=?', (max(now, a['expires'])+r['days']*86400, aid))
        c.execute('INSERT INTO payments(charge,order_id,tg_id,account_id,days,stars,paid_at) VALUES (?,?,?,?,?,?,?)', (charge, payload, uid, aid, r['days'], r['stars'], now))
        c.execute('UPDATE orders SET paid=1 WHERE id=?', (payload,))
        # Refund can arrive before a delayed successful_payment is processed.
        refund = c.execute('SELECT * FROM refund_events WHERE charge=?', (charge,)).fetchone()
        if refund:
            _apply_refund(c, charge, refund['tg_id'], refund['payload'], refund['currency'], refund['amount'])
        enqueue(c, 'paid:'+charge, uid, 'access', {'paid_days': r['days']})
    return True


def access(uid):
    with core.db() as c:
        r = c.execute('SELECT a.*,u.nonce,u.last_reset FROM customers u JOIN accounts a ON a.id=u.account_id WHERE u.tg_id=?', (uid,)).fetchone()
        if not r:
            return None
        result = dict(r)
        # Do not give out an obsolete code after a local admin reset: regenerate via bot reset.
        code = code_for(uid, r['nonce'])
        result['code'] = code if core.digest(code) == r['code_hash'] else None
        return result


def reset_device(uid, event):
    now = int(time.time())
    with core.db() as c:
        if c.execute('SELECT 1 FROM outbox WHERE dedupe=?', ('reset:'+event,)).fetchone():
            return
        r = c.execute('SELECT a.*,u.last_reset FROM customers u JOIN accounts a ON a.id=u.account_id WHERE u.tg_id=?', (uid,)).fetchone()
        if not r or r['revoked'] or (r['expires'] is not None and r['expires'] <= now):
            raise PermissionError('Нет действующего доступа. Сначала оплати подписку.')
        if now - r['last_reset'] < 86400:
            raise PermissionError('Менять устройство можно раз в 24 часа. Для срочной смены обратись в поддержку.')
        # wg and DB updates serialized against /connect; failure rolls back without issuing code.
        core.remove(r['key'])
        nonce = secrets.token_urlsafe(24)
        code = code_for(uid, nonce)
        c.execute('UPDATE accounts SET key=NULL,token_hash=NULL,code_hash=? WHERE id=?', (core.digest(code), r['id']))
        c.execute('UPDATE customers SET nonce=?,last_reset=? WHERE tg_id=?', (nonce, now, uid))
        enqueue(c, 'reset:'+event, uid, 'access', {'reset': True})


def _apply_refund(c, charge, uid, payload, currency, amount):
    p = c.execute('SELECT * FROM payments WHERE charge=?', (charge,)).fetchone()
    if not p:
        return
    if p['tg_id'] != uid or p['order_id'] != payload or currency != 'XTR' or amount != p['stars']:
        raise ValueError('Refund mismatch')
    if p['refunded']:
        return
    a = c.execute('SELECT * FROM accounts WHERE id=?', (p['account_id'],)).fetchone()
    now = int(time.time())
    if a['expires'] is None:
        left = max(0, a['days'] - p['days'])
        c.execute('UPDATE accounts SET days=?,expires=? WHERE id=?', (left, None if left else now, a['id']))
    else:
        expires = max(now, a['expires'] - p['days']*86400)
        if expires <= now:
            core.remove(a['key'])
        c.execute('UPDATE accounts SET expires=? WHERE id=?', (expires, a['id']))
    c.execute('UPDATE payments SET refunded=1 WHERE charge=?', (charge,))
    enqueue(c, 'refund:'+charge, uid, 'text', {'text': 'Возврат Stars подтверждён. Купленные этим платежом дни удалены из оставшегося срока. Статус: /access'})


def refunded(uid, payment):
    charge = payment['telegram_payment_charge_id']
    payload = payment['invoice_payload']
    with core.db() as c:
        r = c.execute('SELECT * FROM orders WHERE id=?', (payload,)).fetchone()
        if not r or r['tg_id'] != uid or payment['currency'] != 'XTR' or payment['total_amount'] != r['stars']:
            raise ValueError('Unknown refund')
        c.execute('INSERT OR IGNORE INTO refund_events VALUES (?,?,?,?,?,?)', (charge, uid, payload, payment['total_amount'], payment['currency'], int(time.time())))
        _apply_refund(c, charge, uid, payload, payment['currency'], payment['total_amount'])
