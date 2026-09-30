#!/usr/bin/env python3
"""Local root-only operator interface. Does not need bot token."""
import argparse
import billing
import core
p=argparse.ArgumentParser(description='Stars ledger and refund queue')
s=p.add_subparsers(dest='command',required=True)
s.add_parser('list')
s.add_parser('queue')
a=s.add_parser('refund'); a.add_argument('charge'); a.add_argument('--confirm',action='store_true')
args=p.parse_args(); billing.init()
with core.db() as c:
    if args.command=='list':
        for r in c.execute('SELECT * FROM payments ORDER BY paid_at DESC LIMIT 100'):
            print(f"tg={r['tg_id']} account={r['account_id']} days={r['days']} stars={r['stars']} refunded={r['refunded']} charge={r['charge']}")
    elif args.command=='queue':
        for r in c.execute('SELECT * FROM refund_jobs'): print(dict(r))
        for table in ('inbox','outbox'):
            for r in c.execute(f'SELECT * FROM {table} WHERE tries>0 ORDER BY next_try DESC LIMIT 20'):
                print(table, 'event=',r['update_id'] if table=='inbox' else r['id'],'tries=',r['tries'])
    else:
        r=c.execute('SELECT * FROM payments WHERE charge=?',(args.charge,)).fetchone()
        if not r: raise SystemExit('Unknown charge; inspect Telegram Stars history and retained payment inbox. Never refund an unverified charge.')
        if not args.confirm: raise SystemExit(f"This will refund {r['stars']} Stars and subtract {r['days']} days. Repeat with --confirm.")
        c.execute('INSERT OR IGNORE INTO refund_jobs(charge) VALUES (?)',(args.charge,))
        print('Queued. Bot must be running. Use: tiho-payments queue')
