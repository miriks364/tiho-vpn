#!/usr/bin/env python3
"""Interactive local configuration. Never pass bot token on command line."""
import getpass
import os
import re
import urllib.parse

path='/etc/tiho-bot.env'
if os.geteuid()!=0: raise SystemExit('Run as root')
if os.path.exists(path): raise SystemExit('Config exists; edit /etc/tiho-bot.env on the VPS instead of overwriting.')
values={}
values['BOT_TOKEN']=getpass.getpass('BotFather token (hidden): ').strip()
if not re.fullmatch(r'\d+:[A-Za-z0-9_-]{25,}',values['BOT_TOKEN']): raise SystemExit('Invalid token format')
values['ADMIN_TG_ID']=input('Your numeric Telegram user ID (start your bot first): ').strip()
if not values['ADMIN_TG_ID'].isdigit() or int(values['ADMIN_TG_ID'])<=0: raise SystemExit('Invalid ID')
for key,label in [('PUBLIC_API_URL','API URL, e.g. https://vpn.example.com'),('WEB_APP_URL','Web App URL, e.g. https://vpn.example.com/web-app'),('TERMS_URL','Published purchase/refund terms URL'),('PRIVACY_URL','Published privacy policy URL')]:
    value=input(label+': ').strip().rstrip('/')
    u=urllib.parse.urlparse(value)
    if u.scheme!='https' or not u.hostname or u.username or u.fragment: raise SystemExit('Invalid HTTPS URL')
    if key in ('PUBLIC_API_URL',) and (u.path or u.query): raise SystemExit('API URL must not contain a path/query')
    values[key]=value
values['SUPPORT_CONTACT']=input('Support contact, e.g. @your_support: ').strip()
values['SELLER_NAME']=input('Real seller/operator name: ').strip()
if not values['SUPPORT_CONTACT'] or not values['SELLER_NAME']: raise SystemExit('Seller and support required')
values['TERMS_VERSION']='2026-09-v1'
if any('\n' in x or '\r' in x for x in values.values()): raise SystemExit('Newlines not allowed')
def quote(s): return '"'+s.replace('\\','\\\\').replace('"','\\"')+'"'
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:
    for k,v in values.items(): f.write(k+'='+quote(v)+'\n')
print('Saved root-only configuration. No secrets were printed.')
