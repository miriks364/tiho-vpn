#!/usr/bin/env python3
import argparse
import datetime
import time
import core

p = argparse.ArgumentParser(description='Local Tiho VPN account administration')
s = p.add_subparsers(dest='command', required=True)
a = s.add_parser('issue'); a.add_argument('--days', type=int, required=True)
s.add_parser('list')
a = s.add_parser('extend'); a.add_argument('id', type=int); a.add_argument('--days', type=int, required=True)
a = s.add_parser('revoke'); a.add_argument('id', type=int)
a = s.add_parser('reset-device'); a.add_argument('id', type=int)
args = p.parse_args(); core.init()
if args.command == 'issue':
    account, code = core.issue(args.days)
    print(f'ID: {account}\nActivation code: {code}\nDays from activation: {args.days}')
elif args.command == 'list':
    with core.db() as c:
        for r in c.execute('SELECT * FROM accounts ORDER BY id'):
            exp = datetime.datetime.fromtimestamp(r['expires'], datetime.timezone.utc).isoformat() if r['expires'] else 'not activated'
            print(f"ID={r['id']} until={exp} revoked={bool(r['revoked'])} address={r['address'] or '-'}")
else:
    with core.db() as c:
        r = c.execute('SELECT * FROM accounts WHERE id=?', (args.id,)).fetchone()
        if not r:
            raise SystemExit('Account not found')
        if args.command == 'extend':
            if not 1 <= args.days <= 3650:
                raise SystemExit('days must be 1..3650')
            if r['revoked']:
                raise SystemExit('Revoked accounts cannot be extended; issue a new code')
            if r['expires']:
                c.execute('UPDATE accounts SET expires=? WHERE id=?', (max(r['expires'], int(time.time())) + args.days*86400, args.id))
            else:
                c.execute('UPDATE accounts SET days=days+? WHERE id=?', (args.days, args.id))
        elif args.command == 'revoke':
            core.remove(r['key'])
            c.execute('UPDATE accounts SET revoked=1 WHERE id=?', (args.id,))
        else:
            import secrets
            if r['revoked'] or (r['expires'] and r['expires'] <= int(time.time())):
                raise SystemExit('Account expired or revoked')
            core.remove(r['key'])
            code = secrets.token_urlsafe(24)
            c.execute('UPDATE accounts SET key=NULL,token_hash=NULL,code_hash=? WHERE id=?', (core.digest(code), args.id))
            print('New activation code:', code)
    print('OK')
